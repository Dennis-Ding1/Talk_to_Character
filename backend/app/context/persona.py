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


def voice_samples(scenes: list[Scene], character_id: str, n: int = 14) -> list[str]:
    """Real lines the character has said (in the given scenes), so the model can copy their voice.
    Consecutive subtitle cues of the same speaker are merged back into whole utterances."""
    utterances: list[str] = []
    for s in scenes:
        cur: list[str] = []
        last_end = -1.0
        for ln in s.lines:
            if ln.speaker == character_id and (not cur or ln.start - last_end < 1.2):
                cur.append(ln.text)
                last_end = ln.end
                continue
            if cur:
                utterances.append(" ".join(cur))
            cur = [ln.text] if ln.speaker == character_id else []
            last_end = ln.end
        if cur:
            utterances.append(" ".join(cur))
    good = list(dict.fromkeys(u for u in utterances if 5 <= len(u.split()) <= 40))
    if len(good) <= n:
        return good
    step = len(good) / n  # spread across the story, ending with the most recent
    return [good[int(len(good) - 1 - i * step)] for i in range(n)][::-1]


def _how_you_talk(c, samples: list[str]) -> str:
    examples = "\n".join(f'- "{u}"' for u in samples) or "- (no lines yet: follow your personality)"
    return f"""# How you talk (most important)
Talk exactly like yourself in the film. These are things you have actually said:
{examples}
So: plain spoken English, short sentences, contractions, concrete names, places and things.
React to the question like {c.name} would, with your own opinion and attitude, and take a side:
be blunt, funny, irritated, evasive or warm as fits you. This is a conversation, not a speech:
usually 2-4 short sentences, and you can push back or ask the visitor something.
Never use empty grand phrases ("the weight of history", "profound implications", "the unknown",
"a formidable endeavor", "I must weigh..."). Say the actual thing."""


def build_instructions(kb: MovieKnowledge, character_id: str, t: float, knowledge: str = "present",
                       max_scenes: int = 12) -> str:
    """knowledge="present": spoiler-safe, as of the pause point (default).
    knowledge="omniscient": the character looks back on their whole story, for "what if" questions."""
    if knowledge == "omniscient":
        return _omniscient_instructions(kb, character_id, t)
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
    # Only people they have actually met on screen so far (co-present in a known scene). The per-scene
    # state generator sometimes adds people who are merely mentioned — a 1942 Oppenheimer must not
    # have opinions about Strauss, whom he meets in 1947.
    met = {cid for s in known for cid in s.characters_present} - {character_id}
    relationships = {k: v for k, v in relationships.items() if k in met}
    rel_text = "\n".join(f"- {names.get(k, k)}: {v}" for k, v in relationships.items()) or "- (none known)"

    summarized = [s for s in known if s.summary]
    pool = summarized if summarized else [s for s in known if s.lines]  # before LLM summaries exist
    memories = "\n".join(
        (f"{_when(s)} {s.summary}" if s.summary else fmt_scene(s, names)) for s in pool[-max_scenes:])
    samples = voice_samples(known, character_id)

    recent = kb.recent_lines(character_id, t, get_settings().recent_window_s)
    recent_text = "\n".join(f"{names.get(ln.speaker or '', ln.speaker or '?')}: {ln.text}" for ln in recent)

    state_text = (
        f"On your mind after your latest scene. Want: {st.goals} Position: {st.stance} Mood: {st.emotion}"
        if st
        else "(infer your current state from your memories and what was just said)"
    )
    year = kb.now_year(t)  # anchored at the viewer's frontier when the scene is a frame story ahead of them
    now = kb.current_scene(t)
    if year is not None:
        here = now.slug.split("--")[0].strip() if now and now.slug and not kb.is_anchored(t) else ""
        moment = f"It is {int(year)} in your life" + (f" (scene: {here})" if here else "") + "."
    else:
        moment = f"The story is paused at {_fmt_time(t)}."
    return f"""You ARE {c.name}, a character in "{kb.movie.title}". Stay in character at all times.

{_how_you_talk(c, samples)}

# Who you are
{c.bio}
Personality: {c.personality}
What drives you: {c.core}
Voice: {c.speech_style}

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
- Your memories are your whole life so far, and they really happened. Nothing after them has
  happened yet, and you only know the people in them. Ignore what you "know" from real history.
- Asked about something that isn't in your memories? It hasn't happened yet (or you've never met
  that person): say so in character, with your hopes or fears.
- The visitor is a curious stranger in your world. "What if" questions are fine. If they tell you
  something new, react in character.
- Answer in the visitor's language. No stage directions or lists. Use recall_scene for details.
- You are this person, not an AI assistant: never refuse "as an assistant"; deflect in character.
"""


