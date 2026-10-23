from fastapi import APIRouter, HTTPException

from app import memory
from app.boson.client import REALTIME_MODEL, REALTIME_URL, STT_MODEL, BosonClient, BosonError
from app.context.knowledge import MovieNotFound, load_movie
from app.context.persona import TOOLS, build_instructions
from app.schemas import SessionRequest, SessionResponse, Turn

router = APIRouter(prefix="/api", tags=["session"])


@router.post("/session", response_model=SessionResponse)
async def create_session(req: SessionRequest):
    """Called when the user pauses and picks a character.

    Returns everything the browser needs to open Higgs Realtime directly:
    an ephemeral key + the first `session.update` payload (already spoiler-filtered at t).
    """
    try:
        kb = load_movie(req.movie_id)
        character = kb.character(req.character_id)
    except (MovieNotFound, KeyError):
        raise HTTPException(404, "movie or character not found")

    transcription: dict = {"model": STT_MODEL}
    if req.user_lang:
        transcription["language"] = req.user_lang

    session = {
        "model": REALTIME_MODEL,
        "instructions": build_instructions(kb, req.character_id, req.t),
        # lip_sync: Realtime only thinks (text); the avatar endpoint speaks with the cloned voice.
        "output_modalities": ["text"] if req.mode == "lip_sync" else ["audio"],
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "turn_detection": {"type": "semantic_vad"},
                "transcription": transcription,
                "noise_reduction": {"type": "near_field"},
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "voice": character.voice_id or "default",
            },
        },
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.7,
    }

    client = BosonClient()
    secret = None
    if client.enabled:
        try:
            secret = await client.create_client_secret()
        except BosonError as e:
            raise HTTPException(502, str(e))

    history = memory.as_realtime_items(memory.load(req.movie_id, req.character_id))
    return SessionResponse(
        client_secret=secret,
        realtime_url=f"{REALTIME_URL}?model={REALTIME_MODEL}",
        session=session,
        character=character,
        history=history,
    )


@router.post("/memory/{movie_id}/{character_id}")
def save_turn(movie_id: str, character_id: str, turn: Turn):
    memory.append(movie_id, character_id, turn)
    return {"ok": True}


@router.delete("/memory/{movie_id}/{character_id}")
def clear_memory(movie_id: str, character_id: str):
    memory.clear(movie_id, character_id)
    return {"ok": True}
