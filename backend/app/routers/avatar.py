"""Proxies Higgs Avatar streaming (fragmented MP4) so the API key stays server-side."""

import base64
import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.boson.client import BosonClient, BosonError
from app.context.knowledge import MovieNotFound, load_movie
from app.routers.movies import face_crop_path
from app.schemas import AvatarRequest

router = APIRouter(prefix="/api/avatar", tags=["avatar"])


def _data_uri(path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


@router.post("/stream")
async def avatar_stream(req: AvatarRequest):
    try:
        kb = load_movie(req.movie_id)
        c = kb.character(req.character_id)
    except (MovieNotFound, KeyError):
        raise HTTPException(404, "movie or character not found")
    # Prefer the face grabbed at the pause point (the character's look right now), else the portrait.
    face_path = face_crop_path(kb, req.face_id) if req.face_id else None
    if face_path is None and c.face_image:
        face_path = kb.folder / "characters" / c.id / c.face_image
    if face_path is None or not face_path.exists():
        raise HTTPException(400, f"no face for {c.id}: pick a face at the pause point or set face_image")

    client = BosonClient()
    if not client.enabled:
        raise HTTPException(503, "BOSON_API_KEY not configured")

    ref_image = _data_uri(face_path)
    try:
        if req.text:
            body = client.avatar_body(ref_image, text=req.text, voice=c.voice_id, size=req.size)
        elif req.audio_b64:
            body = client.avatar_body(ref_image, audio=f"data:audio/wav;base64,{req.audio_b64}", size=req.size)
        else:
            raise HTTPException(400, "need text or audio_b64")
    except ValueError as e:
        raise HTTPException(400, str(e))

    stream = client.avatar_stream(body)
    try:
        first = await anext(stream)  # surface API errors as HTTP errors, not a broken stream
    except BosonError as e:
        raise HTTPException(502, str(e))
    except StopAsyncIteration:
        raise HTTPException(502, "empty avatar stream")

    async def body_iter():
        yield first
        async for chunk in stream:
            yield chunk

    return StreamingResponse(body_iter(), media_type="video/mp4")
