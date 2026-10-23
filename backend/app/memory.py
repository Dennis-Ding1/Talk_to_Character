"""Conversation history per (movie, character), persisted as JSON so it survives restarts."""

import json
import threading

from app.config import REPO_ROOT
from app.schemas import Turn

_DIR = REPO_ROOT / "data" / "memory"
_lock = threading.Lock()


def _path(movie_id: str, character_id: str):
    return _DIR / f"{movie_id}__{character_id}.json"


def load(movie_id: str, character_id: str) -> list[Turn]:
    p = _path(movie_id, character_id)
    if not p.exists():
        return []
    return [Turn(**t) for t in json.loads(p.read_text(encoding="utf-8"))]


def append(movie_id: str, character_id: str, turn: Turn) -> None:
    with _lock:
        turns = load(movie_id, character_id)
        turns.append(turn)
        _DIR.mkdir(parents=True, exist_ok=True)
        _path(movie_id, character_id).write_text(
            json.dumps([t.model_dump() for t in turns], ensure_ascii=False, indent=1), encoding="utf-8"
        )


def clear(movie_id: str, character_id: str) -> None:
    _path(movie_id, character_id).unlink(missing_ok=True)


def as_realtime_items(turns: list[Turn], limit: int = 20) -> list[dict]:
    """Shape for `conversation.item.create` (user -> input_text, assistant -> text)."""
    items = []
    for t in turns[-limit:]:
        ctype = "input_text" if t.role == "user" else "text"
        items.append({"type": "message", "role": t.role, "content": [{"type": ctype, "text": t.text}]})
    return items
