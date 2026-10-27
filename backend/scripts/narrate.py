"""Clone your own voice with Higgs TTS 3 and use it to narrate a video.

1. Register your voice (once per API key):
     .venv/Scripts/python.exe scripts/narrate.py register --audio my_voice.m4a \
         --text "Exactly what you said in the recording, word for word."
   The recording: 10-20 s of you talking naturally, in a quiet room, no music. Any format ffmpeg reads
   (m4a, mp3, wav...). The voice id is saved to narration/voice.json.

2. Write the narration, one paragraph per line, in a text file (blank lines and lines starting with
   "#" are skipped, so you can leave notes for yourself). Higgs TTS tags work inline, e.g. "<|emotion:enthusiasm|>Pause any scene..." (see docs.boson.ai, TTS tags).

3. Generate it:
     .venv/Scripts/python.exe scripts/narrate.py say --script narration.txt
   Writes narration/01.wav, 02.wav, ... (one per line, so a single line can be redone with --only 3)
   and narration/all.wav with the lines joined by a short pause.
"""

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings  # noqa: E402

API = "https://api.boson.ai/v1"
OUT = Path.cwd() / "narration"


def headers() -> dict:
    key = get_settings().boson_api_key
    if not key:
        raise SystemExit("BOSON_API_KEY is not set (.env)")
    return {"Authorization": f"Bearer {key}"}


def to_wav(src: Path) -> bytes:
    """Any audio file -> 24 kHz mono 16-bit WAV (what Higgs expects)."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "voice.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                        "-ac", "1", "-ar", "24000", "-sample_fmt", "s16", str(out)], check=True)
        return out.read_bytes()


def wav_seconds(data: bytes) -> float:
    import io
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def register(args) -> None:
    wav = to_wav(Path(args.audio))
    secs = wav_seconds(wav)
    if not 4 <= secs <= 30:
        print(f"warning: the recording is {secs:.1f} s; 10-20 s works best (5-30 s accepted)")
    body = {"ref_audio": base64.b64encode(wav).decode(), "ref_text": args.text.strip(), "title": args.title}
    r = httpx.post(f"{API}/audio/voices", headers=headers(), json=body, timeout=120)
    if r.is_error:
        raise SystemExit(f"{r.status_code}: {r.text[:400]}")
    voice_id = r.json()["voice_id"]
    OUT.mkdir(exist_ok=True)
    (OUT / "voice.json").write_text(json.dumps({"voice_id": voice_id, "title": args.title}, indent=2), encoding="utf-8")
    print(f"registered {voice_id}  ({secs:.1f} s of audio) -> {OUT / 'voice.json'}")


def speak(text: str, voice: str) -> bytes:
    r = httpx.post(f"{API}/audio/speech", headers=headers(), timeout=180,
                   json={"model": "higgs-tts-3", "input": text, "voice": voice, "response_format": "wav"})
    if r.is_error:
        raise SystemExit(f"{r.status_code}: {r.text[:400]}")
    return r.content


def say(args) -> None:
    voice = args.voice or json.loads((OUT / "voice.json").read_text(encoding="utf-8"))["voice_id"]
    # one paragraph per line; blank lines and "# notes" are skipped
    lines = [ln.strip() for ln in Path(args.script).read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    only = {int(x) for x in args.only.split(",")} if args.only else None
    OUT.mkdir(exist_ok=True)
    for i, line in enumerate(lines, 1):
        if only and i not in only:
            continue
        data = speak(line, voice)
        (OUT / f"{i:02d}.wav").write_bytes(data)
        print(f"{i:02d}.wav  {wav_seconds(data):5.1f} s  {line[:70]}")
    # join every line's file (fresh or from an earlier run) with a short pause in between
    parts = [OUT / f"{i:02d}.wav" for i in range(1, len(lines) + 1) if (OUT / f"{i:02d}.wav").exists()]
    with tempfile.TemporaryDirectory() as d:
        silence = Path(d) / "pause.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "anullsrc=r=24000:cl=mono", "-t", str(args.pause), "-sample_fmt", "s16", str(silence)], check=True)
        listing = Path(d) / "list.txt"
        listing.write_text("".join(f"file '{p.resolve().as_posix()}'\nfile '{silence.as_posix()}'\n" for p in parts),
                           encoding="utf-8")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(listing), "-ac", "1", "-ar", "24000", str(OUT / "all.wav")], check=True)
    print(f"all lines -> {OUT / 'all.wav'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register", help="clone your voice from a recording")
    r.add_argument("--audio", required=True)
    r.add_argument("--text", required=True, help="exact words spoken in the recording")
    r.add_argument("--title", default="my-narration-voice")
    s = sub.add_parser("say", help="narrate a script, one paragraph per line")
    s.add_argument("--script", required=True)
    s.add_argument("--voice", help="voice id (default: narration/voice.json)")
    s.add_argument("--only", help="redo just these line numbers, e.g. 2,5")
    s.add_argument("--pause", type=float, default=0.6, help="seconds between lines in all.wav")
    args = ap.parse_args()
    register(args) if args.cmd == "register" else say(args)


if __name__ == "__main__":
    main()
