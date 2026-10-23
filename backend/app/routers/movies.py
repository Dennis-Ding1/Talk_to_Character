from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.context.knowledge import MovieNotFound, list_movies, load_movie
from app.schemas import Character, Movie

router = APIRouter(prefix="/api/movies", tags=["movies"])


def _kb(movie_id: str):
    try:
        return load_movie(movie_id)
    except MovieNotFound:
        raise HTTPException(404, f"movie {movie_id!r} not found")


@router.get("", response_model=list[Movie])
def movies():
    return list_movies()


@router.get("/{movie_id}/characters", response_model=list[Character])
def characters(movie_id: str, t: float | None = None):
    """All characters, or (with ?t=) the ones on screen around t for the pause picker."""
    kb = _kb(movie_id)
    return kb.characters_at(t) if t is not None else list(kb.characters.values())


@router.get("/{movie_id}/video")
def video(movie_id: str):
    kb = _kb(movie_id)
    path = kb.folder / kb.movie.video
    if not path.exists():
        raise HTTPException(404, f"put the video at {path}")
    return FileResponse(path)  # supports Range requests -> seeking works


@router.get("/{movie_id}/subtitles")
def subtitles(movie_id: str):
    kb = _kb(movie_id)
    path = kb.folder / kb.movie.subtitles
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="text/plain; charset=utf-8")


@router.get("/{movie_id}/characters/{character_id}/face")
def face(movie_id: str, character_id: str):
    kb = _kb(movie_id)
    c = kb.characters.get(character_id)
    if not c or not c.face_image:
        raise HTTPException(404)
    path = kb.folder / "characters" / character_id / c.face_image
    if not path.exists():
        raise HTTPException(404, f"missing {path}")
    return FileResponse(path)
