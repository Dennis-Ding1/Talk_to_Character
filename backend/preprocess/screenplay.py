"""Parse a standard-format screenplay PDF into scenes with speaker-attributed dialogue.

Relies on `pdftotext -layout` (poppler) which keeps the indentation that distinguishes
sluglines (col 0, INT./EXT.), character cues (deep indent, UPPERCASE) and dialogue (mid indent).
"""

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SLUG_RE = re.compile(r"^\s{0,6}((?:INT|EXT|INT\./EXT|EXT\./INT|I/E)\.?\s.*)$")
CUE_RE = re.compile(
    r"^(?P<indent>\s{12,})(?P<name>[A-Z][A-Z0-9 .'\-]{1,40}?)\s*(?P<ext>(?:\((?:V\.O\.|O\.S\.|O\.C\.|CONT'D|CONT’D|ON PHONE|ON RADIO|PRE-LAP)\)\s*)*)$"
)
PAGE_HEADER_RE = re.compile(r"FINAL Shooting Script|^\s*\d+\.\s*$")
NOISE_RE = re.compile(r"^\s*\((?:CONTINUED|MORE)\)\s*$|^\s*(?:CUT TO|SMASH CUT TO|FADE (?:IN|OUT|TO BLACK)|DISSOLVE TO)[:.]?\s*$")
PAREN_RE = re.compile(r"^\s*\(.*\)?\s*$")
NOT_NAMES = {"CUT TO", "SUPER TITLE", "INSERT CUT", "CLOSE", "THE END", "CONTINUED", "MORE", "BLACK", "SILENCE"}


@dataclass
class ScriptLine:
    speaker: str
    text: str
    vo: bool = False  # voice-over / off-screen: speaker not necessarily present


@dataclass
class ScriptScene:
    index: int
    slug: str
    timeline: str  # "colour" | "bw"
    lines: list[ScriptLine] = field(default_factory=list)
    action: list[str] = field(default_factory=list)
    # the scene in reading order: ("action", paragraph text) and ("line", index into `lines`).
    # Lets us time each action paragraph between the dialogue lines around it.
    elements: list[tuple[str, object]] = field(default_factory=list)


def pdf_to_text(pdf: Path) -> str:
    if shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"], capture_output=True, check=True)
        return out.stdout.decode("utf-8", errors="replace")
    from pypdf import PdfReader  # fallback (pip install pypdf)

    return "\n".join(p.extract_text(extraction_mode="layout") for p in PdfReader(str(pdf)).pages)


def _timeline_from_slug(slug: str, current: str) -> str:
    s = slug.upper()
    if "B&W" in s or "BLACK-AND-WHITE" in s or "BLACK AND WHITE" in s:
        return "bw"
    if "COLOUR" in s or "COLOR" in s:
        return "colour"
    return current


def parse_screenplay(text: str) -> list[ScriptScene]:
    scenes: list[ScriptScene] = []
    timeline = "colour"
    cur: ScriptScene | None = None
    speaker: str | None = None
    vo = False
    buf: list[str] = []
    para: list[str] = []

    def flush():
        nonlocal speaker, buf
        if cur is not None and speaker and buf:
            cur.lines.append(ScriptLine(speaker, " ".join(buf), vo))
            cur.elements.append(("line", len(cur.lines) - 1))
        speaker, buf = None, []

    def flush_para():
        nonlocal para
        if cur is not None and para:
            cur.elements.append(("action", " ".join(para)))
        para = []

    for raw in text.splitlines():
        line = raw.rstrip()
        if PAGE_HEADER_RE.search(line) or NOISE_RE.match(line):
            continue
        if not line.strip():
            if speaker is None:
                flush_para()  # a blank line ends an action paragraph (inside speech it means nothing)
            continue

        m = SLUG_RE.match(line)
        if m:
            flush()
            flush_para()
            slug = re.sub(r"\s+", " ", m.group(1)).strip()
            timeline = _timeline_from_slug(slug, timeline)
            cur = ScriptScene(index=len(scenes), slug=slug, timeline=timeline)
            scenes.append(cur)
            continue
        if cur is None:
            cur = ScriptScene(index=0, slug="OPENING", timeline=timeline)
            scenes.append(cur)

        c = CUE_RE.match(line)
        if c and c.group("name").strip() not in NOT_NAMES and not line.strip().endswith(":"):
            flush()
            flush_para()
            speaker = c.group("name").strip()
            vo = "V.O." in c.group("ext") or "O.S." in c.group("ext")
            continue

        indent = len(line) - len(line.lstrip())
        if speaker and indent >= 6:
            if PAREN_RE.match(line) and line.strip().startswith("("):
                continue  # (beat), (to Kitty) ...
            buf.append(line.strip())
        else:
            flush()
            cur.action.append(line.strip())
            para.append(line.strip())
    flush()
    flush_para()
    return scenes


def load_screenplay(pdf: Path) -> list[ScriptScene]:
    return parse_screenplay(pdf_to_text(pdf))
