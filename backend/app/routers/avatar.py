"""Proxies Higgs Avatar (fragmented MP4) so the API key stays server-side.

Boson allows one avatar render at a time per key (a second concurrent request gets 429), so every
render goes through one queue here, with a retry on rate limits.
"""

import asyncio
import base64
import hashlib
import mimetypes
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.boson.client import BosonClient, BosonError
from app.context.delivery import tts_input
from app.context.knowledge import MovieNotFound, resolve
from app.routers.movies import face_crop_path
from app.schemas import AvatarRequest

router = APIRouter(prefix="/api/avatar", tags=["avatar"])

_render_slot = asyncio.Semaphore(1)  # one Higgs Avatar render at a time (account limit)
_idle_locks: dict[str, asyncio.Lock] = {}


def _data_uri(path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _resolve_face(movie_id: str, character_id: str, face_id: str | None):
    try:
        kb, _ = resolve(movie_id)  # demo cut: faces and voices live with the full film
        c = kb.character(character_id)
    except (MovieNotFound, KeyError):
        raise HTTPException(404, "movie or character not found")
    # Prefer the face grabbed at the pause point (the character's look right now), else the portrait.
    face_path = face_crop_path(kb, face_id) if face_id else None
    if face_path is None and c.face_image:
        face_path = kb.folder / "characters" / c.id / c.face_image
    if face_path is None or not face_path.exists():
        raise HTTPException(400, f"no face for {c.id}: pick a face at the pause point or set face_image")
    return kb, c, face_path


async def _open_stream(client: BosonClient, body: dict, attempts: int = 4):
    """Start a render (the caller holds the render slot); retry on 429. Returns (first_chunk, stream)."""
    for k in range(attempts):
        stream = client.avatar_stream(body)
        try:
            return await anext(stream), stream
        except BosonError as e:
            if "429" in str(e) and k < attempts - 1:
                await asyncio.sleep(1.5 * (k + 1))
                continue
            raise HTTPException(502, str(e))
        except StopAsyncIteration:
            raise HTTPException(502, "empty avatar stream")
    raise HTTPException(502, "avatar render failed")


@router.post("/stream")
async def avatar_stream(req: AvatarRequest, request: Request):
    _kb, c, face_path = _resolve_face(req.movie_id, req.character_id, req.face_id)
    try:
        state_kb, state_t = resolve(req.movie_id, req.t)
        state = state_kb.state_at(req.character_id, state_t)
    except (MovieNotFound, KeyError):
        state = None
    client = BosonClient()
    if not client.enabled:
        raise HTTPException(503, "BOSON_API_KEY not configured")
    ref_image = _data_uri(face_path)
    try:
        if req.text:
            body = client.avatar_body(
                ref_image,
                text=tts_input(req.text, c, state),
                voice=c.voice_id,
                size=req.size,
            )
        elif req.audio_b64:
            body = client.avatar_body(ref_image, audio=f"data:audio/wav;base64,{req.audio_b64}", size=req.size)
        else:
            raise HTTPException(400, "need text or audio_b64")
    except ValueError as e:
        raise HTTPException(400, str(e))

    await _render_slot.acquire()  # released when the stream is fully sent (or fails)
    if await request.is_disconnected():  # superseded while waiting in the queue: don't pay for it
        _render_slot.release()
        raise HTTPException(499, "client went away")
    try:
        first, stream = await _open_stream(client, body)
    except BaseException:
        _render_slot.release()
        raise

    async def body_iter():
        try:
            yield first
            async for chunk in stream:
                yield chunk
        finally:
            # Browser hung up (superseded reply) or done: close the upstream connection right away.
            # Boson frees its one-render-at-a-time slot as soon as we disconnect (measured), so the
            # next reply can start rendering immediately.
            try:
                await asyncio.shield(stream.aclose())
            except BaseException:
                pass
            _render_slot.release()

    return StreamingResponse(body_iter(), media_type="video/mp4")


def _silence_wav(path: Path, seconds: float = 5.0) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", str(seconds), "-c:a", "pcm_s16le", str(path)], check=True)


IDLE_SECONDS = 8.0
IDLE_FADE = 1.0


def _duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def _idle_cache_key(character_id: str, face_id: str | None, face_path: Path) -> str:
    """Stable per-character/per-image key; portraits in different folders are often both face.png."""
    safe_character = re.sub(r"[^a-zA-Z0-9_-]", "_", character_id)[:40] or "character"
    digest = hashlib.sha256()
    digest.update(character_id.encode())
    digest.update(b"\0")
    digest.update((face_id or "portrait").encode())
    digest.update(b"\0")
    digest.update(face_path.read_bytes())
    return f"{safe_character}.{digest.hexdigest()[:16]}"


@router.get("/idle")
async def avatar_idle(movie_id: str, character_id: str, face_id: str | None = None):
    """A seamlessly looping 'listening' clip for this face: Higgs Avatar driven by silence (blinks,
    small head motion, mouth closed). Everything plays forwards; the loop seam is hidden by
    cross-fading the clip's end into its own beginning (a reversed boomerang looked robotic).
    Rendered once per face and cached; shown under the talking clips so the avatar is never a still."""
    kb, _c, face_path = _resolve_face(movie_id, character_id, face_id)
    out_dir = kb.folder / "cache" / "idle"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_key = _idle_cache_key(character_id, face_id, face_path)
    out = out_dir / f"{cache_key}.v3.mp4"
    if out.exists():
        return FileResponse(out, media_type="video/mp4")

    lock = _idle_locks.setdefault(str(out), asyncio.Lock())
    async with lock:
        if not out.exists():
            client = BosonClient()
            if not client.enabled:
                raise HTTPException(503, "BOSON_API_KEY not configured")
            silence = out_dir / f"_silence_{IDLE_SECONDS:.0f}s.wav"
            if not silence.exists():
                _silence_wav(silence, IDLE_SECONDS)
            body = client.avatar_body(_data_uri(face_path), audio=_data_uri(silence), size="640x640")
            raw = out_dir / f"{cache_key}.raw.mp4"
            async with _render_slot:
                first, stream = await _open_stream(client, body)
                with raw.open("wb") as f:
                    f.write(first)
                    async for chunk in stream:
                        f.write(chunk)
            # forward-only seamless loop: A = clip[F:], B = clip[:F]; cross-fade A's tail into B.
            # The output starts at clip time F and ends at clip time F, so looping it has no jump.
            # (The clip is read twice: splitting one input into two trims deadlocks ffmpeg.)
            length = _duration(raw)
            f = IDLE_FADE
            norm = "setpts=PTS-STARTPTS,fps=24,format=yuv420p,settb=AVTB"
            graph = (f"[0:v]trim=start={f},{norm}[A];[1:v]trim=end={f},{norm}[B];"
                     f"[A][B]xfade=transition=fade:duration={f}:offset={length - 2 * f:.3f}[v]")
            tmp = out.with_suffix(".tmp.mp4")
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-i", str(raw),
                 "-filter_complex", graph, "-map", "[v]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-crf", "20", "-preset", "veryfast", "-movflags", "+faststart", str(tmp)], capture_output=True)
            raw.unlink(missing_ok=True)
            if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
                tmp.unlink(missing_ok=True)  # never cache a broken loop
                raise HTTPException(500, f"idle loop encode failed: {r.stderr[-300:]!r}")
            tmp.replace(out)
    return FileResponse(out, media_type="video/mp4")
