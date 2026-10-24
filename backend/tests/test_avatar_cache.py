from pathlib import Path

from app.routers.avatar import _idle_cache_key


def test_idle_cache_key_separates_characters_and_image_contents(tmp_path: Path):
    rick = tmp_path / "rick" / "face.png"
    morty = tmp_path / "morty" / "face.png"
    rick.parent.mkdir()
    morty.parent.mkdir()
    rick.write_bytes(b"rick portrait")
    morty.write_bytes(b"morty portrait")

    rick_key = _idle_cache_key("rick", None, rick)
    morty_key = _idle_cache_key("morty", None, morty)

    assert rick_key != morty_key
    assert _idle_cache_key("rick", None, rick) == rick_key
    rick.write_bytes(b"new rick portrait")
    assert _idle_cache_key("rick", None, rick) != rick_key
