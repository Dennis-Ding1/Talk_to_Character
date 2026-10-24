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


INNER_SYSTEM = """You write a film character's PRIVATE inner notes about one scene, in the FIRST PERSON,
as they would honestly think it to themselves. Use what happens ON SCREEN (the actions) as much as
the dialogue: actions often carry the real story (a poisoned apple, a look, a lie).
Return JSON only:
{"did": "what I did in this scene, concretely (1-2 sentences)",
 "why": "my real reasons and motives, including ugly or petty ones (1-3 sentences)",
 "felt": "what I felt, in plain words (1 sentence)",
 "hiding": "what I'd rather nobody knew or I won't admit out loud ('' if nothing)"}
Think about cause and effect like a novelist: what in this scene (or in my earlier notes) provoked
me, and how does that explain what I did? Connect my actions to earlier ones (e.g. if I poisoned
something earlier and someone is about to eat it, THAT is why I react). For shocking actions give the
real psychology: humiliation, resentment, envy, fear, guilt, desire, panic.
Be specific to this scene and consistent with my drives and my earlier notes.
Use only the given text; nothing from later in the story. Plain words, no grand phrases."""


def _beats_text(s: Scene, limit: int = 2500) -> str:
    return "\n".join(f"- {b.text}" for b in s.beats)[:limit]


def build_inner_notes(scenes: list[Scene], cast: list[Character], states: list[CharacterState],
                      only: set[str], workers: int = 4) -> list[CharacterState]:
    """Adds did/why/felt/hiding to the per-scene states of the characters in `only` (creating a state
    if a scene had none). Each character's notes are written in screen order and see that character's
    own earlier notes (so "why did I grab the apple" can follow from "I poisoned it"); characters run in
    parallel. Context = this scene + the character's earlier scenes, so nothing comes from what the
    viewer hasn't seen yet."""
    from concurrent.futures import ThreadPoolExecutor

    names = {c.id: c.name for c in cast}
    by_key = {(st.character_id, st.scene_id): st for st in states}
    by_screen = sorted(scenes, key=lambda x: x.start)
    nl = "\n"

    def notes_for(c: Character) -> int:
        done = 0
        mine = [x for x in by_screen if c.id in x.characters_present]
        for s in mine:
            st = by_key.get((c.id, s.id))
            if st and st.why:
                continue  # resumable
            if not (s.summary or s.beats or any(ln.speaker == c.id for ln in s.lines)):
                continue
            before = [p for p in mine if p.start < s.start and p.summary and
                      (s.story_year is None or p.story_year is None or p.story_year <= s.story_year)]
            so_far = nl.join(f"- ({int(p.story_year) if p.story_year else '?'}) {p.summary}" for p in before[-5:])
            prev_notes = []
            for p in before[-4:]:
                ps = by_key.get((c.id, p.id))
                if ps and ps.did:
                    prev_notes.append(f"- ({p.slug.split('--')[0].strip()}) I did: {ps.did} Why: {ps.why}")
            dialogue = nl.join(f"{names.get(ln.speaker or '', ln.speaker or '?')}"
                               f"{' (voice-over)' if ln.vo else ''}: {ln.text}" for ln in s.lines)[:3000]
            user = (f"Character: {c.name} ({c.id}){nl}Profile: {c.bio} Personality: {c.personality}{nl}"
                    f"Drives: {c.core}{nl}"
                    f"What I've been through recently:{nl}{so_far or '- (nothing yet)'}{nl}"
                    f"My own private notes from those scenes:{nl}{nl.join(prev_notes) or '- (none)'}{nl}{nl}"
                    f"THIS SCENE ({int(s.story_year) if s.story_year else '?'}; {s.slug}){nl}"
                    f"Summary: {s.summary}{nl}What happens on screen:{nl}{_beats_text(s) or '- (no action notes)'}{nl}"
                    f"Dialogue:{nl}{dialogue}{nl}{nl}Write {c.name}'s private inner notes about this scene.")
            try:
                out = chat_json(INNER_SYSTEM, user)
            except Exception as e:  # noqa: BLE001
                print(f"  inner {c.id}@{s.id} failed: {e}")
                continue
            if st is None:
                st = CharacterState(character_id=c.id, t=s.end, scene_id=s.id)
                states.append(st)
                by_key[(c.id, s.id)] = st
            st.did, st.why = str(out.get("did", "")), str(out.get("why", ""))
            st.felt, st.hiding = str(out.get("felt", "")), str(out.get("hiding", ""))
            done += 1
            if done % 20 == 0:
                print(f"  {c.id}: {done} notes")
        print(f"  {c.id}: done ({done} new)")
        return done

    targets = [c for c in cast if c.id in only]
    with ThreadPoolExecutor(max(1, min(workers, len(targets)))) as ex:
        list(ex.map(notes_for, targets))
    return states


