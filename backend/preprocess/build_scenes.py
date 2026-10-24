"""Screenplay + subtitles -> knowledge/scenes.json (no LLM).

Each film scene = a run of subtitle cues aligned to one screenplay scene. We get:
speaker per line, who's present (speakers + names in the action lines), the screenplay heading,
colour/B&W timeline, and the story year from `story_years.json` (hand-reviewable).
"""

import json
import re
from pathlib import Path

from app.schemas import Character, Scene, SubtitleLine
from preprocess.align import align, load_cues, segments
from preprocess.screenplay import ScriptScene, load_screenplay


def _expand(spec: str) -> list[int]:
    out: list[int] = []
    for part in str(spec).split(","):
        a, _, b = part.strip().partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return out


def load_story_years(path: Path, scenes: list[ScriptScene]) -> dict[int, tuple[float | None, str]]:
    """screenplay scene index -> (story_year, thread)."""
    result: dict[int, tuple[float | None, str]] = {s.index: (None, "past") for s in scenes}
    if not path.exists():
        return result
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for s in scenes:
        for thread, rule in cfg.get("threads", {}).items():
            if any(m in s.slug.upper() for m in rule["match"]):
                result[s.index] = (rule["year"], thread)
                break
    explicit: set[int] = set()
    for r in cfg.get("ranges", []):
        for i in _expand(r["scenes"]):
            if i in result:
                result[i] = (r["year"], r.get("thread", result[i][1]))
                explicit.add(i)
    # "INT. SAME -- DAY" continues the previous scene
    for s in scenes[1:]:
        if " SAME " in f" {s.slug.upper()} " and s.index not in explicit and result[s.index][0] is None:
            result[s.index] = result[s.index - 1]
    return result


def _name_index(cast: list[Character]) -> dict[str, str]:
    idx: dict[str, str] = {}
    for c in cast:
        for n in [c.id, c.name, *c.aliases]:
            idx[n.upper()] = c.id
    return idx


