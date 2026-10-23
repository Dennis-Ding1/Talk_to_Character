"""Loads a movie's knowledge and filters it by playback time t and the character's point of view.

This is the anti-spoiler core: nothing after t, and nothing from scenes the character
wasn't in, ever leaves this module. Everything downstream (prompt, tools) goes through it.
"""

import json
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.context.subtitles import parse_srt
from app.schemas import Character, CharacterState, Movie, Scene, SubtitleLine


class MovieNotFound(KeyError):
    pass


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class MovieKnowledge:
    def __init__(self, folder: Path):
        self.folder = folder
        meta = _read_json(folder / "movie.json", None)
        if meta is None:
            raise MovieNotFound(folder.name)
        self.movie = Movie(**meta)
        self.characters: dict[str, Character] = {
            c["id"]: Character(**c) for c in _read_json(folder / "characters.json", [])
        }
        scenes = _read_json(folder / "knowledge" / "scenes.json", None)
        if scenes is None:
            scenes = self._fallback_scenes()
        self.scenes: list[Scene] = sorted((Scene(**s) for s in scenes), key=lambda s: s.start)
        self.states: list[CharacterState] = sorted(
            (CharacterState(**s) for s in _read_json(folder / "knowledge" / "character_states.json", [])),
            key=lambda s: s.t,
        )

    def _fallback_scenes(self) -> list[dict]:
        """No preprocessing yet: one scene per subtitle line, presence = speaker."""
        srt = self.folder / self.movie.subtitles
        if not srt.exists():
            return []
        lines = parse_srt(srt, list(self.characters.values()))
        return [
            Scene(
                id=f"line{i}",
                start=ln.start,
                end=ln.end,
                characters_present=[ln.speaker] if ln.speaker else [],
                lines=[ln],
            ).model_dump()
            for i, ln in enumerate(lines)
        ]

    # ---------- point-of-view filters ----------

    def character(self, character_id: str) -> Character:
        return self.characters[character_id]

    def _was_present(self, scene: Scene, character_id: str) -> bool:
        if scene.characters_present:
            return character_id in scene.characters_present
        # Unknown presence: fall back to "spoke in this scene"; if nobody is attributed, assume present.
        speakers = {ln.speaker for ln in scene.lines if ln.speaker}
        return character_id in speakers if speakers else True

    def known_scenes(self, character_id: str, t: float) -> list[Scene]:
        """Scenes the character witnessed, cut at t.

        A scene still in progress at t keeps only lines spoken before t and drops its
        summary/key_events (those were written with the whole scene in view -> spoilers).
        """
        out: list[Scene] = []
        for s in self.scenes:
            if s.start >= t:
                break
            if not self._was_present(s, character_id):
                continue
            if s.end <= t:
                out.append(s)
            else:
                out.append(
                    s.model_copy(
                        update={
                            "end": t,
                            "summary": "",
                            "key_events": [],
                            "lines": [ln for ln in s.lines if ln.start < t],
                        }
                    )
                )
        return out

    def current_scene(self, t: float) -> Scene | None:
        for s in self.scenes:
            if s.start <= t < s.end:
                return s
        return None

    def characters_at(self, t: float) -> list[Character]:
        """Characters on screen around t (for the picker). Falls back to everyone."""
        window = [s for s in self.scenes if s.start <= t + 5 and s.end >= t - 30]
        ids: list[str] = []
        for s in window:
            for cid in s.characters_present + [ln.speaker for ln in s.lines if ln.speaker]:
                if cid and cid not in ids and cid in self.characters:
                    ids.append(cid)
        return [self.characters[i] for i in ids] or list(self.characters.values())

    def state_at(self, character_id: str, t: float) -> CharacterState | None:
        latest = None
        for st in self.states:
            if st.character_id != character_id:
                continue
            if st.t > t:
                break
            latest = st
        return latest

    def recent_lines(self, character_id: str, t: float, window_s: float) -> list[SubtitleLine]:
        lines: list[SubtitleLine] = []
        for s in self.known_scenes(character_id, t):
            lines.extend(ln for ln in s.lines if t - window_s <= ln.start < t)
        return lines


@lru_cache(maxsize=16)
def load_movie(movie_id: str) -> MovieKnowledge:
    folder = get_settings().movies_dir / movie_id
    if not folder.is_dir():
        raise MovieNotFound(movie_id)
    return MovieKnowledge(folder)


def list_movies() -> list[Movie]:
    root = get_settings().movies_dir
    out = []
    for p in sorted(root.glob("*/movie.json")):
        out.append(Movie(**json.loads(p.read_text(encoding="utf-8"))))
    return out
