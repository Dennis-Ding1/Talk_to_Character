"""LLM passes over the scenes:

1. per scene: summary, key_events, who is present (speaker attribution if missing)
2. per character, walking forward in time: a state checkpoint after each scene they're in
   (goals / stance / emotion / relationships / what they've learned).

Each step only ever sees the past, so the generated knowledge is spoiler-free by construction.
"""

import json

from app.schemas import Character, CharacterState, Scene
from preprocess.llm import chat_json

SCENE_SYSTEM = """You annotate scenes of a film from its subtitles.
Return JSON: {"summary": str, "key_events": [str], "characters_present": [character_id]}
- summary: 1-3 sentences, factual, written in English, include who did/said what.
- key_events: important plot facts revealed in THIS scene only.
- characters_present: ids from the given cast list who appear (speaking or clearly addressed).
Do not use any knowledge of the film beyond the given text."""

STATE_SYSTEM = """You track one film character's inner state over time.
Given their profile, their previous state and the scene they were just in, return JSON:
{"goals": str, "stance": str, "emotion": str, "relationships": {character_id: str}, "knows": [str]}
- Only update based on what this character witnessed. Keep "knows" cumulative but short (<=15 items).
Do not use any knowledge of the film beyond the given text."""


def _cast_text(cast: list[Character]) -> str:
    return "\n".join(f"- {c.id}: {c.name} ({', '.join(c.aliases)}) — {c.bio}" for c in cast)


def annotate_scenes(scenes: list[Scene], cast: list[Character], context: str = "") -> list[Scene]:
    cast_text = _cast_text(cast)
    ids = {c.id for c in cast}
    prev_summary = ""
    for s in scenes:
        dialogue = "\n".join(f"{ln.speaker or '?'}: {ln.text}" for ln in s.lines)
        user = (
            f"Cast:\n{cast_text}\n\nExtra context: {context or '-'}\n\n"
            f"Previous scene: {prev_summary or '-'}\n\nThis scene's subtitles:\n{dialogue}"
        )
        out = chat_json(SCENE_SYSTEM, user)
        s.summary = out.get("summary", "")
        s.key_events = out.get("key_events", [])
        present = [c for c in out.get("characters_present", []) if c in ids]
        s.characters_present = list(dict.fromkeys(s.characters_present + present))
        prev_summary = s.summary
        print(f"  {s.id} [{s.start:.0f}s] {s.summary[:80]}")
    return scenes


def build_states(scenes: list[Scene], cast: list[Character]) -> list[CharacterState]:
    states: list[CharacterState] = []
    for c in cast:
        prev: dict = {"goals": "", "stance": "", "emotion": "", "relationships": c.relationships, "knows": []}
        profile = f"{c.name}: {c.bio}\nPersonality: {c.personality}"
        for s in scenes:
            if c.id not in s.characters_present:
                continue
            user = (
                f"Character profile:\n{profile}\n\nPrevious state:\n{json.dumps(prev, ensure_ascii=False)}\n\n"
                f"Scene summary: {s.summary}\nKey events: {s.key_events}"
            )
            out = chat_json(STATE_SYSTEM, user)
            prev = {k: out.get(k, prev.get(k)) for k in prev}
            states.append(CharacterState(character_id=c.id, t=s.end, **prev))
        print(f"  {c.id}: {sum(1 for st in states if st.character_id == c.id)} checkpoints")
    return states
