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


@app.get("/api/health")
def health():
    return {"ok": True, "boson_key": BosonClient().enabled}
