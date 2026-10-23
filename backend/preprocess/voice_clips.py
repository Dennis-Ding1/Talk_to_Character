"""Reference voice for cloning: cut the clip, strip music (demucs), transcribe (faster-whisper),
register with Higgs (POST /v1/audio/voices). Higgs wants 5-30 s of clean single-speaker speech."""

import asyncio
import base64
import shutil
import subprocess
import sys
from pathlib import Path

from app.boson.client import BosonClient


def cut_clip(video: Path, start: float, end: float, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-to", str(end), "-i", str(video),
         "-vn", "-ac", "1", "-ar", "24000", str(out)],
        check=True,
    )
    return out


def separate_vocals(wav: Path) -> Path:
    """Returns the vocals-only stem; falls back to the input if demucs isn't installed."""
    if shutil.which("demucs") is None and not _has_module("demucs"):
        print("  demucs not installed -> using raw clip (pip install -e '.[preprocess]')")
        return wav
    out_dir = wav.parent / "separated"
    subprocess.run(
        [sys.executable, "-m", "demucs", "--two-stems", "vocals", "-o", str(out_dir), str(wav)],
        check=True,
    )
    vocals = next(out_dir.rglob("vocals.wav"))
    final = wav.with_name("voice_ref.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vocals), "-ac", "1", "-ar", "24000", str(final)], check=True)
    return final


def transcribe(wav: Path, language: str | None = None) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  faster-whisper not installed -> no ref_text (fill voice_ref_text by hand)")
        return ""
    model = WhisperModel("small", device="auto", compute_type="auto")
    segments, _ = model.transcribe(str(wav), language=language)
    return " ".join(s.text.strip() for s in segments)


def register_voice(wav: Path, ref_text: str | None, title: str) -> str:
    b64 = base64.b64encode(wav.read_bytes()).decode()
    return asyncio.run(BosonClient().create_voice(b64, ref_text or None, title))


def _has_module(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None
