"""Think -> check -> speak.

Higgs Realtime writes the character's reply as text. Each sentence comes here: in present (spoiler-
safe) mode it is checked against what the viewer hasn't seen yet (app/context/guard.py) and, if
needed, rewritten; then it is spoken with the character's cloned voice by Higgs TTS, streamed as
24 kHz 16-bit mono PCM. The check and the TTS run in parallel, so a clean sentence costs only the
check time (~0.6 s) on top of TTS; a spoiler is re-synthesised from the rewrite.
"""

import asyncio
import urllib.parse

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.boson.client import TTS_MODEL, BosonClient
from app.context.guard import check_sentence
from app.context.knowledge import MovieNotFound, load_movie
from app.schemas import KnowledgeMode

router = APIRouter(prefix="/api", tags=["speech"])


class SpeakRequest(BaseModel):
    movie_id: str
    character_id: str
    t: float
    knowledge: KnowledgeMode = "present"
    text: str
    question: str = ""


def _load(req: SpeakRequest):
    try:
        kb = load_movie(req.movie_id)
        return kb, kb.character(req.character_id)
    except (MovieNotFound, KeyError):
        raise HTTPException(404, "movie or character not found")


async def _checked(req: SpeakRequest, kb) -> tuple[bool, str]:
    if req.knowledge == "omniscient":
        return False, req.text
    return await check_sentence(kb, req.character_id, req.t, req.text, req.question)


@router.post("/check")
async def check(req: SpeakRequest):
    """Spoiler check only (lip-sync mode: the avatar endpoint does its own TTS)."""
    kb, _ = _load(req)
    spoiler, text = await _checked(req, kb)
    return {"spoiler": spoiler, "text": text}


async def _tts_stream(client: BosonClient, text: str, voice: str):
    async with httpx.AsyncClient(base_url=client.base_url, timeout=60,
                                 headers={"Authorization": f"Bearer {client.api_key}"}) as c:
        async with c.stream("POST", "/audio/speech", json={
            "model": TTS_MODEL, "input": text, "voice": voice, "response_format": "pcm", "stream": True,
        }) as r:
            if r.is_error:
                await r.aread()
                raise HTTPException(502, f"tts {r.status_code}: {r.text[:200]}")
            async for chunk in r.aiter_bytes():
                yield chunk


@router.post("/speak")
async def speak(req: SpeakRequest):
    """One sentence -> (spoiler check) -> cloned-voice PCM stream. The text actually spoken is
    returned in the X-Spoken-Text header (URL-encoded) so the chat shows exactly what was said."""
    kb, c = _load(req)
    client = BosonClient()
    if not client.enabled:
        raise HTTPException(503, "BOSON_API_KEY not configured")
    voice = c.voice_id or "default"

    # start synthesising the original sentence right away, while it is being checked
    async def pump(text: str, q: asyncio.Queue):
        try:
            async for chunk in _tts_stream(client, text, voice):
                await q.put(chunk)
        except Exception as e:  # noqa: BLE001
            await q.put(e)
        finally:
            await q.put(None)

    queue: asyncio.Queue = asyncio.Queue()
    tts_task = asyncio.create_task(pump(req.text, queue))
    spoiler, text = await _checked(req, kb)
    if spoiler:
        tts_task.cancel()  # throw away the audio of the spoiling sentence
        queue = asyncio.Queue()
        tts_task = asyncio.create_task(pump(text, queue))

    async def body():
        try:
            while (chunk := await queue.get()) is not None:
                if isinstance(chunk, Exception):
                    return
                yield chunk
        finally:
            tts_task.cancel()

    return StreamingResponse(body(), media_type="audio/pcm", headers={
        "X-Spoken-Text": urllib.parse.quote(text),
        "X-Spoiler-Rewritten": "1" if spoiler else "0",
        "Access-Control-Expose-Headers": "X-Spoken-Text, X-Spoiler-Rewritten",
    })
