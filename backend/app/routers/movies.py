from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.context.knowledge import MovieNotFound, list_movies, load_movie, resolve
from app.schemas import CharacterAtTime, Movie

router = APIRouter(prefix="/api/movies", tags=["movies"])


def _kb(movie_id: str):
    """The movie's own folder (its video file)."""
    try:
        return load_movie(movie_id)
    except MovieNotFound:
        raise HTTPException(404, f"movie {movie_id!r} not found")


def _frames(movie_id: str, t: float):
    """Where to grab the picture at playback time t: this movie's own video at t (a demo cut needs
    only its own short video, not the full film), and its own folder for the crops."""
    own = _kb(movie_id)
    return own.folder / own.movie.video, t, own.folder / "cache" / "faces"


def _src(movie_id: str, t: float | None = None):
    """Knowledge + time to use: for a demo cut, the full source film at the mapped time."""
    try:
        return resolve(movie_id, t)
    except MovieNotFound:
        raise HTTPException(404, f"movie {movie_id!r} not found")


@router.get("", response_model=list[Movie])
def movies():
    return list_movies()


@router.get("/{movie_id}/characters", response_model=list[CharacterAtTime])
def characters(movie_id: str, t: float | None = None):
    """All characters, or (with ?t=) the ones around t for the pause picker, each with their best
    face from this scene before t (look_url) when the film has a face index."""
    kb, t = _src(movie_id, t)
    if t is None:
        return [CharacterAtTime(**c.model_dump()) for c in kb.characters.values()]
    out = []
    for c in kb.characters_at(t):
        lk = kb.best_look(c.id, t)
        out.append(CharacterAtTime(**c.model_dump(), look_id=lk["id"] if lk else None,
                                   look_url=f"/api/movies/{movie_id}/faces/{lk['id']}.jpg" if lk else None))
    return out


@router.get("/{movie_id}/video")
def video(movie_id: str):
    kb = _kb(movie_id)
    path = kb.folder / kb.movie.video
    if not path.exists():
        raise HTTPException(404, f"put the video at {path}")
    return FileResponse(path)  # supports Range requests -> seeking works


@router.get("/{movie_id}/poster")
def poster(movie_id: str):
    kb = _kb(movie_id)
    path = kb.folder / kb.movie.poster if kb.movie.poster else None
    if path is None or not path.exists():
        raise HTTPException(404, "no poster for this movie")
    return FileResponse(path)


@router.get("/{movie_id}/subtitles")
def subtitles(movie_id: str):
    kb = _kb(movie_id)
    path = kb.folder / kb.movie.subtitles
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="text/plain; charset=utf-8")


@router.get("/{movie_id}/faces")
def faces(movie_id: str, t: float):
    """Faces visible in the few seconds before t, as head-and-shoulders crops (the look *now*)."""
    from app.faces import faces_at

    video_path, t_video, crops_dir = _frames(movie_id, t)
    if not video_path.exists():
        return []
    crops = faces_at(video_path, t_video, crops_dir)
    return [
        {"id": f.id, "url": f"/api/movies/{movie_id}/faces/{f.id}.jpg", "frame_t": f.frame_t, "score": f.score}
        for f in crops
    ]


@router.get("/{movie_id}/frame_faces")
def frame_faces(movie_id: str, t: float):
    """Faces in the exact paused frame, recognised, for click-a-face-to-talk.

    box is [x, y, w, h] normalised to the video frame. For recognised faces, `character` carries the
    character plus their best photo at this moment (look_url) for the avatar; face_url is the crop of
    this very face (fallback)."""
    from app.faces import recognise_frame

    # The frame comes from this movie's own video (for a demo cut: the cut itself, at demo time);
    # who the faces are comes from the full film's face index, and their best look from film time.
    video_path, t_video, crops_dir = _frames(movie_id, t)
    kb, t = _src(movie_id, t)
    if not video_path.exists():
        return []
    animation_profile = kb.folder / "knowledge" / "animation_faces.json"
    faces = recognise_frame(
        video_path,
        t_video,
        kb.folder / "cache" / "face_cores.npz",
        crops_dir,
        animation_profile=animation_profile,
    )
    out = []
    for f in faces:
        c = kb.characters.get(f["character_id"] or "")
        character = None
        if c:
            if animation_profile.exists():
                # Recognition follows the current frame, but Higgs Avatar gets the curated,
                # closed-mouth portrait. A speaking animation frame can bias its resting mouth.
                character = CharacterAtTime(**c.model_dump())
            else:
                lk = kb.best_look(c.id, t)
                character = CharacterAtTime(
                    **c.model_dump(), look_id=lk["id"] if lk else f["face_id"],
                    look_url=f"/api/movies/{movie_id}/faces/{lk['id'] if lk else f['face_id']}.jpg")
        out.append({**f, "face_url": f"/api/movies/{movie_id}/faces/{f['face_id']}.jpg", "character": character})
    return out


@router.get("/{movie_id}/faces/{face_id}.jpg")
def face_crop(movie_id: str, face_id: str):
    kb, _ = _src(movie_id)
    path = face_crop_path(kb, face_id, _kb(movie_id).folder)
    if path is None:
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")


def face_crop_path(kb, face_id: str, own_folder=None):
    """A face picture by id: the film's face-index looks, or a crop grabbed on the fly (in the film's
    folder, or in the demo cut's own folder when it was grabbed from the cut's video)."""
    if not face_id.replace("_", "").isalnum():
        return None
    folders = [kb.folder] + ([own_folder] if own_folder is not None and own_folder != kb.folder else [])
    for folder in folders:
        for sub in ("looks", "faces"):
            path = folder / "cache" / sub / f"{face_id}.jpg"
            if path.exists():
                return path
    return None


@router.get("/{movie_id}/characters/{character_id}/face")
def face(movie_id: str, character_id: str):
    kb, _ = _src(movie_id)
    c = kb.characters.get(character_id)
    if not c or not c.face_image:
        raise HTTPException(404)
    path = kb.folder / "characters" / character_id / c.face_image
    if not path.exists():
        raise HTTPException(404, f"missing {path}")
    return FileResponse(path)
