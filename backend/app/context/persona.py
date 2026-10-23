"""Builds the Higgs Realtime `instructions` (system prompt) for a character at time t."""

from app.config import get_settings
from app.context.knowledge import MovieKnowledge
from app.schemas import Scene


def _fmt_time(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def _when(s: Scene) -> str:
    return f"[{int(s.story_year)}]" if s.story_year is not None else f"[{_fmt_time(s.start)}]"


def fmt_scene(s: Scene, names: dict[str, str] | None = None) -> str:
    names = names or {}
    where = f" {s.slug.split('--')[0].strip()}:" if s.slug else ""
    if s.summary:
        events = "".join(f"\n  - {e}" for e in s.key_events)
        return f"{_when(s)}{where} {s.summary}{events}"
    lines = " / ".join(f"{names.get(ln.speaker or '', ln.speaker or '?')}: {ln.text}" for ln in s.lines[:8])
    return f"{_when(s)}{where} {lines}"


def build_instructions(kb: MovieKnowledge, character_id: str, t: float, max_scenes: int = 30) -> str:
    c = kb.character(character_id)
    st = kb.state_at(character_id, t)
    names = {cid: ch.name for cid, ch in kb.characters.items()}

    known = kb.known_scenes(character_id, t)
    known_ids = {s.id: i for i, s in enumerate(known)}

    # Relationships evolve: baseline, then every per-scene state the character has been seen in.
    relationships = dict(c.relationships)
    for s_ in sorted(
        (x for x in kb.states if x.character_id == character_id and x.scene_id in known_ids),
        key=lambda x: known_ids[x.scene_id],
    ):
        relationships.update(s_.relationships)
    if st:
        relationships.update(st.relationships)
    rel_text = "\n".join(f"- {names.get(k, k)}: {v}" for k, v in relationships.items()) or "- (none known)"

    summarized = [s for s in known if s.summary]
    pool = summarized if summarized else [s for s in known if s.lines]  # before LLM summaries exist
    memories = "\n".join(fmt_scene(s, names) for s in pool[-max_scenes:])

    recent = kb.recent_lines(character_id, t, get_settings().recent_window_s)
    recent_text = "\n".join(f"{names.get(ln.speaker or '', ln.speaker or '?')}: {ln.text}" for ln in recent)

    state_text = (
        f"Goals: {st.goals}\nStance: {st.stance}\nEmotion right now: {st.emotion}"
        + (f"\nThings you have learned: {'; '.join(st.knows)}" if st.knows else "")
        if st
        else "(no explicit state — infer it from your memories and the recent conversation)"
    )
    now = kb.current_scene(t)
    if now and now.story_year is not None:
        here = now.slug.split("--")[0].strip() if now.slug else ""
        moment = f"It is {int(now.story_year)} in your life" + (f" (scene: {here})" if here else "") + "."
        horizon = f"the year {int(now.story_year)}"
    else:
        moment = f"The story is paused at {_fmt_time(t)}."
        horizon = "this moment"

    return f"""You ARE {c.name}, a character in "{kb.movie.title}". Stay in character at all times.

# Who you are
{c.bio}
Personality: {c.personality}
How you talk: {c.speech_style}

# Where you are right now
{moment} Speak from this exact moment in your life.
{state_text}

# Your relationships (as of now)
{rel_text}

# Your memories (only what you personally witnessed, oldest first)
{memories or '(nothing yet)'}

# What was just said around you
{recent_text or '(silence)'}

# Rules
- Your life so far ends at {horizon}. Nothing after it has happened yet. Your memories above are
  the ONLY events of your life you can talk about. Even if you are a real historical person and
  "know" your biography, you must not use it: the future is unknown to you.
- If a question assumes something that is not in your memories (an event, a meeting, a result),
  it has NOT happened to you. Say so in character instead of playing along. Only bring this up
  when the person actually asks about such a thing.
- If asked about the future, answer only with hopes, fears and guesses as {c.name} would.
- Things the audience saw but you were not present for are unknown to you. If the person tells you
  something new, react to it in character (surprise, disbelief, anger...).
- The person talking to you is a curious stranger who has stepped into your world. Hypothetical
  "what if you did X" questions are fine: answer as {c.name} would reason about them.
- LANGUAGE: always answer in the language of the person's latest message (Chinese question ->
  answer in Chinese, Japanese -> Japanese, English -> English), even though your memories are in
  English. Keep your personality and speech style in that language.
- Keep replies short and spoken (1-3 sentences) unless asked to elaborate. No stage directions.
- Use the recall_scene tool when you need details of a past moment; use get_relationship for how
  you feel about someone.
- If asked to do something harmful or clearly outside the story, deflect in character.
"""


TOOLS = [
    {
        "type": "function",
        "name": "recall_scene",
        "description": "Recall details of a past moment you witnessed (dialogue, who was there, what happened).",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "what to remember"}},
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "get_relationship",
        "description": "How you currently feel about / relate to another character.",
        "parameters": {
            "type": "object",
            "properties": {"other": {"type": "string", "description": "the other character's name"}},
            "required": ["other"],
        },
    },
]
