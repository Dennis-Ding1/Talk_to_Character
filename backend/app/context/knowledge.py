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
        self.scene_by_id = {s.id: s for s in self.scenes}
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

    def now_year(self, t: float) -> float | None:
        """Story time of what's on screen at t (None for linear films without story_year)."""
        s = self.current_scene(t)
        return s.story_year if s else None

    def known_scenes(self, character_id: str, t: float) -> list[Scene]:
        """Scenes the character witnessed that the viewer has already seen, as of the story
        moment on screen at t. Ordered by story time (the character's memory order).

        Rules:
        - viewer has seen it: scene.start < t
        - character was there: characters_present
        - non-linear films: it happened no later (in the story) than the scene on screen now,
          so a 1942 flashback can't "remember" a 1954 hearing the viewer saw earlier.
        - a scene still in progress at t keeps only lines before t and drops its
          summary/key_events (those were written with the whole scene in view).
        """
        now = self.now_year(t)
        out: list[Scene] = []
        for s in self.scenes:
            if s.start >= t:
                break
            if not self._was_present(s, character_id):
                continue
            if now is not None and s.story_year is not None and s.story_year > now + 1e-6:
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
        out.sort(key=lambda s: (s.story_year if s.story_year is not None else 0.0, s.start))
        return out

    def current_scene(self, t: float) -> Scene | None:
        """The scene playing at t, or the last one that started before t (gaps between scenes)."""
        last = None
        for s in self.scenes:
            if s.start > t:
                break
            last = s
            if t < s.end:
                return s
        return last

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
        mine = [st for st in self.states if st.character_id == character_id]
        if any(st.scene_id for st in mine):
            # Per-scene states: take the one from the latest (in story order) fully-seen known scene.
            done = {s.id: i for i, s in enumerate(self.known_scenes(character_id, t)) if s.summary or s.end < t}
            ranked = [st for st in mine if st.scene_id in done]
            return max(ranked, key=lambda st: done[st.scene_id]) if ranked else None
        latest = None
        for st in mine:  # screen-time checkpoints (hand-written data)
            if st.t > t:
                break
            latest = st
        return latest

    def recent_lines(self, character_id: str, t: float, window_s: float) -> list[SubtitleLine]:
        lines: list[SubtitleLine] = []
        for s in self.known_scenes(character_id, t):
            lines.extend(ln for ln in s.lines if t - window_s <= ln.start < t)
        return lines


_DATA_FILES = ("movie.json", "characters.json", "knowledge/scenes.json", "knowledge/character_states.json")


def _signature(folder: Path) -> tuple:
    return tuple((folder / f).stat().st_mtime_ns if (folder / f).exists() else 0 for f in _DATA_FILES)


@lru_cache(maxsize=16)
def _load_cached(folder: Path, signature: tuple) -> MovieKnowledge:
    return MovieKnowledge(folder)


def load_movie(movie_id: str) -> MovieKnowledge:
    """Cached, but reloads automatically when any data file changes (new voices, new summaries...)."""
    folder = get_settings().movies_dir / movie_id
    if not folder.is_dir():
        raise MovieNotFound(movie_id)
    return _load_cached(folder, _signature(folder))


def list_movies() -> list[Movie]:
    root = get_settings().movies_dir
    out = []
    for p in sorted(root.glob("*/movie.json")):
        out.append(Movie(**json.loads(p.read_text(encoding="utf-8"))))
    return out
