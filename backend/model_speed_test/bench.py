"""Higgs Avatar latency benchmark: text-driven vs audio-driven renders.

Question: to make a talking-head reply appear as soon as possible, should Higgs Avatar get the
reply as TEXT (`input_tts`, Avatar runs Higgs TTS itself) or as finished AUDIO (`input`)?
And if audio, where should it come from: Higgs TTS 3 or Higgs Realtime speaking directly?

Measured (same reference image, voice, size and text in every condition; conditions interleaved
in random order inside each round so server load drifts affect both equally):

  avatar_text   POST /v1/videos/stream with input_tts      (text  -> video)
  avatar_audio  POST /v1/videos/stream with input = wav    (audio -> video)
  tts_full      POST /v1/audio/speech, whole wav           (text  -> audio, Higgs TTS 3)
  realtime      wss /v1/realtime, output_modalities=audio  (text  -> audio, Higgs Realtime)

For every avatar render the fMP4 stream is saved with the arrival time of each network chunk; the
analysis maps each video frame (pts) to when its bytes arrived, which gives
  - time to first frame,
  - "smooth start": the earliest moment playback can begin and never stall
    (max over frames of arrival_time - pts),
  - render speed (seconds of video produced per second of wall time).

Usage (from the backend folder):
  .venv/Scripts/python.exe model_speed_test/bench.py --image face.jpg --trials 5
The API key is read from BOSON_API_KEY or from the .env file given with --env-file.
Results are appended to model_speed_test/results/raw.jsonl (re-runs add more trials).
"""

import argparse
import asyncio
import base64
import io
import json
import os
import random
import subprocess
import tempfile
import time
import uuid
import wave
from pathlib import Path

import httpx
import websockets

API = "https://api.boson.ai/v1"
REALTIME_URL = "wss://api.boson.ai/v1/realtime"
REALTIME_MODEL = "higgs-realtime-1.5-preview"
HERE = Path(__file__).resolve().parent

# Neutral English replies of three lengths (~3 s, ~9 s, ~18 s of speech).
TEXTS = {
    "short": "Hello. I'm glad you came to talk to me today.",
    "medium": ("I've been thinking about that question all morning. The honest answer is that I'm not "
               "sure yet, but I know which way I'm leaning, and I'll tell you why."),
    "long": ("I've been thinking about that question all morning. The honest answer is that I'm not sure "
             "yet, but I know which way I'm leaning. When I was younger I would have said yes without a "
             "second thought. Now I've seen what happens when people rush, and I'd rather take a day, ask "
             "the people I trust, and then decide."),
}