MOMENT_SYSTEM = """You write what a film character is thinking AT ONE EXACT MOMENT inside a scene, in the
FIRST PERSON, as private thoughts. You get everything that has happened in the scene UP TO this moment
(on-screen actions and dialogue) and nothing after. Explain the WHY of what I just did or am about to
react to, connecting it to my earlier actions and feelings (e.g. "that's the apple I poisoned last
night — if Bohr bites it he dies"). Include the ugly or petty parts if they are true.
Return JSON only: {"thought": "2-4 plain sentences, first person, present tense"}
Use only the given text; nothing from later. Plain words, no grand phrases."""


def build_moment_notes(scenes: list[Scene], cast: list[Character], states: list[CharacterState],
                       only: set[str], ranges: list[tuple[float, float]], workers: int = 4,
                       every_s: float = 30.0) -> list[dict]:
    """Time-anchored thoughts inside scenes, so a pause in the middle of a scene still has the
    character's inner life up to that second (a whole-scene note would spoil its ending).
    Checkpoints: each on-screen action beat, plus one every `every_s` seconds of dialogue.
    Only for scenes overlapping `ranges` (e.g. the clips of a demo cut)."""
    from concurrent.futures import ThreadPoolExecutor

    nl = "\n"
    names = {c.id: c.name for c in cast}
    by_key = {(st.character_id, st.scene_id): st for st in states}
    by_screen = sorted(scenes, key=lambda x: x.start)
    in_range = [s for s in by_screen if any(s.start < b and s.end > a for a, b in ranges)]

    jobs = []
    for s in in_range:
        times = sorted({round(b.t, 1) for b in s.beats})
        k = s.start + every_s
        while k < s.end:
            times.append(round(k, 1))
            k += every_s
        times = sorted(times)
        dedup: list[float] = []
        for x in times:
            if not dedup or x - dedup[-1] >= 4.0:
                dedup.append(x)
        for c in cast:
            if c.id not in only or c.id not in s.characters_present:
                continue
            for t in dedup:
                jobs.append((c, s, t))

    def run(job):
        c, s, t = job
        mine = [p for p in by_screen if c.id in p.characters_present and p.start < s.start and p.summary]
        if s.story_year is not None:
            mine = [p for p in mine if p.story_year is None or p.story_year <= s.story_year]
        earlier = []
        for p in mine[-4:]:
            st = by_key.get((c.id, p.id))
            line = f"- ({p.slug.split('--')[0].strip()}) {p.summary}"
            if st and st.did:
                line += f" | I did: {st.did} Why: {st.why}"
            earlier.append(line)
        so_far = sorted(
            [(b.t, f"[on screen] {b.text}") for b in s.beats if b.t <= t + 0.01]
            + [(ln.start, f"{names.get(ln.speaker or '', ln.speaker or '?')}: {ln.text}") for ln in s.lines
               if ln.start <= t + 0.01])
        scene_so_far = nl.join(x for _, x in so_far)[-3500:]
        user = (f"Character: {c.name} ({c.id}){nl}Profile: {c.bio} Personality: {c.personality}{nl}"
                f"Drives: {c.core}{nl}"
                f"My earlier scenes and private notes:{nl}{nl.join(earlier) or '- (none)'}{nl}{nl}"
                f"THIS SCENE ({int(s.story_year) if s.story_year else '?'}; {s.slug}), "
                f"everything up to this moment:{nl}{scene_so_far}{nl}{nl}"
                f"What is {c.name} thinking right now, at this exact moment?")
        try:
            out = chat_json(MOMENT_SYSTEM, user)
            return {"character_id": c.id, "scene_id": s.id, "t": t, "text": str(out.get("thought", "")).strip()}
        except Exception as e:  # noqa: BLE001
            print(f"  moment {c.id}@{s.id}/{t} failed: {e}")
            return None

    print(f"  {len(jobs)} moment notes to write")
    with ThreadPoolExecutor(workers) as ex:
        notes = [n for n in ex.map(run, jobs) if n and n["text"]]
    return sorted(notes, key=lambda n: (n["character_id"], n["t"]))
