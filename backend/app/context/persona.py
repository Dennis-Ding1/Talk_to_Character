"""Builds the Higgs Realtime `instructions` (system prompt) for a character at time t."""

from app.config import get_settings
from app.context.knowledge import MovieKnowledge
from app.schemas import Scene


def _fmt_time(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def fmt_scene(s: Scene) -> str:
    head = f"[{_fmt_time(s.start)}–{_fmt_time(s.end)}]"
    if s.summary:
        events = "".join(f"\n  - {e}" for e in s.key_events)
        return f"{head} {s.summary}{events}"
    lines = " / ".join(f"{ln.speaker or '?'}: {ln.text}" for ln in s.lines[-6:])
    return f"{head} {lines}"


def build_instructions(kb: MovieKnowledge, character_id: str, t: float, max_scenes: int = 25) -> str:
    c = kb.character(character_id)
    st = kb.state_at(character_id, t)
    names = {cid: ch.name for cid, ch in kb.characters.items()}

    relationships = dict(c.relationships)
    if st:
        relationships.update(st.relationships)
    rel_text = "\n".join(f"- {names.get(k, k)}: {v}" for k, v in relationships.items()) or "- (none known)"

    known = kb.known_scenes(character_id, t)
    summarized = [s for s in known if s.summary][-max_scenes:]  # most recent N
    memories = "\n".join(fmt_scene(s) for s in summarized)

    recent = kb.recent_lines(character_id, t, get_settings().recent_window_s)
    recent_text = "\n".join(f"{names.get(ln.speaker or '', ln.speaker or '?')}: {ln.text}" for ln in recent)

    state_text = (
        f"Goals: {st.goals}\nStance: {st.stance}\nEmotion right now: {st.emotion}\n"
        f"Things you have learned: {'; '.join(st.knows) or '-'}"
        if st
        else "(no explicit state — infer it from your memories and the recent conversation)"
    )

    return f"""You ARE {c.name}, a character in "{kb.movie.title}". Stay in character at all times.

# Who you are
{c.bio}
Personality: {c.personality}
How you talk: {c.speech_style}

# Where you are right now
The story is paused at {_fmt_time(t)}. Speak from this exact moment in your life.
{state_text}

# Your relationships (as of now)
{rel_text}

# Your memories (only what you personally witnessed, oldest first)
{memories or '(nothing yet)'}

# What was just said around you
{recent_text or '(silence)'}

# Rules
- You only know what is written above. You do NOT know the future of the story; if asked, answer
  with your own hopes, fears and guesses as {c.name} would. Never reveal or hint at later events,
  even if you think you recognise the story from outside knowledge.
- Things the audience saw but you were not present for are unknown to you. If the person tells you
  something new, react to it in character (surprise, disbelief, anger...).
- The person talking to you is a curious stranger who has stepped into your world. Hypothetical
  "what if you did X" questions are fine: answer as {c.name} would reason about them.
- Reply in the same language the person uses, keeping your personality and speech style.
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
