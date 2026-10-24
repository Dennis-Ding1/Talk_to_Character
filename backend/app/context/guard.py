"""Spoiler guard: check what a character is about to say *before* it is spoken.

The realtime model writes the reply as text; each sentence is checked against the key events of the
scenes the viewer hasn't watched yet. If a sentence reveals or confirms one of them (or states an
outcome the viewer hasn't seen), it is rewritten in the character's voice to "not yet / don't know".
The checker is the only model that sees those future facts; the speaking model never does.
"""

import asyncio
import json
import re

import websockets

from app.boson.client import REALTIME_MODEL, REALTIME_URL
from app.config import get_settings
from app.context.knowledge import MovieKnowledge

GUARD_SYSTEM = """You are a spoiler filter for an interactive film. A viewer paused the film and is talking
to a character. You get: what the viewer has NOT seen yet (future events), and one sentence the
character is about to say. Decide if the sentence reveals, confirms or strongly hints at any future
event, or states the outcome of something whose outcome the viewer hasn't seen (e.g. that a test
worked, that someone dies, how a trial ends). Talking about plans, hopes, fears, preparations and
uncertainty is fine. If it spoils, rewrite it in the same voice and language so it says the thing
hasn't happened yet / the character doesn't know yet — revealing nothing from the future events.
Return JSON only: {"spoiler": true|false, "rewrite": "<sentence or empty>"}"""


def future_facts(kb: MovieKnowledge, character_id: str, t: float, limit: int = 70) -> list[str]:
    """Key events of scenes the viewer hasn't watched yet (screen time >= t): all of the character's
    own future scenes, then the soonest other scenes, up to `limit` lines."""
    unseen = [s for s in kb.scenes if s.start >= t and (s.key_events or s.summary)]
    own = [s for s in unseen if character_id in s.characters_present]
    other = [s for s in unseen if character_id not in s.characters_present]
    picked = own[: limit // 2]
    picked += other[: limit - len(picked)]
    picked.sort(key=lambda s: s.start)
    out = []
    for s in picked:
        out.append(s.key_events[0] if s.key_events else s.summary.split(". ")[0])
    return out


async def _higgs_text(system: str, user: str, timeout: float = 8.0) -> str:
    s = get_settings()
    async with websockets.connect(
        f"{REALTIME_URL}?model={REALTIME_MODEL}",
        additional_headers={"Authorization": f"Bearer {s.boson_api_key}"},
        max_size=None, open_timeout=timeout,
    ) as ws:
        await ws.send(json.dumps({"type": "session.update", "session": {
            "model": REALTIME_MODEL, "instructions": system, "output_modalities": ["text"],
            "audio": {"input": {"turn_detection": None}}, "temperature": 0.0, "max_output_tokens": 300}}))
        await ws.send(json.dumps({"type": "conversation.item.create", "item": {
            "type": "message", "role": "user", "content": [{"type": "input_text", "text": user}]}}))
        await ws.send(json.dumps({"type": "response.create"}))
        out: list[str] = []
        async def read():
            async for raw in ws:
                ev = json.loads(raw)
                if ev.get("type") == "response.output_text.delta":
                    out.append(ev.get("delta", ""))
                elif ev.get("type") == "response.done":
                    return
                elif ev.get("type") == "error":
                    raise RuntimeError(ev)
        await asyncio.wait_for(read(), timeout)
        return "".join(out)


async def check_sentence(kb: MovieKnowledge, character_id: str, t: float, sentence: str,
                         question: str = "") -> tuple[bool, str]:
    """Returns (was_spoiler, text_to_speak). Fails open on errors (speaks the original)."""
    facts = future_facts(kb, character_id, t)
    if not facts or not sentence.strip():
        return False, sentence
    c = kb.character(character_id)
    user = (f"Character: {c.name}\n"
            f"Future events the viewer has NOT seen yet:\n- " + "\n- ".join(facts) +
            (f"\n\nThe viewer asked: {question}" if question else "") +
            f"\n\nSentence the character is about to say:\n{sentence}")
    try:
        raw = await _higgs_text(GUARD_SYSTEM, user)
        m = re.search(r"\{.*\}", raw, re.S)
        verdict = json.loads(m.group(0)) if m else {}
    except Exception:  # noqa: BLE001 — never block the conversation on the guard
        return False, sentence
    if verdict.get("spoiler") and str(verdict.get("rewrite", "")).strip():
        return True, str(verdict["rewrite"]).strip()
    return False, sentence
