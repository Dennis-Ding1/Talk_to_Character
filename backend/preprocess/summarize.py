"""LLM passes over the scenes:

1. per scene: summary, key_events, who is present
2. per (scene, character present): that character's state at the end of the scene
   (goals / stance / emotion / relationships), from THIS scene only.

States are local on purpose: the runtime composes them from scenes the viewer has already seen,
so a state can never smuggle in information from later in the film (important for non-linear
films where story order != screen order).
"""

from app.schemas import Character, CharacterState, Scene
from preprocess.llm import chat_json

SCENE_SYSTEM = """You annotate scenes of a film from its screenplay and subtitles.
Return JSON: {"summary": str, "key_events": [str], "characters_present": [character_id]}
- summary: 2-3 sentences, factual, in English, say who did/said what and what it means for them.
- key_events: up to 4 important facts revealed in THIS scene only.
- characters_present: ids from the cast list physically in the scene (not just mentioned).
Use only the given text."""

STATE_SYSTEM = """You write ONE film character's inner voice at the END of one scene, in the FIRST PERSON.
Return JSON: {"goals": str, "stance": str, "emotion": str, "relationships": {character_id: str}}
Describe only the named character, as they would honestly think it ("I want...", "I think...").
- goals: what I want right now and why (1 sentence, concrete)
- stance: what I really think about the big issues in my life at this point (the work, the war,
  politics, loyalty, the people around me), with my own bias and attitude (1-2 sentences, plain words)
- emotion: how I feel (a few words)
- relationships: for each other cast member I deal with in this scene, what I think of them now
  (1 short blunt sentence, first person). Keys must be ids from the cast list given.
Be consistent with the character's drives and what they have lived through so far. Use only the
given text; do not use knowledge of what happens later. Plain words, no grand abstract phrases."""


def _cast_text(cast: list[Character]) -> str:
    return "\n".join(f"- {c.id}: {c.name} ({', '.join(c.aliases)}) — {c.bio}" for c in cast)


def _scene_text(s: Scene, names: dict[str, str]) -> str:
    dialogue = "\n".join(f"{names.get(ln.speaker or '', ln.speaker or '?')}: {ln.text}" for ln in s.lines)
    when = f"Story year: {int(s.story_year)}\n" if s.story_year else ""
    where = f"Heading: {s.slug}\n" if s.slug else ""
    action = f"What we see (screenplay): {s.action[:1500]}\n" if s.action else ""
    return f"{when}{where}{action}Dialogue:\n{dialogue}"


def annotate_scenes(scenes: list[Scene], cast: list[Character], context: str = "") -> list[Scene]:
    cast_text = _cast_text(cast)
    ids = {c.id for c in cast}
    names = {c.id: c.name for c in cast}
    for s in scenes:
        if s.summary:
            continue  # resumable
        user = f"Cast:\n{cast_text}\n\nExtra context: {context or '-'}\n\n{_scene_text(s, names)}"
        try:
            out = chat_json(SCENE_SYSTEM, user)
        except Exception as e:  # noqa: BLE001 — keep going, scene stays unsummarized
            print(f"  {s.id} failed: {e}")
            continue
        s.summary = out.get("summary", "")
        s.key_events = [str(e) for e in out.get("key_events", [])][:4]
        present = [c for c in out.get("characters_present", []) if c in ids]
        s.characters_present = sorted(set(s.characters_present) | set(present))
        print(f"  {s.id} [{s.start / 60:.0f}m] {s.summary[:90]}")
    return scenes


def build_states(scenes: list[Scene], cast: list[Character],
                 existing: list[CharacterState] | None = None) -> list[CharacterState]:
    names = {c.id: c.name for c in cast}
    alias = {n.lower(): c.id for c in cast for n in [c.id, c.name, *c.aliases]}
    done = {(st.character_id, st.scene_id) for st in existing or []}
    states = list(existing or [])
    # `scenes` are in screen order. A state for scene X is only ever used once the viewer has watched
    # X, i.e. after every scene that starts before X -> earlier scenes are safe context (no spoilers).
    by_screen = sorted(scenes, key=lambda x: x.start)
    for idx, s in enumerate(by_screen):
        for c in cast:
            if c.id not in s.characters_present or (c.id, s.id) in done:
                continue
            spoke = any(ln.speaker == c.id for ln in s.lines)
            if not spoke and not s.summary:
                continue
            before = [p for p in by_screen[:idx] if c.id in p.characters_present and p.summary][-6:]
            if s.story_year is not None:  # flash-forwards seen earlier aren't "before" in their life
                before = [p for p in before if p.story_year is None or p.story_year <= s.story_year]
            so_far = "\n".join(f"- ({int(p.story_year) if p.story_year else '?'}) {p.summary}" for p in before)
            others = ", ".join(f"{o.id} ({o.name})" for o in cast if o.id in s.characters_present and o.id != c.id)
            user = (f"Character: {c.name} ({c.id})\nProfile: {c.bio} Personality: {c.personality}\n"
                    f"Drives: {c.core}\n"
                    f"What I've been through recently:\n{so_far or '- (nothing yet)'}\n"
                    f"Other cast in this scene: {others or 'none'}\n\n"
                    f"Scene summary: {s.summary}\n{_scene_text(s, names)}\n\n"
                    f"Now write {c.name}'s inner voice — only {c.name} — at the end of this scene, "
                    f"in the first person.")
            try:
                out = chat_json(STATE_SYSTEM, user)
            except Exception as e:  # noqa: BLE001
                print(f"  state {c.id}@{s.id} failed: {e}")
                continue
            rel = {}
            for k, v in (out.get("relationships") or {}).items():
                cid = alias.get(str(k).strip().lower())  # model may answer with names instead of ids
                if cid and cid != c.id:
                    rel[cid] = str(v)
            states.append(CharacterState(
                character_id=c.id, t=s.end, scene_id=s.id,
                goals=str(out.get("goals", "")), stance=str(out.get("stance", "")),
                emotion=str(out.get("emotion", "")), relationships=rel,
            ))
    print(f"  {len(states)} character states")
    return states
