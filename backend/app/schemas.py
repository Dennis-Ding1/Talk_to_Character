"""Shared data models. Field names match the JSON files in data/movies/<id>/ (see dev-docs/data-spec.md)."""

from typing import Literal

from pydantic import BaseModel, Field


# ---------- movie data (on disk) ----------

class DemoSegment(BaseModel):
    """One clip of a demo cut: demo time [start, start+duration) plays source time [src_start, src_end)."""

    key: str
    title: str
    emoji: str = ""
    src_start: float
    src_end: float
    start: float
    duration: float
    jump: float | None = None  # where its chapter button jumps to (demo seconds); default: the start


class Movie(BaseModel):
    id: str
    title: str
    language: str = "en"  # main spoken language, ISO-639-1
    video: str = "video.mp4"  # file name inside the movie folder
    subtitles: str = "subtitles.srt"
    poster: str | None = None  # image shown before playback starts, file name inside the movie folder
    duration_s: float | None = None
    # Avatar replies use Realtime audio by default. Opt a movie into text-driven Higgs TTS 3
    # for explicit emotion/prosody tags; voice_first always stays on Realtime audio.
    avatar_speech: Literal["realtime", "tts3"] = "realtime"
    # A demo cut of another movie: only the video differs; every time is mapped back to `source`,
    # so characters remember and know exactly what they would at that point of the full film.
    source: str | None = None
    segments: list[DemoSegment] = []


class Character(BaseModel):
    id: str
    name: str
    aliases: list[str] = []
    bio: str = ""
    personality: str = ""
    speech_style: str = ""  # catchphrases, tone, dialect
    # expressive: scene mood + speech style may become explicit TTS/Realtime delivery controls.
    # subtle: preserve the cloned voice's natural performance; use tags only for cues in the reply.
    # None uses the project's character preset, then falls back to expressive.
    delivery_profile: Literal["expressive", "subtle"] | None = None
    tts_emotion: str | None = None  # allowlisted fallback when neither the line nor scene has a mood
    core: str = ""  # deep drives and beliefs that hold across the whole story (must not spoil anything)
    relationships: dict[str, str] = {}  # other character id -> description (baseline, t=0)
    # Assets
    face_image: str | None = None  # path relative to characters/<id>/
    face_at_s: float | None = None  # or: grab this frame from the video
    voice_clip: tuple[float, float] | None = None  # (start_s, end_s) of a clean 5-30s line
    voice_ref_text: str | None = None  # verbatim transcript of that clip
    voice_id: str | None = None  # Boson voice id after registration


class CharacterAtTime(Character):
    """A character for the pause picker, with their best-looking face as they appear right now."""

    look_id: str | None = None
    look_url: str | None = None


class SubtitleLine(BaseModel):
    start: float
    end: float
    text: str
    speaker: str | None = None  # character id if known
    vo: bool = False  # voice-over / off-screen narration (the speaker isn't in this scene)


class Beat(BaseModel):
    """Something that happens on screen (screenplay action), timed within the film."""

    t: float
    text: str


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
    beats: list[Beat] = []  # timed screenplay action: what happens on screen, second by second


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
    # inner notes (first person, this scene only): what I did, why, how it felt, what I'd rather hide
    did: str = ""
    why: str = ""
    felt: str = ""
    hiding: str = ""


# ---------- API ----------

OutputMode = Literal["voice_first", "lip_sync"]
# present: spoiler-safe, as of the pause point. omniscient: knows the whole story ("what if" mode).
KnowledgeMode = Literal["present", "omniscient"]


class SessionRequest(BaseModel):
    movie_id: str
    character_id: str
    t: float = Field(ge=0, description="playback position in seconds")
    user_lang: str | None = None  # hint only; Higgs Realtime auto-detects
    mode: OutputMode = "voice_first"
    knowledge: KnowledgeMode = "present"


class SessionResponse(BaseModel):
    client_secret: str | None  # ephemeral Boson key (None if no API key configured)
    realtime_url: str
    session: dict  # payload for the client's first `session.update`
    character: Character
    history: list[dict] = []  # prior turns to replay via conversation.item.create
    turn_note: str = ""  # send as a user text item after each user turn (keeps replies long + on-rules)
    as_of_year: float | None = None  # story year the character speaks from
    anchored: bool = False  # True: paused in a flash-forward; character is as of the viewer's progress
    knowledge: KnowledgeMode = "present"


class ToolCall(BaseModel):
    movie_id: str
    character_id: str
    t: float
    knowledge: KnowledgeMode = "present"
    arguments: dict = {}


class AvatarRequest(BaseModel):
    movie_id: str
    character_id: str
    t: float = Field(default=0, ge=0)  # pause point, used only to choose current vocal delivery
    text: str | None = None  # lip_sync mode: drive with TTS
    audio_b64: str | None = None  # voice_first mode: drive with recorded reply audio (wav)
    face_id: str | None = None  # face crop from GET /api/movies/{id}/faces?t=
    size: Literal["640x640", "640x480", "480x640"] = "640x640"


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    t: float
