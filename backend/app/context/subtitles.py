"""SRT parsing shared by the API (fallback when no knowledge/ exists) and the preprocess CLI.

Speaker convention (optional): a line starting with "NAME:" or "[NAME]" sets `speaker`
to the matching character id/name/alias.
"""

import re
from pathlib import Path

import pysrt

from app.schemas import Character, SubtitleLine

_SPEAKER_RE = re.compile(r"^\s*(?:\[(?P<a>[^\]]{1,40})\]|(?P<b>[^:：\n]{1,40})[:：])\s*(?P<text>.*)$", re.S)


def _speaker_lookup(characters: list[Character]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for c in characters:
        for name in [c.id, c.name, *c.aliases]:
            lookup[name.strip().lower()] = c.id
    return lookup


def parse_srt(path: Path, characters: list[Character] | None = None) -> list[SubtitleLine]:
    lookup = _speaker_lookup(characters or [])
    out: list[SubtitleLine] = []
    for item in pysrt.open(str(path), encoding="utf-8"):
        text = item.text.replace("\n", " ").strip()
        speaker = None
        m = _SPEAKER_RE.match(text)
        if m:
            name = (m.group("a") or m.group("b") or "").strip().lower()
            if name in lookup:
                speaker = lookup[name]
                text = m.group("text").strip()
        out.append(
            SubtitleLine(
                start=item.start.ordinal / 1000,
                end=item.end.ordinal / 1000,
                text=text,
                speaker=speaker,
            )
        )
    return out
