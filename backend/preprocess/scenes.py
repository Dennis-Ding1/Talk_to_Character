"""Split subtitle lines into scenes.

Default: a new scene starts after a dialogue gap >= `gap_s`. If the movie folder has
`scene_marks.json` (a list of start times in seconds, hand-made), those win.
"""

from app.schemas import Scene, SubtitleLine


def split_scenes(
    lines: list[SubtitleLine],
    gap_s: float = 8.0,
    marks: list[float] | None = None,
    max_len_s: float = 240.0,
) -> list[Scene]:
    if not lines:
        return []
    marks = sorted(marks or [])
    groups: list[list[SubtitleLine]] = [[lines[0]]]
    for prev, ln in zip(lines, lines[1:]):
        cur = groups[-1]
        if marks:
            new = any(prev.start < m <= ln.start for m in marks)
        else:
            new = ln.start - prev.end >= gap_s or ln.end - cur[0].start > max_len_s
        if new:
            groups.append([ln])
        else:
            cur.append(ln)

    scenes = []
    for i, g in enumerate(groups):
        speakers = list(dict.fromkeys(ln.speaker for ln in g if ln.speaker))
        scenes.append(
            Scene(id=f"s{i:03d}", start=g[0].start, end=g[-1].end, characters_present=speakers, lines=g)
        )
    # Close gaps so every timestamp belongs to a scene.
    for a, b in zip(scenes, scenes[1:]):
        a.end = b.start
    return scenes