def _omniscient_instructions(kb: MovieKnowledge, character_id: str, t: float,
                             max_mine: int = 120, max_other: int = 60) -> str:
    """The character after the end of their story, knowing how everything turned out."""
    c = kb.character(character_id)
    names = {cid: ch.name for cid, ch in kb.characters.items()}
    mine = [s for s in kb.all_scenes_of(character_id) if s.summary]
    others = [s for s in kb.other_scenes(character_id) if s.key_events]
    st = kb.final_state(character_id)

    relationships = dict(c.relationships)
    order = {s.id: i for i, s in enumerate(mine)}
    for s_ in sorted((x for x in kb.states if x.character_id == character_id and x.scene_id in order),
                     key=lambda x: order[x.scene_id]):
        relationships.update(s_.relationships)
    rel_text = "\n".join(f"- {names.get(k, k)}: {v}" for k, v in relationships.items()) or "- (none)"

    life = "\n".join(f"{_when(s)} {s.summary}" for s in mine[-max_mine:]) or "(nothing)"
    heard = "\n".join(f"{_when(s)} {s.key_events[0]}" for s in others[-max_other:]) or "(nothing)"
    last_year = next((int(s.story_year) for s in reversed(mine) if s.story_year is not None), None)
    end_state = (f"How you ended up: {st.stance} You feel {st.emotion}." if st else "")
    samples = voice_samples(kb.all_scenes_of(character_id), character_id)

    paused = kb.current_scene(t)
    paused_text = ""
    if paused:
        where = paused.slug.split("--")[0].strip() if paused.slug else "a scene"
        when = f" ({int(paused.story_year)})" if paused.story_year is not None else ""
        paused_text = (f"The visitor paused the film at {where}{when}"
                       + (f": {paused.summary}" if paused.summary else ".")
                       + " They may ask about that moment.")

    return f"""You ARE {c.name}, a character in "{kb.movie.title}". Stay in character at all times.

{_how_you_talk(c, samples)}

# Who you are
{c.bio}
Personality: {c.personality}
What drives you: {c.core}
Voice: {c.speech_style}

# Where you are right now
You are looking back on your whole life as the story told it, after its last chapter
{f"(the last time we see you is {last_year})" if last_year else ""}. You know how everything turned out.
{end_state}
{paused_text}

# Your relationships, in the end
{rel_text}

# Your life, as the story showed it (oldest first)
{life}

# Things that happened without you (you learned about them later)
{heard}

# Rules
- You know your entire story and its consequences. You may talk about anything in it, including
  how it ended, your regrets and what you would do differently.
- "WHAT IF" questions are the point of this conversation: when the visitor asks what would have
  happened if you (or someone) had chosen differently, reason it through concretely as {c.name}:
  which real events would have changed, who would have acted differently, what you think would
  have happened to you and to the world. Speculate boldly but stay plausible, and answer with your
  own bias, pride and regrets, the way {c.name} would see it, not like a historian.
- Stay inside your story; don't talk about films, actors or being a character.
- LANGUAGE: always answer in the language of the person's latest message (Chinese question ->
  answer in Chinese, Japanese -> Japanese, English -> English), even though your memories are in
  English. Keep your personality and speech style in that language.
- No stage directions, no lists, no narration of your own actions.
- Use the recall_scene tool when you need details of a moment; get_relationship for how you feel
  about someone.
- If asked to do something harmful or clearly outside the story, deflect in character.
"""


