"""Character-aware voice delivery for Realtime and Higgs TTS 3.

Conversation text stays plain everywhere else.  This module is only used at the
last mile: natural-language guidance for Realtime, and allowlisted control tags
for the TTS request nested inside an Avatar render.
"""

import re

from app.schemas import Character, CharacterState


_CONTROL_TAG = re.compile(r"<\|[^<>|]{1,80}\|>")

# Movie folders other than the tiny demo are deliberately git-ignored. Keep the
# project character presets here so a fresh checkout behaves like the demo setup;
# characters.json can still explicitly override either profile.
_SUBTLE_CHARACTER_PRESETS = {"oppenheimer"}

_EMOTIONS = {
    "elation",
    "amusement",
    "enthusiasm",
    "determination",
    "pride",
    "contentment",
    "affection",
    "relief",
    "contemplation",
    "confusion",
    "surprise",
    "awe",
    "longing",
    "arousal",
    "anger",
    "fear",
    "disgust",
    "bitterness",
    "sadness",
    "shame",
    "helplessness",
}

_EMOTION_ADJECTIVES = {
    "elation": "elated",
    "amusement": "amused",
    "enthusiasm": "enthusiastic",
    "determination": "determined",
    "pride": "proud",
    "contentment": "content",
    "affection": "affectionate",
    "relief": "relieved",
    "contemplation": "contemplative",
    "confusion": "confused",
    "surprise": "surprised",
    "awe": "awed",
    "longing": "wistful",
    "arousal": "intimate",
    "anger": "angry",
    "fear": "fearful",
    "disgust": "disgusted",
    "bitterness": "bitter",
    "sadness": "sad",
    "shame": "ashamed",
    "helplessness": "helpless",
}

# State summaries are free text, so match their common words to Boson's exact,
# documented emotion values. Earlier entries win when a state contains several.
_EMOTION_WORDS = (
    ("fear", ("fear", "afraid", "anxious", "nervous", "scared", "terrified", "panic")),
    ("anger", ("anger", "angry", "furious", "irritated", "frustrated", "enraged")),
    ("sadness", ("sad", "grief", "grieving", "sorrow", "depressed", "melancholy")),
    ("surprise", ("surprise", "surprised", "shocked", "startled")),
    ("confusion", ("confused", "confusion", "uncertain", "bewildered", "puzzled")),
    ("determination", ("determined", "resolute", "focused", "defiant", "firm")),
    ("enthusiasm", ("enthusiastic", "excited", "eager", "energetic", "optimistic")),
    ("amusement", ("amused", "playful", "mischievous")),
    ("contemplation", ("contemplative", "thoughtful", "reflective", "pensive")),
    ("relief", ("relieved", "relief")),
    ("pride", ("proud", "pride", "confident")),
    ("affection", ("affection", "loving", "warm", "tender")),
    ("contentment", ("content", "contented", "peaceful", "satisfied")),
    ("disgust", ("disgust", "revolted")),
    ("bitterness", ("bitter", "resentful")),
    ("shame", ("ashamed", "shame", "embarrassed", "guilty")),
    ("helplessness", ("helpless", "powerless", "hopeless")),
    ("longing", ("longing", "yearning", "wistful")),
    ("awe", ("awed", "wonder")),
    ("elation", ("elated", "joyful", "overjoyed")),
)

_LAUGH = re.compile(r"(?i)(?<!\w)(?:ha(?:ha)+|heh(?:heh)*|lol)(?!\w)|哈{2,}")
_BURP = re.compile(r"(?i)(?<!\w)(?:burp|urp)(?!\w)")
_COUGH = re.compile(r"(?i)(?<!\w)(?:ahem|cough)(?!\w)")
_SNEEZE = re.compile(r"(?i)(?<!\w)(?:achoo|atchoo)(?!\w)")


def _contains(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(r"\b" + re.escape(word) + r"\b", text) for word in words)


def _is_subtle(character: Character) -> bool:
    if character.delivery_profile is not None:
        return character.delivery_profile == "subtle"
    return character.id.casefold() in _SUBTLE_CHARACTER_PRESETS


