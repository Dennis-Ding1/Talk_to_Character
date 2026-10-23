"""Quick live check of the Boson APIs we depend on. Uses a little credit (< $0.05).

Run from backend/:  python scripts/smoke_boson.py [--face path/to/face.png] [--out out_dir]
"""

import argparse
import asyncio
import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import websockets  # noqa: E402

from app.boson.client import REALTIME_MODEL, REALTIME_URL, BosonClient  # noqa: E402
from app.config import get_settings  # noqa: E402


def ok(name, msg=""):
    print(f"  OK   {name} {msg}")


def fail(name, e):
    print(f"  FAIL {name}: {e}")


async def check_client_secret(c: BosonClient):
    secret = await c.create_client_secret(ttl_s=60)
    assert secret.startswith("bai-eph-"), secret[:8]
    ok("client_secret", "(bai-eph-...)")
    return secret


async def check_realtime_text(secret: str):
    """Opens the socket the way the browser does (ephemeral key subprotocol), text in -> text out."""
    t0 = time.time()
    async with websockets.connect(
        f"{REALTIME_URL}?model={REALTIME_MODEL}",
        subprotocols=["realtime", f"bai-client-secret.{secret}"],
        max_size=None,
    ) as ws:
        await ws.send(json.dumps({"type": "session.update", "session": {
            "model": REALTIME_MODEL,
            "instructions": "You are Alice, a sarcastic retired safecracker. Reply in one short sentence, "
                            "in the same language as the user.",
            "output_modalities": ["text"],
        }}))
        await ws.send(json.dumps({"type": "conversation.item.create", "item": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "你现在在干嘛？"}]}}))
        await ws.send(json.dumps({"type": "response.create"}))
        text, first = [], None
        async for raw in ws:
            ev = json.loads(raw)
            if ev["type"] == "response.output_text.delta":
                first = first or time.time()
                text.append(ev["delta"])
            elif ev["type"] == "response.done":
                break
            elif ev["type"] == "error":
                raise RuntimeError(ev["error"])
    ok("realtime text", f"first token {first - t0:.2f}s -> {''.join(text)!r}")


async def check_realtime_audio(secret: str, out: Path):
    """Text in -> audio out with the default voice; saves the reply as wav."""
    t0 = time.time()
    pcm, first, transcript = bytearray(), None, []
    async with websockets.connect(
        f"{REALTIME_URL}?model={REALTIME_MODEL}",
        subprotocols=["realtime", f"bai-client-secret.{secret}"],
        max_size=None,
    ) as ws:
        await ws.send(json.dumps({"type": "session.update", "session": {
            "model": REALTIME_MODEL,
            "instructions": "Reply in one short sentence.",
            "audio": {"output": {"format": {"type": "audio/pcm", "rate": 24000}, "voice": "default"}},
        }}))
        await ws.send(json.dumps({"type": "conversation.item.create", "item": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "Say hello to the hackathon judges."}]}}))
        await ws.send(json.dumps({"type": "response.create"}))
        async for raw in ws:
            ev = json.loads(raw)
            if ev["type"] == "response.output_audio.delta":
                first = first or time.time()
                pcm += base64.b64decode(ev["delta"])
            elif ev["type"] == "response.output_audio_transcript.delta":
                transcript.append(ev["delta"])
            elif ev["type"] == "response.done":
                break
            elif ev["type"] == "error":
                raise RuntimeError(ev["error"])
    import wave

    path = out / "realtime_reply.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000), w.writeframes(bytes(pcm))
    ok("realtime audio", f"first audio {first - t0:.2f}s, {len(pcm) / 48000:.1f}s audio "
       f"{''.join(transcript)!r} -> {path}")
    return path


async def check_tts(c: BosonClient, out: Path):
    t0 = time.time()
    audio = await c.speech("Now I am become death, the destroyer of worlds.", voice="default")
    path = out / "tts.wav"
    path.write_bytes(audio)
    ok("tts", f"{time.time() - t0:.2f}s, {len(audio)} bytes -> {path}")


async def check_voices(c: BosonClient):
    voices = await c.list_voices()
    ok("list voices", f"{len(voices)} custom voices")


async def check_avatar(c: BosonClient, face: Path, out: Path):
    mime = "image/png" if face.suffix.lower() == ".png" else "image/jpeg"
    ref = f"data:{mime};base64,{base64.b64encode(face.read_bytes()).decode()}"
    body = c.avatar_body(ref, text="Hello. I can only tell you what I know so far.")
    t0, first, n = time.time(), None, 0
    path = out / "avatar.mp4"
    with path.open("wb") as f:
        async for chunk in c.avatar_stream(body):
            first = first or time.time()
            n += len(chunk)
            f.write(chunk)
    ok("avatar stream", f"first bytes {first - t0:.2f}s, total {time.time() - t0:.2f}s, {n} bytes -> {path}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--face", type=Path)
    ap.add_argument("--out", type=Path, default=Path("smoke_out"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if not get_settings().boson_api_key:
        sys.exit("BOSON_API_KEY not set in .env")
    c = BosonClient()
    print("Boson smoke test")

    secret = None
    for name, fn in [
        ("client_secret", lambda: check_client_secret(c)),
        ("voices", lambda: check_voices(c)),
        ("tts", lambda: check_tts(c, args.out)),
    ]:
        try:
            r = await fn()
            if name == "client_secret":
                secret = r
        except Exception as e:  # noqa: BLE001
            fail(name, e)

    for name, fn in [("realtime text", check_realtime_text), ("realtime audio", lambda s: check_realtime_audio(s, args.out))]:
        try:
            # one ephemeral key per connection
            await fn(await c.create_client_secret(ttl_s=60) if secret else None)
        except Exception as e:  # noqa: BLE001
            fail(name, e)

    if args.face:
        try:
            await check_avatar(c, args.face, args.out)
        except Exception as e:  # noqa: BLE001
            fail("avatar", e)
    else:
        print("  SKIP avatar (pass --face path/to/face.png)")


if __name__ == "__main__":
    asyncio.run(main())
