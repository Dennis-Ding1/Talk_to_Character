from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.boson.client import BosonClient
from app.config import get_settings
from app.routers import avatar, movies, session, speech, tools

app = FastAPI(title="Talk to Character")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(movies.router)
app.include_router(session.router)
app.include_router(tools.router)
app.include_router(avatar.router)
app.include_router(speech.router)


@app.on_event("startup")
def _warm_up() -> None:
    """Load the memory search once at startup: the first question otherwise pays ~1 s for it."""
    from app.context.knowledge import MovieNotFound, resolve
    from app.context.persona import question_notes

    for movie_id in ("oppenheimer_demo", "oppenheimer", "demo"):
        try:
            kb, t = resolve(movie_id, 60.0)
        except (MovieNotFound, FileNotFoundError):
            continue
        if kb.characters:
            question_notes(kb, next(iter(kb.characters)), t, "warm up the memory search")
        break


@app.get("/api/health")
def health():
    return {"ok": True, "boson_key": BosonClient().enabled}
