import pytest

from app.context.delivery import realtime_delivery_note, tts_input
from app.schemas import Character, CharacterState


def _character(style: str, profile: str | None = "expressive") -> Character:
    return Character(id="test", name="Test", speech_style=style, delivery_profile=profile)


def test_tts_delivery_uses_allowlisted_character_and_state_controls():
    character = _character("Fast, blunt speech with occasional burps.")
    state = CharacterState(character_id="test", t=10, emotion="Anxious but determined")

    result = tts_input("We need to go. Burp.", character, state)

    assert result.startswith("<|emotion:fear|><|prosody:speed_fast|>")
    assert "<|sfx:burping|>Burp" in result


def test_tts_delivery_strips_untrusted_tags_and_marks_existing_laughter():
    result = tts_input(
        "<|style:shouting|>Haha, very funny.",
        _character("Short, dry sentences."),
    )

    assert "style:shouting" not in result
    assert result.startswith("<|emotion:amusement|><|sfx:laughter|>Haha")


def test_tts_delivery_does_not_invent_sound_effects():
    result = tts_input("That is a terrible idea.", _character("Fast speech with occasional burps."))

    assert "sfx:" not in result
    assert result.endswith("That is a terrible idea.")


def test_tts_delivery_rejects_tag_only_input():
    with pytest.raises(ValueError, match="empty"):
        tts_input("<|style:shouting|>", _character("Fast speech."))


def test_realtime_uses_words_instead_of_tts_control_tags():
    state = CharacterState(character_id="test", t=10, emotion="Surprised and confused")
    note = realtime_delivery_note(_character("Measured, quiet speech."), state)

    assert "surprise" in note
    assert "slower pace" in note
    assert "<|" not in note


def test_subtle_profile_does_not_turn_scene_mood_or_voice_prose_into_global_controls():
    character = _character("Quick speech with understatement.", "subtle")
    state = CharacterState(character_id="test", t=10, emotion="Frustrated, determined")

    assert tts_input("I understand. Tell me what you mean.", character, state) == (
        "I understand. Tell me what you mean."
    )
    assert tts_input("Wait, what?!", character, state).startswith("<|emotion:surprise|>")
    note = realtime_delivery_note(character, state)
    assert "natural" in note
    assert "angry" not in note
    assert "quick pace" not in note


def test_oppenheimer_has_a_tracked_subtle_preset_when_movie_data_is_local_only():
    character = Character(id="oppenheimer", name="J. Robert Oppenheimer", speech_style="Quick, understated.")
    state = CharacterState(character_id="oppenheimer", t=10, emotion="Frustrated, determined")

    assert tts_input("I understand.", character, state) == "I understand."


def test_character_default_emotion_is_allowlisted_and_yields_to_scene_mood():
    rick = Character(
        id="rick", name="Rick", speech_style="Fast speech.",
        delivery_profile="expressive", tts_emotion="enthusiasm",
    )
    assert tts_input("Let's go.", rick).startswith("<|emotion:enthusiasm|><|prosody:speed_fast|>")
    assert tts_input("Wait, what?!", rick).startswith("<|emotion:surprise|><|prosody:speed_fast|>")
    afraid = CharacterState(character_id="rick", t=10, emotion="Scared and uncertain")
    assert tts_input("Let's go.", rick, afraid).startswith("<|emotion:fear|><|prosody:speed_fast|>")
    assert tts_input("Let's go.", _character("Fast speech.")) == "<|prosody:speed_fast|>Let's go."


def test_character_default_emotion_cannot_inject_arbitrary_tts_tags():
    character = Character(id="test", name="Test", tts_emotion="fear|><|style:shouting")

    assert tts_input("Hello.", character) == "Hello."
