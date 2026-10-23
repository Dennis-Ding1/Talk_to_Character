"""Shared data models. Field names match the JSON files in data/movies/<id>/ (see docs/data-spec.md)."""

from typing import Literal

from pydantic import BaseModel, Field


# ---------- movie data (on disk) ----------

class Movie(BaseModel):
    id: str
    title: str
    language: str = "en"  # main spoken language, ISO-639-1
    video: str = "video.mp4"  # file name inside the movie folder
    subtitles: str = "subtitles.srt"
    duration_s: float | None = None


class Character(BaseModel):
    id: str
    name: str
    aliases: list[str] = []
    bio: str = ""
    personality: str = ""
    speech_style: str = ""  # catchphrases, tone, dialect
    relationships: dict[str, str] = {}  # other character id -> description (baseline, t=0)
    # Assets
    face_image: str | None = None  # path relative to characters/<id>/
    face_at_s: float | None = None  # or: grab this frame from the video
    voice_clip: tuple[float, float] | None = None  # (start_s, end_s) of a clean 5-30s line
    voice_ref_text: str | None = None  # verbatim transcript of that clip
    voice_id: str | None = None  # Boson voice id after registration


class SubtitleLine(BaseModel):
    start: float
    end: float
    text: str
    speaker: str | None = None  # character id if known


class Scene(BaseModel):
    id: str
    start: float  # film (screen) time, seconds
    end: float
    characters_present: list[str] = []
    summary: str = ""
    key_events: list[str] = []
    lines: list[SubtitleLine] = []
    # Non-linear films: when the scene happens *in the story*. None = assume screen order.
    story_year: float | None = None
    thread: str | None = None  # e.g. "past", "hearing_1954", "senate_1959"
    slug: str = ""  # screenplay heading, e.g. "INT. ROOM 2022, ATOMIC ENERGY COMMISSION -- DAY"
    action: str = ""  # screenplay action lines (what we see) — used by the summarizer only


class CharacterState(BaseModel):
    """What a character wants/feels/thinks at the end of one scene.

    With `scene_id` set, the state is local to that scene (built only from it), and the runtime
    picks the latest state among scenes the character has already been seen in — so a state can
    never carry information from scenes the viewer hasn't watched yet.
    Without `scene_id` (hand-written data), `t` is a screen-time checkpoint.
    """

    character_id: str
    t: float
    scene_id: str | None = None
    goals: str = ""
    stance: str = ""
    emotion: str = ""
    relationships: dict[str, str] = {}
    knows: list[str] = []


# ---------- API ----------

OutputMode = Literal["voice_first", "lip_sync"]


class SessionRequest(BaseModel):
    movie_id: str
    character_id: str
    t: float = Field(ge=0, description="playback position in seconds")
    user_lang: str | None = None  # hint only; Higgs Realtime auto-detects
    mode: OutputMode = "voice_first"


class SessionResponse(BaseModel):
    client_secret: str | None  # ephemeral Boson key (None if no API key configured)
    realtime_url: str
    session: dict  # payload for the client's first `session.update`
    character: Character
    history: list[dict] = []  # prior turns to replay via conversation.item.create


class ToolCall(BaseModel):
    movie_id: str
    character_id: str
    t: float
    arguments: dict = {}


class AvatarRequest(BaseModel):
    movie_id: str
    character_id: str
    text: str | None = None  # lip_sync mode: drive with TTS
    audio_b64: str | None = None  # voice_first mode: drive with recorded reply audio (wav)
    face_id: str | None = None  # face crop from GET /api/movies/{id}/faces?t=
    size: Literal["640x640", "640x480", "480x640"] = "640x640"


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    t: float