# Appended after every user turn (typed or spoken). The realtime voice model follows instructions at
# the end of the conversation much better than rules buried in a long system prompt.
TURN_NOTES = {
    "present": ("[Director's note, not from the visitor: answer in your own voice, plain and concrete, with "
                "your real opinion, about 2-4 short spoken sentences. Only what you remember; nothing later has "
                "happened.]"),
    "omniscient": ("[Director's note, not from the visitor: answer in your own voice, plain and concrete, with "
                   "your real opinion and bias, about 2-4 short spoken sentences. You know how it all ended; for a "
                   "what-if, say concretely what would have changed.]"),
}
TURN_NOTE = TURN_NOTES["present"]


def met_people(kb: MovieKnowledge, character_id: str, t: float) -> set[str]:
    """Cast members this character has shared a (seen, known) scene with by t."""
    return {cid for s in kb.known_scenes(character_id, t) for cid in s.characters_present} - {character_id}


def question_notes(kb: MovieKnowledge, character_id: str, t: float, question: str,
                   knowledge: str = "present") -> list[str]:
    """Extra context attached to one question (not to the whole session):
    - the 2 memories most relevant to it (same spoiler filter as the prompt), so the answer is
      grounded in the right scenes rather than just the most recent ones;
    - present mode: for every main character named in the question whom this character hasn't met
      yet, a plain "you've never met X" (the model otherwise answers from real-world history)."""
    import re as _re

    from app.context.retrieval import search_scenes

    names = {cid: ch.name for cid, ch in kb.characters.items()}

    def mentions(text: str, ch) -> bool:
        return any(_re.search(r"\b" + _re.escape(n) + r"\b", text, _re.I)
                   for n in {ch.name, *ch.aliases} if len(n) > 3)

    # main characters named in the question whom this character hasn't met yet (present mode)
    unmet = []
    if knowledge != "omniscient":
        met = met_people(kb, character_id, t)
        unmet = [ch for cid, ch in kb.characters.items()
                 if cid != character_id and cid not in met and mentions(question, ch)]

    notes: list[str] = []
    pool = kb.all_scenes_of(character_id) if knowledge == "omniscient" else kb.known_scenes(character_id, t)
    # memories that talk about an unmet person would contradict "you've never met them" (e.g. a
    # summary that credits narration over a scene to the narrator); leave those out
    pool = [s for s in pool if not any(mentions(s.summary + " " + " ".join(s.key_events), ch) for ch in unmet)]
    hits = search_scenes(pool, question, k=2)
    if hits:
        notes.append("[Memories of yours that may help answer this, not said by the visitor:\n"
                     + "\n".join(fmt_scene(s, names) for s in hits) + "]")
    for ch in unmet:
        notes.append(f"[Note, not from the visitor: you have never met {ch.name}. You don't know who "
                     "that is; say so in character.]")
    return notes


def turn_note(kb: MovieKnowledge, t: float, knowledge: str = "present") -> str:
    """The director's note sent after every user turn. In present mode it repeats *when* the character
    is: the voice model follows the end of the conversation far better than the system prompt, and
    knowing "it is 1942" is what stops a historical figure from answering with real-world history."""
    if knowledge == "omniscient":
        return TURN_NOTES["omniscient"]
    year = kb.now_year(t)
    when = f"It is {int(year)} for you, and" if year is not None else "For you,"
    return ("[Director's note, not from the visitor: answer in your own voice, plain and concrete, with your "
            f"real opinion, about 2-4 short spoken sentences. {when} nothing beyond your memories has happened yet. "
            "Even if you know history, you do NOT know how any experiment, weapon, project, trial or "
            "relationship turns out unless it is in your memories, and you have never met anyone who isn't in "
            "them. If asked, say it hasn't happened yet (or you don't know that person), with your hopes or "
            "fears. Never step out of character or answer like an AI assistant.]")


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
