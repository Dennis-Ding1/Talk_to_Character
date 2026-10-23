"""Align subtitle cues (timed, mostly unattributed) with screenplay lines (attributed, untimed).

Result: every spoken subtitle gets a speaker + a screenplay scene; consecutive cues of the same
scene become one film scene with real start/end times. Scenes the final cut reordered still match,
because matching is n-gram based with a locality preference rather than strictly monotonic.
"""

import re
from collections import defaultdict
from dataclasses import dataclass

import pysrt

from preprocess.screenplay import ScriptScene

_WORD_RE = re.compile(r"[a-z0-9']+")
_SOUND_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]|♪+|</?[a-z]+[^>]*>")
_LABEL_RE = re.compile(r"^([A-Z][A-Z0-9 .'\-]{1,30}):\s*")


def words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower().replace("’", "'"))


@dataclass
class Cue:
    idx: int
    start: float
    end: float
    text: str
    label: str | None = None  # speaker label printed in the SDH subtitle, if any
    # filled by align()
    script_line: int | None = None  # global id of the matched screenplay line
    scene: int | None = None
    speaker: str | None = None
    score: float = 0.0


def load_cues(path) -> list[Cue]:
    """Clean an SDH .srt: drop sound descriptions, split '- a / - b' two-speaker cues."""
    cues: list[Cue] = []
    for item in pysrt.open(str(path), encoding="utf-8"):
        start, end = item.start.ordinal / 1000, item.end.ordinal / 1000
        raw = item.text.replace("\r", "")
        parts = [p for p in re.split(r"(?:^|\n)\s*-\s+", raw) if p.strip()] if raw.lstrip().startswith("-") else [raw]
        for k, part in enumerate(parts):
            text = " ".join(part.split())
            label = None
            m = _LABEL_RE.match(text)
            if m:
                label, text = m.group(1).strip(), text[m.end():]
            text = _SOUND_RE.sub("", text).strip(" -")
            if not words(text):
                continue
            span = (end - start) / len(parts)
            cues.append(Cue(len(cues), start + k * span, start + (k + 1) * span, text, label))
    return cues


def _ngrams(ws: list[str], n: int) -> set[tuple]:
    return {tuple(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def align(cues: list[Cue], scenes: list[ScriptScene], window: int = 40) -> list[tuple[int, int, str]]:
    """Returns the flat screenplay line list [(scene_idx, line_idx, speaker)] and fills cue fields."""
    flat: list[tuple[int, int, str]] = []
    index: dict[int, dict[tuple, set[int]]] = {1: defaultdict(set), 2: defaultdict(set), 3: defaultdict(set)}
    line_words: list[list[str]] = []
    for s in scenes:
        for j, ln in enumerate(s.lines):
            gid = len(flat)
            flat.append((s.index, j, ln.speaker))
            ws = words(ln.text)
            line_words.append(ws)
            for n in (1, 2, 3):
                for g in _ngrams(ws, n):
                    index[n][g].add(gid)

    df1 = {g: len(ids) for g, ids in index[1].items()}
    n_scenes = len(scenes)

    # 1) per-cue candidate lines with a normalised match score
    cand: list[dict[int, float]] = []
    for c in cues:
        ws = words(c.text)
        scores: dict[int, float] = defaultdict(float)
        for n, weight in ((3, 3.0), (2, 1.5)):
            for g in _ngrams(ws, n):
                for gid in index[n].get(g, ()):
                    scores[gid] += weight
        if not scores:  # very short cue: rare words only
            for w in ws:
                if df1.get((w,), 99) <= 3:
                    for gid in index[1][(w,)]:
                        scores[gid] += 1.0
        norm = max(len(ws), 1)
        cand.append({gid: s / norm for gid, s in scores.items() if s / norm >= (0.5 if norm >= 4 else 1.0)})

    # 2) Viterbi over screenplay scenes: staying is free, moving to the next few scenes is cheap,
    #    any other jump (reordered cut) must be paid for by several good matches.
    STAY, NEXT, JUMP = 0.0, 0.6, 2.5
    NEG = -1e9
    score = [0.0] * n_scenes
    back: list[list[int]] = []
    for cs in cand:
        emit = [0.0] * n_scenes
        for gid, s in cs.items():
            sc = flat[gid][0]
            emit[sc] = max(emit[sc], min(s, 3.0))
        best_any = max(range(n_scenes), key=score.__getitem__)
        new, ptr = [NEG] * n_scenes, [0] * n_scenes
        for s in range(n_scenes):
            opts = [(score[s] - STAY, s), (score[best_any] - JUMP, best_any)]
            for d in (1, 2, 3):
                if s - d >= 0:
                    opts.append((score[s - d] - NEXT * d, s - d))
            v, p = max(opts)
            new[s], ptr[s] = v + emit[s], p
        score = new
        back.append(ptr)
    path = [max(range(n_scenes), key=score.__getitem__)]
    for ptr in reversed(back[1:]):
        path.append(ptr[path[-1]])
    path.reverse()

    # 3) assign scene + speaker (best matching line inside the chosen scene)
    for c, cs, sc in zip(cues, cand, path):
        c.scene = sc
        inside = {gid: s for gid, s in cs.items() if flat[gid][0] == sc}
        if inside:
            best = max(inside, key=lambda g: (inside[g], -abs(g)))
            c.script_line, c.score, c.speaker = best, inside[best], flat[best][2]
    return flat


def _fill_gaps(cues: list[Cue]) -> None:
    """Unmatched cues inherit the scene when both neighbours agree."""
    for i, c in enumerate(cues):
        if c.scene is not None:
            continue
        before = next((cues[j].scene for j in range(i - 1, -1, -1) if cues[j].scene is not None), None)
        after = next((cues[j].scene for j in range(i + 1, len(cues)) if cues[j].scene is not None), None)
        if before is not None and before == after:
            c.scene = before


def segments(cues: list[Cue], min_cues: int = 2) -> list[tuple[int, list[Cue]]]:
    """Group time-ordered cues into runs of the same screenplay scene (film scenes).

    Short runs (< min_cues, usually a stray mismatch) are merged into the surrounding run.
    """
    runs: list[list] = []
    for c in cues:
        if c.scene is None:
            if runs:
                runs[-1][1].append(c)
            continue
        if runs and runs[-1][0] == c.scene:
            runs[-1][1].append(c)
        else:
            runs.append([c.scene, [c]])
    merged: list[list] = []
    for sc, cs in runs:
        if merged and len(cs) < min_cues and len([x for x in cs if x.script_line is not None]) < min_cues:
            merged[-1][1].extend(cs)
        elif merged and merged[-1][0] == sc:
            merged[-1][1].extend(cs)
        else:
            merged.append([sc, cs])
    return [(sc, cs) for sc, cs in merged]