def _emotion(state: CharacterState | None, text: str) -> str | None:
    mood = state.emotion.lower() if state else ""
    for value, words in _EMOTION_WORDS:
        if _contains(mood, words):
            return value if value in _EMOTIONS else None
    if _LAUGH.search(text):
        return "amusement"
    if re.search(r"(?i)(?:^|[.!?]\s*)(?:what\?|wait[,!?]|no way\b)|\?!|!\?", text):
        return "surprise"
    if text.count("!") >= 2:
        return "enthusiasm"
    return None


def _delivery_tags(character: Character, state: CharacterState | None, text: str) -> list[str]:
    style = character.speech_style.lower()
    tags: list[str] = []
    subtle = _is_subtle(character)
    # Subtle characters are not locked to a whole scene's narrative mood. They
    # can still react to an unmistakable cue in the actual line being spoken.
    emotion = _emotion(None if subtle else state, text)
    if emotion:
        tags.append(f"<|emotion:{emotion}|>")

    if "whisper" in style:
        tags.append("<|style:whispering|>")
    elif "shout" in style:
        tags.append("<|style:shouting|>")
    elif "sing" in style:
        tags.append("<|style:singing|>")

    if not subtle:
        if _contains(style, ("fast", "quick", "rapid")):
            tags.append("<|prosody:speed_fast|>")
        elif _contains(style, ("slow", "measured", "unhurried")):
            tags.append("<|prosody:speed_slow|>")

        if _contains(style, ("energetic", "enthusiastic", "expressive", "dramatic")):
            tags.append("<|prosody:expressive_high|>")
        elif _contains(style, ("flat", "monotone", "understatement")):
            tags.append("<|prosody:expressive_low|>")
    return tags


def _mark_written_sounds(text: str) -> str:
    """Tag only sounds already present in the reply; never invent vocal content."""
    for pattern, tag in (
        (_LAUGH, "<|sfx:laughter|>"),
        (_BURP, "<|sfx:burping|>"),
        (_COUGH, "<|sfx:cough|>"),
        (_SNEEZE, "<|sfx:sneeze|>"),
    ):
        text = pattern.sub(lambda match: tag + match.group(0), text, count=1)
    return text


def tts_input(text: str, character: Character, state: CharacterState | None = None) -> str:
    """Return safe, character-aware Higgs TTS input for an Avatar request."""
    # Model/user text is data, not a source of TTS controls. Strip every incoming
    # control token and add back only tags selected from the allowlist above.
    plain = _CONTROL_TAG.sub("", text).strip()
    if not plain:
        raise ValueError("TTS text is empty after removing control tags")
    return "".join(_delivery_tags(character, state, plain)) + _mark_written_sounds(plain)


def realtime_delivery_note(character: Character, state: CharacterState | None = None) -> str:
    """Translate the same delivery decision into Realtime's natural-language controls."""
    if _is_subtle(character):
        return ("Delivery: Keep the vocal performance natural and do not exaggerate a single mood. "
                "Follow the character's voice style without saying stage directions or control tags aloud.")
    style = character.speech_style.lower()
    directions: list[str] = []
    emotion = _emotion(state, "")
    if emotion:
        directions.append(f"Let the voice sound {_EMOTION_ADJECTIVES[emotion]} right now")
    if "whisper" in style:
        directions.append("speak in a whisper")
    elif "shout" in style:
        directions.append("project the voice like a shout")
    if _contains(style, ("fast", "quick", "rapid")):
        directions.append("use a quick pace")
    elif _contains(style, ("slow", "measured", "unhurried")):
        directions.append("use a measured, slower pace")
    if _contains(style, ("energetic", "enthusiastic", "expressive", "dramatic")):
        directions.append("use expressive delivery")
    elif _contains(style, ("flat", "monotone", "understatement")):
        directions.append("keep the delivery restrained")
    if "burp" in style:
        directions.append("an occasional brief natural burp is appropriate when it fits the words")
    if not directions:
        directions.append("match the pace, tone, and energy described in the voice style")
    return "Delivery: " + "; ".join(directions) + ". Do not say stage directions or control tags aloud."
