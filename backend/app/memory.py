"""Conversation history per (movie, character), persisted as JSON so it survives restarts."""

import json
import threading

from app.config import REPO_ROOT
from app.schemas import Turn

_DIR = REPO_ROOT / "data" / "memory"
_lock = threading.Lock()


def _path(movie_id: str, character_id: str, knowledge: str = "present"):
    # separate histories per mode: an omniscient chat must never be replayed into a spoiler-safe one
    return _DIR / f"{movie_id}__{character_id}__{knowledge}.json"


def load(movie_id: str, character_id: str, knowledge: str = "present", at_t: float | None = None) -> list[Turn]:
    """Past turns. In present mode pass at_t: only the conversation from this same pause point is
    replayed. Turns from a later pause could spoil; turns from an earlier one are stale ("the test
    hasn't happened yet" said at 1:30 would make the character repeat it at 2:00, after the test)."""
    p = _path(movie_id, character_id, knowledge)
    if not p.exists():
        return []
    turns = [Turn(**t) for t in json.loads(p.read_text(encoding="utf-8"))]
    return [t for t in turns if at_t is None or abs(t.t - at_t) <= 2.0]


def append(movie_id: str, character_id: str, turn: Turn, knowledge: str = "present") -> None:
    with _lock:
        turns = load(movie_id, character_id, knowledge)
        turns.append(turn)
        _DIR.mkdir(parents=True, exist_ok=True)
        _path(movie_id, character_id, knowledge).write_text(
            json.dumps([t.model_dump() for t in turns], ensure_ascii=False, indent=1), encoding="utf-8"
        )


def clear(movie_id: str, character_id: str) -> None:
    for k in ("present", "omniscient"):
        _path(movie_id, character_id, k).unlink(missing_ok=True)


def as_realtime_items(turns: list[Turn], limit: int = 20) -> list[dict]:
    """Shape for `conversation.item.create` (user -> input_text, assistant -> text)."""
    items = []
    for t in turns[-limit:]:
        ctype = "input_text" if t.role == "user" else "text"
        items.append({"type": "message", "role": t.role, "content": [{"type": ctype, "text": t.text}]})
    return items
