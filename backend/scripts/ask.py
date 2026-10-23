"""Ask a character a question at a given pause time, from the command line (Higgs Realtime, text mode).

Uses exactly the same instructions + tools as the web app.

  python scripts/ask.py oppenheimer oppenheimer 44:00 "What do you think of this project?"
  python scripts/ask.py oppenheimer strauss 1:05:00 "你怎么看奥本海默？" --show-prompt
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import websockets  # noqa: E402

from app.boson.client import REALTIME_MODEL, REALTIME_URL, BosonClient  # noqa: E402
from app.context.knowledge import load_movie  # noqa: E402
from app.context.persona import TOOLS, build_instructions  # noqa: E402
from app.routers.tools import run_tool  # noqa: E402
from app.schemas import ToolCall  # noqa: E402


def language_hint(text: str) -> str:
    """Same as frontend detectLanguage(): keep typed non-English questions answered in kind."""
    import re
    for pat, lang in ((r"[぀-ヿ]", "Japanese"), (r"[가-힯]", "Korean"),
                      (r"[一-鿿]", "Chinese"), (r"[Ѐ-ӿ]", "Russian")):
        if re.search(pat, text):
            return f"{text}\n\n(Reply in {lang}.)"
    return text


def parse_t(s: str) -> float:
    parts = [float(p) for p in s.split(":")]
    t = 0.0
    for p in parts:
        t = t * 60 + p
    return t


async def ask(movie: str, character: str, t: float, questions: list[str], show_prompt: bool):
    kb = load_movie(movie)
    instructions = build_instructions(kb, character, t)
    cur = kb.current_scene(t)
    print(f"[{movie} @ {t / 60:.1f} min] on screen: {cur.slug if cur else '?'} (story year {cur.story_year if cur else '?'})")
    print(f"[{character}] knows {len(kb.known_scenes(character, t))} scenes; prompt {len(instructions)} chars")
    if show_prompt:
        print("-" * 60 + "\n" + instructions + "\n" + "-" * 60)

    secret = await BosonClient().create_client_secret(ttl_s=120)
    async with websockets.connect(
        f"{REALTIME_URL}?model={REALTIME_MODEL}",
        subprotocols=["realtime", f"bai-client-secret.{secret}"],
        max_size=None,
    ) as ws:
        await ws.send(json.dumps({"type": "session.update", "session": {
            "model": REALTIME_MODEL, "instructions": instructions, "output_modalities": ["text"],
            "tools": TOOLS, "tool_choice": "auto", "temperature": 0.7,
        }}))
        for q in questions:
            print(f"\nYou: {q}")
            await ws.send(json.dumps({"type": "conversation.item.create", "item": {
                "type": "message", "role": "user", "content": [{"type": "input_text", "text": language_hint(q)}]}}))
            await ws.send(json.dumps({"type": "response.create"}))
            out: list[str] = []
            pending_tools = 0
            async for raw in ws:
                ev = json.loads(raw)
                typ = ev["type"]
                if typ == "response.output_text.delta":
                    out.append(ev["delta"])
                elif typ == "response.function_call_arguments.done":
                    args = json.loads(ev.get("arguments") or "{}")
                    res = run_tool(ev["name"], ToolCall(movie_id=movie, character_id=character, t=t, arguments=args))
                    print(f"  (tool {ev['name']}({args}) -> {res['result'][:120]!r}...)")
                    await ws.send(json.dumps({"type": "conversation.item.create", "item": {
                        "type": "function_call_output", "call_id": ev["call_id"], "output": res["result"]}}))
                    pending_tools += 1
                elif typ == "response.done":
                    if pending_tools:
                        pending_tools = 0
                        await ws.send(json.dumps({"type": "response.create"}))
                        continue
                    break
                elif typ == "error":
                    print("ERROR", ev["error"])
                    break
            print(f"{kb.character(character).name}: {''.join(out).strip()}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("movie")
    ap.add_argument("character")
    ap.add_argument("t", help="pause time, e.g. 44:00 or 1:16:30 or seconds")
    ap.add_argument("questions", nargs="+")
    ap.add_argument("--show-prompt", action="store_true")
    a = ap.parse_args()
    asyncio.run(ask(a.movie, a.character, parse_t(a.t), a.questions, a.show_prompt))
