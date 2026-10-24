from fastapi import APIRouter, HTTPException

from app import memory
from app.boson.client import REALTIME_MODEL, REALTIME_URL, STT_MODEL, BosonClient, BosonError
from app.config import get_settings
from app.context.knowledge import MovieNotFound, load_movie, resolve
from pydantic import BaseModel

from app.context.persona import TOOLS, build_instructions, question_notes, turn_note
from app.schemas import KnowledgeMode, SessionRequest, SessionResponse, Turn

router = APIRouter(prefix="/api", tags=["session"])


@router.post("/session", response_model=SessionResponse)
async def create_session(req: SessionRequest):
    """Called when the user pauses and picks a character.

    Returns everything the browser needs to open Higgs Realtime directly:
    an ephemeral key + the first `session.update` payload (already spoiler-filtered at t).
    """
    try:
        kb, t_src = resolve(req.movie_id, req.t)  # demo cut -> full film at the mapped time
        character = kb.character(req.character_id)
    except (MovieNotFound, KeyError):
        raise HTTPException(404, "movie or character not found")

    transcription: dict = {"model": STT_MODEL}
    if req.user_lang:
        transcription["language"] = req.user_lang

    voice_mode = req.mode == "voice_first"
    session = {
        "model": REALTIME_MODEL,
        "instructions": build_instructions(kb, req.character_id, t_src, req.knowledge),
        # voice_first: Realtime speaks directly with the cloned voice (first audio ~0.7 s after the
        # user stops talking); the browser spoiler-checks the reply transcript as it streams and makes
        # the character take back a sentence that reveals something.
        # lip_sync: Realtime also speaks the reply in the cloned voice, but the browser holds the
        # audio: once every sentence has passed the spoiler check, the avatar is driven by that audio
        # (rendering starts ~2 s sooner from audio than from text, and runs faster than real time).
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 24000},
                # voice_first: hands-free. Semantic VAD ends the turn when the user has finished
                # (also on natural pauses), and barges in when they talk over the character.
                # create_response=False: the browser asks for the reply itself once the transcript is
                # in (~0.3 s), so the memories relevant to the question can go in first.
                # lip_sync: push-to-talk; the client commits the audio when the mic is tapped again.
                "turn_detection": {"type": "semantic_vad", "create_response": False} if voice_mode else None,
                "transcription": transcription,
                # No server-side noise reduction: near_field cut most of each question before
                # transcription (measured: a 15-word question came back as its last 4 words).
                # The browser already applies echo cancellation and noise suppression.
                "noise_reduction": None,
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "voice": character.voice_id or "default",
            },
        },
        **({"tools": TOOLS, "tool_choice": "auto"} if get_settings().realtime_tools else {"tools": []}),
        "temperature": 0.7,
    }

    client = BosonClient()
    secret = None
    if client.enabled:
        try:
            secret = await client.create_client_secret()
        except BosonError as e:
            raise HTTPException(502, str(e))

    omni = req.knowledge == "omniscient"
    # conversations are kept per film and film time (a demo cut shares them with the full film, and
    # re-cutting the demo can't attach a chat to the wrong scene)
    history = memory.as_realtime_items(
        memory.load(kb.movie.id, req.character_id, req.knowledge, at_t=None if omni else t_src))
    return SessionResponse(
        client_secret=secret,
        realtime_url=f"{REALTIME_URL}?model={REALTIME_MODEL}",
        session=session,
        character=character,
        history=history,
        turn_note=turn_note(kb, t_src, req.knowledge),
        as_of_year=None if omni else kb.now_year(t_src),
        anchored=False if omni else kb.is_anchored(t_src),
        knowledge=req.knowledge,
    )


class _NotesRequest(BaseModel):
    movie_id: str
    character_id: str
    t: float
    knowledge: KnowledgeMode = "present"
    question: str


@router.post("/question_notes")
def get_question_notes(req: _NotesRequest):
    """Context to attach to one user question: relevant memories + "you've never met X" notes."""
    try:
        kb, t_src = resolve(req.movie_id, req.t)
        kb.character(req.character_id)
    except (MovieNotFound, KeyError):
        raise HTTPException(404, "movie or character not found")
    return {"notes": question_notes(kb, req.character_id, t_src, req.question, req.knowledge)}


def _film(movie_id: str, t: float = 0.0) -> tuple[str, float]:
    """(film id, film time): a demo cut's time maps to its full film."""
    try:
        kb, t_src = resolve(movie_id, t)
    except MovieNotFound:
        raise HTTPException(404, "movie not found")
    return kb.movie.id, t_src


@router.post("/memory/{movie_id}/{character_id}")
def save_turn(movie_id: str, character_id: str, turn: Turn, knowledge: KnowledgeMode = "present"):
    film, t_src = _film(movie_id, turn.t)
    memory.append(film, character_id, turn.model_copy(update={"t": t_src}), knowledge)
    return {"ok": True}


@router.delete("/memory/{movie_id}/{character_id}")
def clear_memory(movie_id: str, character_id: str):
    memory.clear(_film(movie_id)[0], character_id)
    return {"ok": True}
