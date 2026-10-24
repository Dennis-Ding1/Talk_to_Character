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
        _scene("princeton", 500, 600, 1954.2, "past", ["opp", "kitty"], "Opp and Kitty at PRINCETON."),
        _scene("hearing3", 600, 700, 1954.3, "hearing_1954", ["opp"], "The board DECIDES."),
    ]
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "scenes.json").write_text(json.dumps(scenes))
    (tmp_path / "knowledge" / "character_states.json").write_text(json.dumps([
        {"character_id": "opp", "t": 200, "scene_id": "cambridge", "stance": "STANCE_1926"},
        {"character_id": "opp", "t": 300, "scene_id": "party", "stance": "STANCE_1939"},
        {"character_id": "opp", "t": 400, "scene_id": "trinity", "stance": "STANCE_1945"},
    ]))
    (tmp_path / "knowledge" / "looks.json").write_text(json.dumps([
        {"id": "cam_opp", "scene_id": "cambridge", "character_id": "opp", "t": 150, "q": 0.5},
        {"id": "party_opp_early", "scene_id": "party", "character_id": "opp", "t": 220, "q": 0.6},
        {"id": "party_opp_late", "scene_id": "party", "character_id": "opp", "t": 290, "q": 0.9},
        {"id": "party_kitty", "scene_id": "party", "character_id": "kitty", "t": 230, "q": 0.8},
    ]))
    kb = MovieKnowledge(tmp_path)
    kb.anchor_flash_forwards = True  # these tests cover the anchoring rule itself
    return kb


def ids(scenes):
    return [s.id for s in scenes]


def test_flashback_cannot_remember_later_story_events_seen_earlier(kb):
    # paused in 1939 party; the 1954 hearing was already on screen but is in his future
    known = ids(kb.known_scenes("opp", 250))
    assert "hearing" not in known
    assert known == ["cambridge", "party"]
    assert "HEARING" not in build_instructions(kb, "opp", 250)


def test_flash_forward_ahead_of_viewer_is_anchored_at_viewer_progress(kb):
    # paused in the 2nd hearing (1954) but the viewer has only followed the main story to 1945:
    # talk to the 1945 Opp, who can't spoil what happens between 1945 and 1954
    assert kb.is_anchored(450)
    assert kb.now_year(450) == 1945.5
    assert ids(kb.known_scenes("opp", 450)) == ["cambridge", "party", "trinity"]
    assert "TESTIFIES" not in build_instructions(kb, "opp", 450)


def test_opening_flash_forward_with_nothing_seen(kb):
    # nothing of the main story seen: speak from where the main story begins
    assert kb.is_anchored(50)
    assert kb.now_year(50) == 1926.0
    assert ids(kb.known_scenes("opp", 50)) == []


def test_frame_story_caught_up_is_not_anchored(kb):
    # the main story has reached 1954 by now, so the 1954 hearing is no longer ahead of the viewer
    assert not kb.is_anchored(650)
    assert kb.now_year(650) == 1954.3
    assert ids(kb.known_scenes("opp", 650)) == [
        "cambridge", "party", "trinity", "princeton", "hearing", "hearing2", "hearing3"]


def test_not_yet_seen_is_unknown_even_if_earlier_in_story(kb):
    # paused at the start of cambridge (screen 150): trinity (1945) not on screen yet
    assert "trinity" not in ids(kb.known_scenes("opp", 350 - 200))


def test_states_follow_story_time_not_screen_time(kb):
    assert kb.state_at("opp", 250) .stance == "STANCE_1926"  # party still in progress -> last finished
    assert kb.state_at("opp", 350).stance == "STANCE_1939"
    assert kb.state_at("opp", 450).stance == "STANCE_1945"  # anchored at 1945


def test_pov_in_nonlinear(kb):
    assert ids(kb.known_scenes("kitty", 650)) == ["party", "princeton", "hearing2"]


def test_omniscient_knows_whole_story(kb):
    txt = build_instructions(kb, "opp", 150, "omniscient")
    for secret in ("HEARING", "TRINITY", "TESTIFIES", "DECIDES"):
        assert secret in txt
    assert ids(kb.all_scenes_of("kitty")) == ["party", "princeton", "hearing2"]
    assert kb.final_state("opp").stance == "STANCE_1945"  # latest per-scene state in story order


def test_present_mode_history_never_replays_later_turns(tmp_path, monkeypatch):
    from app import memory
    from app.schemas import Turn

    monkeypatch.setattr(memory, "_DIR", tmp_path)
    memory.append("m", "opp", Turn(role="user", text="early question", t=100))
    memory.append("m", "opp", Turn(role="assistant", text="the bomb worked", t=7000))
    memory.append("m", "opp", Turn(role="assistant", text="what-if answer", t=50), "omniscient")
    memory.append("m", "opp", Turn(role="assistant", text="same pause", t=2700.4))
    # only the conversation from this very pause point: later turns spoil, earlier ones are stale
    assert [t.text for t in memory.load("m", "opp", "present", at_t=2700)] == ["same pause"]
    assert [t.text for t in memory.load("m", "opp", "omniscient")] == ["what-if answer"]


def test_best_look_is_from_this_scene_and_never_after_the_pause(kb):
    assert kb.best_look("opp", 250)["id"] == "party_opp_early"   # the sharper one at 290 is in the future
    assert kb.best_look("opp", 295)["id"] == "party_opp_late"
    assert kb.best_look("opp", 210)["id"] == "cam_opp"           # none yet in this scene -> earlier scene
    assert kb.best_look("kitty", 210) is None


def test_picker_lists_faces_seen_in_this_scene_first(kb):
    assert [c.id for c in kb.characters_at(240)][:2] == ["kitty", "opp"]  # by best shot quality


def test_demo_cut_maps_back_to_source_time():
    from app.context.knowledge import to_source_time
    from app.schemas import DemoSegment, Movie

    m = Movie(id="cut", title="cut", source="full", segments=[
        DemoSegment(key="a", title="A", src_start=100, src_end=160, start=0, duration=60),
        DemoSegment(key="b", title="B", src_start=900, src_end=930, start=60, duration=30),
    ])
    assert to_source_time(m, 10) == 110
    assert to_source_time(m, 60) == 900          # first frame of the second clip
    assert to_source_time(m, 75) == 915
    assert abs(to_source_time(m, 95) - 929.99) < 1e-6  # past the end: clamp to the last clip
