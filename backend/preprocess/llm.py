"""Pluggable LLM for offline preprocessing.

- "ollama" (default): free local model, e.g. `ollama pull qwen2.5:7b-instruct` (good at zh + en).
- "higgs_text": Higgs Realtime in text-only mode (costs Boson credit, no local GPU needed).
"""

import asyncio
import json
import re

import httpx

from app.boson.client import REALTIME_MODEL, REALTIME_URL
from app.config import get_settings


def _extract_json(text: str):
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    if not m:
        raise ValueError(f"no JSON in LLM output: {text[:300]}")
    return json.loads(m.group(0))


def _ollama(system: str, user: str) -> str:
    s = get_settings()
    r = httpx.post(
        f"{s.ollama_url}/api/chat",
        json={
            "model": s.ollama_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 8192},
        },
        timeout=600,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


async def _higgs_text_async(system: str, user: str) -> str:
    import websockets

    s = get_settings()
    async with websockets.connect(
        f"{REALTIME_URL}?model={REALTIME_MODEL}",
        additional_headers={"Authorization": f"Bearer {s.boson_api_key}"},
        max_size=None,
    ) as ws:
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "model": REALTIME_MODEL,
                "instructions": system,
                "output_modalities": ["text"],
                "audio": {"input": {"turn_detection": None}},
                "temperature": 0.2,
            },
        }))
        await ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": user}]},
        }))
        await ws.send(json.dumps({"type": "response.create"}))
        out = []
        async for raw in ws:
            ev = json.loads(raw)
            t = ev.get("type", "")
            if t.endswith("text.delta"):
                out.append(ev.get("delta", ""))
            elif t == "response.done":
                break
            elif t == "error":
                raise RuntimeError(ev)
        return "".join(out)


def chat_json(system: str, user: str):
    backend = get_settings().llm_backend
    if backend == "ollama":
        text = _ollama(system, user)
    elif backend == "higgs_text":
        text = asyncio.run(_higgs_text_async(system, user))
    else:
        raise ValueError(f"unknown LLM_BACKEND {backend!r}")
    return _extract_json(text)
