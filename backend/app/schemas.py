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
    start: float
    end: float
    characters_present: list[str] = []
    summary: str = ""
    key_events: list[str] = []
    lines: list[SubtitleLine] = []


class CharacterState(BaseModel):
    """A checkpoint of what a character wants/feels/knows as of time t."""

    character_id: str
    t: float
    goals: str = ""
    stance: str = ""
    emotion: str = ""
    relationships: dict[str, str] = {}
    knows: list[str] = []  # facts the character has learned by t


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
    size: Literal["640x640", "640x480", "480x640"] = "640x640"


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    t: float
