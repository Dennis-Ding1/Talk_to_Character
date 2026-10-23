"""Non-linear films (Oppenheimer-style): screen order != story order."""

import json

import pytest

from app.context.knowledge import MovieKnowledge
from app.context.persona import build_instructions


def _scene(id, start, end, year, thread, present, summary):
    return {"id": id, "start": start, "end": end, "story_year": year, "thread": thread,
            "characters_present": present, "summary": summary, "slug": f"INT. {id.upper()} -- DAY",
            "lines": [{"start": start + 1, "end": start + 2, "text": summary, "speaker": present[0]}]}


@pytest.fixture
def kb(tmp_path):
    (tmp_path / "movie.json").write_text(json.dumps({"id": "nl", "title": "NL"}))
    (tmp_path / "characters.json").write_text(json.dumps([
        {"id": "opp", "name": "Opp"}, {"id": "kitty", "name": "Kitty"}]))
    scenes = [
        # screen order:        story year
        _scene("hearing", 0, 100, 1954.3, "hearing_1954", ["opp"], "Opp is interrogated at the HEARING."),
        _scene("cambridge", 100, 200, 1926.0, "past", ["opp"], "Opp poisons an APPLE at Cambridge."),
        _scene("party", 200, 300, 1939.3, "past", ["opp", "kitty"], "Opp meets Kitty at a PARTY."),
        _scene("trinity", 300, 400, 1945.5, "past", ["opp"], "The TRINITY test succeeds."),
        _scene("hearing2", 400, 500, 1954.3, "hearing_1954", ["opp", "kitty"], "Kitty TESTIFIES."),
    ]
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "scenes.json").write_text(json.dumps(scenes))
    (tmp_path / "knowledge" / "character_states.json").write_text(json.dumps([
        {"character_id": "opp", "t": 200, "scene_id": "cambridge", "stance": "STANCE_1926"},
        {"character_id": "opp", "t": 300, "scene_id": "party", "stance": "STANCE_1939"},
        {"character_id": "opp", "t": 400, "scene_id": "trinity", "stance": "STANCE_1945"},
    ]))
    return MovieKnowledge(tmp_path)


def ids(scenes):
    return [s.id for s in scenes]


def test_flashback_cannot_remember_later_story_events_seen_earlier(kb):
    # paused in 1939 party; the 1954 hearing was already on screen but is in his future
    known = ids(kb.known_scenes("opp", 250))
    assert "hearing" not in known
    assert known == ["cambridge", "party"]
    assert "HEARING" not in build_instructions(kb, "opp", 250)


def test_frame_story_remembers_past_seen_so_far(kb):
    # paused in the second hearing (1954): knows everything seen so far, in story order
    assert ids(kb.known_scenes("opp", 450)) == ["cambridge", "party", "trinity", "hearing", "hearing2"]


def test_not_yet_seen_is_unknown_even_if_earlier_in_story(kb):
    # paused at the start of cambridge (screen 150): trinity (1945) not on screen yet
    assert "trinity" not in ids(kb.known_scenes("opp", 350 - 200))


def test_states_follow_story_time_not_screen_time(kb):
    assert kb.state_at("opp", 250) .stance == "STANCE_1926"  # party still in progress -> last finished
    assert kb.state_at("opp", 350).stance == "STANCE_1939"
    assert kb.state_at("opp", 450).stance == "STANCE_1945"


def test_pov_in_nonlinear(kb):
    assert ids(kb.known_scenes("kitty", 450)) == ["party", "hearing2"]
