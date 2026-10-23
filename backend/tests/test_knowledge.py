"""Anti-spoiler guarantees, checked against data/movies/demo.

Story: s000 (0-60s) Alice+Bob plan the job; s001 (60-120s) Carol alone reveals she's a cop;
s002 (120-180s) Carol meets Alice.
"""

import pytest
from fastapi.testclient import TestClient

from app.context.knowledge import load_movie
from app.context.persona import build_instructions
from app.main import app
from preprocess.scenes import split_scenes
from app.schemas import SubtitleLine

SECRET = "undercover"


@pytest.fixture(scope="module")
def kb():
    return load_movie("demo")


def test_nothing_after_t(kb):
    ids = [s.id for s in kb.known_scenes("alice", 30)]
    assert ids == ["s000"]
    assert all(ln.start < 30 for s in kb.known_scenes("alice", 30) for ln in s.lines)


def test_in_progress_scene_drops_summary(kb):
    s0 = kb.known_scenes("alice", 30)[0]
    assert s0.summary == "" and s0.key_events == []  # summary covers the future part of the scene


def test_pov_excludes_scenes_character_missed(kb):
    # Alice was never in s001, so she can't know Carol is a cop — even at the end of the movie.
    assert "s001" not in [s.id for s in kb.known_scenes("alice", 999)]
    assert SECRET not in build_instructions(kb, "alice", 999).lower()


def test_carol_knows_her_own_secret(kb):
    assert SECRET in build_instructions(kb, "carol", 130).lower()


def test_state_checkpoint_by_time(kb):
    assert kb.state_at("alice", 59) is None
    assert "Meridian" in kb.state_at("alice", 100).goals
    assert "carol" in kb.state_at("alice", 999).relationships


def test_recall_tool_respects_t():
    client = TestClient(app)
    r = client.post(
        "/api/tools/recall_scene",
        json={"movie_id": "demo", "character_id": "alice", "t": 999, "arguments": {"query": "raid captain police"}},
    )
    assert r.status_code == 200
    assert "captain" not in r.json()["result"].lower()


def test_session_endpoint_without_key(monkeypatch):
    from app.boson.client import BosonClient
    from app.routers import session as session_router

    monkeypatch.setattr(session_router, "BosonClient", lambda: BosonClient(api_key=""))
    client = TestClient(app)
    r = client.post("/api/session", json={"movie_id": "demo", "character_id": "bob", "t": 50})
    assert r.status_code == 200
    body = r.json()
    assert body["session"]["model"] == "higgs-realtime"
    assert "Bob" in body["session"]["instructions"]


def test_split_scenes_gap():
    lines = [SubtitleLine(start=a, end=a + 2, text="x") for a in (0, 3, 30, 33)]
    scenes = split_scenes(lines, gap_s=8)
    assert [len(s.lines) for s in scenes] == [2, 2]
