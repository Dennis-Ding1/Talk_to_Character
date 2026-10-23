"""Find a clean reference clip for each character automatically from the speaker-attributed scenes:
a run of consecutive lines by that character only, nobody else talking just before/after,
6-20 s long (Higgs wants 5-30 s)."""

from app.schemas import Scene


def find_voice_clips(scenes: list[Scene], character_id: str, min_s: float = 6.0, max_s: float = 20.0,
                     target_s: float = 12.0, top: int = 3) -> list[tuple[float, float, str]]:
    """Returns up to `top` candidates (start, end, subtitle text), best first."""
    lines = [ln for s in scenes for ln in s.lines]
    cands: list[tuple[float, float, float, str]] = []
    i = 0
    while i < len(lines):
        if lines[i].speaker != character_id:
            i += 1
            continue
        j = i
        while (j + 1 < len(lines) and lines[j + 1].speaker == character_id
               and lines[j + 1].start - lines[j].end < 1.5 and lines[j + 1].end - lines[i].start <= max_s):
            j += 1
        start, end = lines[i].start - 0.15, lines[j].end + 0.15
        dur = end - start
        before_ok = i == 0 or lines[i - 1].end < start - 0.3
        after_ok = j + 1 >= len(lines) or lines[j + 1].start > end + 0.3
        if min_s <= dur <= max_s and before_ok and after_ok:
            text = " ".join(ln.text for ln in lines[i: j + 1])
            words_per_s = len(text.split()) / dur  # dense speech = less silence/music in the clip
            score = -abs(dur - target_s) / target_s + min(words_per_s / 2.5, 1.0)
            cands.append((score, start, end, text))
        i = j + 1
    cands.sort(key=lambda c: -c[0])
    return [(round(s, 2), round(e, 2), t) for _, s, e, t in cands[:top]]