def api_key(env_file: str | None) -> str:
    if os.environ.get("BOSON_API_KEY"):
        return os.environ["BOSON_API_KEY"]
    for path in [env_file, HERE.parent.parent / ".env", HERE.parent / ".env"]:
        if path and Path(path).exists():
            for line in Path(path).read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("BOSON_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("Set BOSON_API_KEY or pass --env-file")


def wav_seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def pcm_to_wav(pcm: bytes, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def video_packets(path: Path) -> list[tuple[float, int]]:
    """(pts seconds, byte offset of the packet's end) for every video packet."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,pos,size",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout
    pk = []
    for line in out.split():
        parts = line.split(",")
        if len(parts) >= 3 and parts[1].isdigit():
            pk.append((float(parts[0]), int(parts[1]) + int(parts[2])))
    return sorted(pk)


def arrival_metrics(arrivals: list[tuple[float, int]], packets: list[tuple[float, int]]) -> dict:
    """Map frames to the wall time their bytes had arrived (arrivals: (t, cumulative bytes))."""
    def arrived(byte_end: int) -> float:
        for t, size in arrivals:
            if size >= byte_end:
                return t
        return arrivals[-1][0]

    frames = [(pts, arrived(end)) for pts, end in packets]
    first_pts = frames[0][0]
    frame_dur = (frames[1][0] - frames[0][0]) if len(frames) > 1 else 1 / 25
    duration = frames[-1][0] - first_pts + frame_dur
    smooth = max(t - (pts - first_pts) for pts, t in frames)  # start here and no frame is late
    def available(sec: float) -> float:  # wall time when `sec` seconds of video were in
        return max((t for pts, t in frames if pts - first_pts <= sec), default=frames[-1][1])
    first_frame = frames[0][1]
    curve = [(round(t, 3), round(pts - first_pts + frame_dur, 3)) for pts, t in frames[:: max(1, len(frames) // 120)]]
    return {
        "video_s": round(duration, 3),
        "first_frame_s": round(first_frame, 3),
        "video_1s_at": round(available(1.0), 3),
        "video_3s_at": round(available(3.0), 3),
        "smooth_start_s": round(smooth, 3),
        "render_speed_x": round(duration / max(1e-6, frames[-1][1] - first_frame), 3),
        "curve": curve,  # (wall seconds, video seconds available) for plotting
    }


async def with_retry(label: str, attempt):
    """Run `attempt()` (returns (status, result)); retry 429s, report how long we waited for them."""
    waited = 0.0
    for k in range(10):
        status, result = await attempt()
        if status != 429:
            return status, result, waited
        pause = min(3 * (k + 1), 20)
        print(f"    {label}: rate limited, retry in {pause}s", flush=True)
        await asyncio.sleep(pause)
        waited += pause
    raise RuntimeError(f"{label}: still rate limited")


async def avatar_render(client: httpx.AsyncClient, key: str, body: dict, label: str) -> dict:
    async def attempt():
        tmp = Path(tempfile.gettempdir()) / f"avatar_bench_{uuid.uuid4().hex}.mp4"
        arrivals: list[tuple[float, int]] = []
        t0 = time.perf_counter()
        async with client.stream("POST", f"{API}/videos/stream", json=body,
                                 headers={"Authorization": f"Bearer {key}"}) as r:
            if r.status_code != 200:
                text = (await r.aread())[:300]
                return r.status_code, text
            total = 0
            with tmp.open("wb") as f:
                async for chunk in r.aiter_bytes():
                    total += len(chunk)
                    arrivals.append((time.perf_counter() - t0, total))
                    f.write(chunk)
        try:
            m = arrival_metrics(arrivals, video_packets(tmp))
        finally:
            tmp.unlink(missing_ok=True)
        m["first_bytes_s"] = round(arrivals[0][0], 3)
        m["total_s"] = round(arrivals[-1][0], 3)
        return 200, m

    status, result, waited = await with_retry(label, attempt)
    if status != 200:
        raise RuntimeError(f"{label}: HTTP {status} {result!r}")
    result["rate_limit_wait_s"] = waited
    return result


async def tts_full(client: httpx.AsyncClient, key: str, text: str, voice: str) -> tuple[dict, bytes]:
    async def attempt():
        t0 = time.perf_counter()
        r = await client.post(f"{API}/audio/speech", headers={"Authorization": f"Bearer {key}"},
                              json={"model": "higgs-tts-3", "input": text, "voice": voice, "response_format": "wav"})
        if r.status_code != 200:
            return r.status_code, r.text[:300]
        return 200, ({"gen_s": round(time.perf_counter() - t0, 3), "audio_s": round(wav_seconds(r.content), 3)}, r.content)

    status, result, waited = await with_retry("tts", attempt)
    if status != 200:
        raise RuntimeError(f"tts: HTTP {status} {result!r}")
    m, data = result
    m["rate_limit_wait_s"] = waited
    return m, data


async def realtime_speak(key: str, text: str, voice: str) -> tuple[dict, bytes]:
    """Higgs Realtime saying `text` with audio output: time to first audio and to the whole reply."""
    async with websockets.connect(f"{REALTIME_URL}?model={REALTIME_MODEL}",
                                  additional_headers={"Authorization": f"Bearer {key}"}, max_size=None) as ws:
        await ws.send(json.dumps({"type": "session.update", "session": {
            "model": REALTIME_MODEL, "output_modalities": ["audio"],
            "instructions": "Read the user's text aloud exactly as written. Say nothing else.",
            "audio": {"input": {"turn_detection": None}, "output": {"voice": voice}}}}))
        await ws.send(json.dumps({"type": "conversation.item.create", "item": {
            "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}}))
        t0 = time.perf_counter()
        await ws.send(json.dumps({"type": "response.create"}))
        pcm = bytearray()
        first = None
        async for raw in ws:
            ev = json.loads(raw)
            if ev["type"] == "response.output_audio.delta":
                first = first or time.perf_counter() - t0
                pcm += base64.b64decode(ev["delta"])
            elif ev["type"] == "response.done":
                break
            elif ev["type"] == "error":
                raise RuntimeError(f"realtime: {ev.get('error')}")
        done = time.perf_counter() - t0
    return {"first_audio_s": round(first or done, 3), "gen_s": round(done, 3),
            "audio_s": round(len(pcm) / 48000, 3)}, bytes(pcm)


def record(out: Path, row: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True, help="portrait photo used as the avatar's face (jpg/png)")
    ap.add_argument("--trials", type=int, default=5, help="rounds per text length")
    ap.add_argument("--lengths", default="short,medium,long")
    ap.add_argument("--voice", default="default", help="Higgs voice (preset or voice_<id>) for every condition")
    ap.add_argument("--size", default="640x640")
    ap.add_argument("--env-file")
    ap.add_argument("--out", default=str(HERE / "results" / "raw.jsonl"))
    args = ap.parse_args()

    key = api_key(args.env_file)
    img = Path(args.image)
    mime = "image/png" if img.suffix.lower() == ".png" else "image/jpeg"
    ref_image = f"data:{mime};base64,{base64.b64encode(img.read_bytes()).decode()}"
    out = Path(args.out)
    run_id = time.strftime("%Y%m%d-%H%M%S")
    lengths = args.lengths.split(",")
    rng = random.Random(run_id)

    async with httpx.AsyncClient(timeout=180) as client:
        # one reference audio per length (Higgs TTS 3, same voice) drives every audio-driven render
        ref_audio = {}
        for name in lengths:
            _, wav = await tts_full(client, key, TEXTS[name], args.voice)
            ref_audio[name] = f"data:audio/wav;base64,{base64.b64encode(wav).decode()}"
            print(f"reference audio {name}: {wav_seconds(wav):.1f} s", flush=True)

        for trial in range(1, args.trials + 1):
            for name in lengths:
                conditions = ["avatar_text", "avatar_audio", "tts_full", "realtime"]
                rng.shuffle(conditions)
                for cond in conditions:
                    base = {"run": run_id, "trial": trial, "length": name, "condition": cond,
                            "chars": len(TEXTS[name]), "voice": args.voice, "size": args.size}
                    try:
                        if cond == "avatar_text":
                            m = await avatar_render(client, key, {
                                "model": "higgs-avatar", "ref_image": ref_image, "size": args.size,
                                "input_tts": {"model": "higgs-tts-3", "input": TEXTS[name], "voice": args.voice}},
                                cond)
                        elif cond == "avatar_audio":
                            m = await avatar_render(client, key, {
                                "model": "higgs-avatar", "ref_image": ref_image, "size": args.size,
                                "input": ref_audio[name]}, cond)
                        elif cond == "tts_full":
                            m, _ = await tts_full(client, key, TEXTS[name], args.voice)
                        else:
                            m, _ = await realtime_speak(key, TEXTS[name], args.voice)
                    except Exception as e:  # keep going; the failure is recorded
                        print(f"  [{trial}] {name:<6} {cond:<12} FAILED {e}", flush=True)
                        record(out, {**base, "error": str(e)[:300]})
                        continue
                    record(out, {**base, **m})
                    brief = {k: v for k, v in m.items() if k != "curve"}
                    print(f"  [{trial}] {name:<6} {cond:<12} {brief}", flush=True)
                    await asyncio.sleep(1.0)  # let the render slot free up between calls
    print(f"done: {out}")


if __name__ == "__main__":
    asyncio.run(main())