def _speaker_id(name: str | None, idx: dict[str, str]) -> str | None:
    if not name:
        return None
    n = name.upper().strip()
    if n in idx:
        return idx[n]
    n2 = re.sub(r"^(YOUNG|OLD|DR\.?|MR\.?|MRS\.?|GENERAL|COLONEL|LT\.?|SENATOR)\s+", "", n)
    if n2 in idx:
        return idx[n2]
    last = n.split()[-1]
    return idx.get(last, re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"))


def _mentioned(text: str, cast: list[Character], first_person_id: str | None) -> set[str]:
    found: set[str] = set()
    for c in cast:
        names = {c.name, *c.aliases}
        names = {n for n in names if len(n) > 3}
        if any(re.search(rf"\b{re.escape(n)}\b", text, re.I) for n in names):
            found.add(c.id)
    if first_person_id and re.search(r"\b(I|ME|MY|MYSELF)\b", text):
        found.add(first_person_id)
    return found


def build(folder: Path, cast: list[Character], subtitles: str, duration: float | None,
          first_person: str | None = None) -> list[Scene]:
    """first_person: character id the screenplay's 'I/ME' refers to in colour scenes (Oppenheimer)."""
    script = load_screenplay(folder / "screenplay.pdf")
    cues = load_cues(folder / subtitles)
    flat = align(cues, script)
    years = load_story_years(folder / "story_years.json", script)
    idx = _name_index(cast)
    vo_lines = {gid for gid, (sc, j, _) in enumerate(flat) if script[sc].lines[j].vo}

    segs = segments(cues)
    scenes: list[Scene] = []
    for n, (sc, cs) in enumerate(segs):
        s = script[sc]
        lines, speakers = [], set()
        for c in cs:
            spk = _speaker_id(c.label, idx) if c.label else _speaker_id(c.speaker, idx)
            vo = c.script_line in vo_lines
            lines.append(SubtitleLine(start=round(c.start, 3), end=round(c.end, 3), text=c.text, speaker=spk, vo=vo))
            # On screen = says a non-voice-over screenplay line. An SDH label alone ("STRAUSS: ...") is
            # often there precisely because the speaker is off screen (narration over a flashback).
            if spk and c.script_line is not None and c.script_line not in vo_lines:
                speakers.add(spk)
        action = " ".join(s.action)
        year, thread = years.get(sc, (None, "past"))
        fp = first_person if s.timeline == "colour" else None
        if thread == "past":
            present = speakers | _mentioned(action, cast, fp)
        else:
            # hearings: people are *talked about* constantly; only speakers (and the narrator) are there
            present = speakers | ({fp} if fp and re.search(r"\b(I|ME|MY)\b", action) else set())
        slug = s.slug
        k = sc
        while " SAME " in f" {slug.upper()} " and k > 0:  # resolve "INT. SAME" to the real place
            k -= 1
            slug = script[k].slug
        scenes.append(Scene(
            id=f"s{n:03d}",
            start=round(cs[0].start, 3),
            end=0.0,
            characters_present=sorted(present),
            lines=lines,
            story_year=year,
            thread=thread,
            slug=slug,
            action=action[:2000],
        ))
    for a, b in zip(scenes, scenes[1:]):
        a.end = b.start
    if scenes:
        scenes[-1].end = duration or scenes[-1].lines[-1].end + 5
    fp_name = None
    if first_person:
        fp_char = next((c for c in cast if c.id == first_person), None)
        fp_name = (fp_char.aliases[0] if fp_char and fp_char.aliases else fp_char.name) if fp_char else None
    _add_beats(scenes, segs, script, cues, flat, fp_name)
    return scenes


_FIRST_PERSON = [(re.compile(r"\b(MYSELF|myself)\b"), "himself"),
                 (re.compile(r"\b(MY|my)\b"), "{n}'s"),
                 (re.compile(r"\b(I|ME|me)\b"), "{n}")]


def _third_person(text: str, name: str) -> str:
    """The screenplay narrates Oppenheimer's scenes as 'I'/'ME'; other characters' memories need a name."""
    for pat, rep in _FIRST_PERSON:
        text = pat.sub(rep.format(n=name), text)
    return text


def _add_beats(scenes: list[Scene], segs, script: list[ScriptScene], cues, flat, fp_name: str | None) -> None:
    """Time every screenplay action paragraph from the dialogue around it, and attach it to the film
    scene playing at that moment. A beat sits just after the line before it (or just before the line
    after it), so a pause mid-scene knows exactly which actions have already happened on screen."""
    from app.schemas import Beat

    # when each screenplay line is spoken in the film: (scene index, line index) -> (start, end)
    spoken: dict[tuple[int, int], tuple[float, float]] = {}
    for c in cues:
        if c.script_line is None:
            continue
        sc, j, _ = flat[c.script_line]
        a, b = spoken.get((sc, j), (c.start, c.end))
        spoken[(sc, j)] = (min(a, c.start), max(b, c.end))
    film_scenes_of: dict[int, list[Scene]] = {}
    for (sc, _), fs in zip(segs, scenes):
        film_scenes_of.setdefault(sc, []).append(fs)

    for sc, film in film_scenes_of.items():
        s = script[sc]
        timed = [(k, v, spoken.get((sc, v)) if k == "line" else None) for k, v in s.elements]
        for pos, (kind, text, _) in enumerate(timed):
            if kind != "action":
                continue
            prev_t = next((tm[1] for _, _, tm in reversed(timed[:pos]) if tm), None)
            next_t = next((tm[0] for _, _, tm in timed[pos + 1:] if tm), None)
            if prev_t is not None:
                t = prev_t + 0.5 if next_t is None else min(prev_t + 0.5, (prev_t + next_t) / 2)
            elif next_t is not None:
                t = max(next_t - 1.0, film[0].start)
            else:
                t = film[0].start
            # the film scene (of this screenplay scene) that is playing at t, else the closest one
            home = next((f for f in film if f.start <= t < f.end), None) or min(
                film, key=lambda f: min(abs(f.start - t), abs(f.end - t)))
            t = min(max(t, home.start), home.end - 0.01)
            body = re.sub(r"\s+", " ", text).strip()
            # drop PDF watermarks, dual-dialogue debris ("ROBB (CONT'D) KITTY (CONT'D) ...") and scraps
            if (re.search(r"8FLiX|SCREENPLAY DATABASE|\(CONT[’']D\)|^\(COLOU?R\)$", body)
                    or len(body.split()) < 3):
                continue
            if fp_name and s.timeline == "colour":
                body = _third_person(body, fp_name)
            home.beats.append(Beat(t=round(t, 2), text=body))
    for f in scenes:
        f.beats.sort(key=lambda b: b.t)
