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
            lines.append(SubtitleLine(start=round(c.start, 3), end=round(c.end, 3), text=c.text, speaker=spk))
            if spk and (c.label or c.script_line not in vo_lines):
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
    return scenes
