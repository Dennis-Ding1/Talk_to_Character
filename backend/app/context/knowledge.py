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
        self.scene_order = {s.id: i for i, s in enumerate(self.scenes)}
        # best face crops per scene and character (preprocess `faceindex`), cache/looks/<id>.jpg
        self.looks: dict[str, list[dict]] = {}
        for lk in _read_json(folder / "knowledge" / "looks.json", []):
            self.looks.setdefault(lk["scene_id"], []).append(lk)
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

    def viewer_frontier(self, t: float) -> float | None:
        """How far into the story's main ("past") timeline the viewer has watched by t.

        Frame-story scenes (a 1954 hearing shown in minute 2) don't count: seeing someone in 1954
        doesn't tell the viewer what happened between the flashbacks and 1954.
        """
        years = [s.story_year for s in self.scenes
                 if s.start < t and s.story_year is not None and s.thread in (None, "past")]
        return max(years) if years else None

    def now_year(self, t: float) -> float | None:
        """The story moment the character speaks from (None for linear films).

        Normally the story year of the scene on screen. But if that scene is a frame story *ahead*
        of what the viewer has seen (a 1954 hearing while the flashbacks have only reached 1943),
        the character is anchored at the viewer's frontier instead: a 1954 Oppenheimer knows the
        bomb worked and models can't reliably keep that secret, so we talk to the 1943 one.
        """
        s = self.current_scene(t)
        if s is None or s.story_year is None:
            return None
        frontier = self.viewer_frontier(t)
        if s.thread not in (None, "past") and (frontier is None or s.story_year > frontier + 1.0):
            if frontier is not None:
                return frontier
            # opening flash-forward, nothing of the main story seen yet: speak from where the main
            # story begins (a character with no year falls back on what the model knows — spoilers)
            return min((x.story_year for x in self.scenes
                        if x.thread in (None, "past") and x.story_year is not None), default=None)
        return s.story_year

    def is_anchored(self, t: float) -> bool:
        s = self.current_scene(t)
        return bool(s and s.story_year is not None and self.now_year(t) != s.story_year)

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

    # ---------- omniscient mode: the whole story, no time limits ----------

    def all_scenes_of(self, character_id: str) -> list[Scene]:
        """Every scene the character is in, in story order (omniscient / "what if" mode)."""
        out = [s for s in self.scenes if self._was_present(s, character_id)]
        out.sort(key=lambda s: (s.story_year if s.story_year is not None else 0.0, s.start))
        return out

    def other_scenes(self, character_id: str) -> list[Scene]:
        """Scenes the character is NOT in (they'd have heard about the big events later)."""
        out = [s for s in self.scenes if not self._was_present(s, character_id)]
        out.sort(key=lambda s: (s.story_year if s.story_year is not None else 0.0, s.start))
        return out

    def final_state(self, character_id: str) -> CharacterState | None:
        order = {s.id: i for i, s in enumerate(self.all_scenes_of(character_id))}
        mine = [st for st in self.states if st.character_id == character_id and st.scene_id in order]
        return max(mine, key=lambda st: order[st.scene_id]) if mine else None

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

    def best_look(self, character_id: str, t: float, max_back: int = 12) -> dict | None:
        """Sharpest, most frontal face of the character *as they look now*: from the current scene
        before t; otherwise from the closest earlier scene they appeared in (similar costume/age).
        Never from after t, so the picture can't spoil anything."""
        cur = self.current_scene(t)
        if cur is None or not self.looks:
            return None
        i = self.scene_order[cur.id]
        for s in reversed(self.scenes[max(0, i - max_back): i + 1]):
            cands = [lk for lk in self.looks.get(s.id, [])
                     if lk["character_id"] == character_id and lk["t"] <= t]
            if cands:
                return max(cands, key=lambda lk: lk["q"])
        return None

    def characters_at(self, t: float) -> list[Character]:
        """Characters around t for the picker: first those whose face we've seen in this scene up to t
        (best shot first), then others present. Falls back to everyone."""
        cur = self.current_scene(t)
        seen_now: dict[str, float] = {}
        if cur:
            for lk in self.looks.get(cur.id, []):
                if lk["t"] <= t and lk["character_id"] in self.characters:
                    seen_now[lk["character_id"]] = max(seen_now.get(lk["character_id"], 0), lk["q"])
        ids = sorted(seen_now, key=lambda c: -seen_now[c])
        window = [s for s in self.scenes if s.start <= t and s.end >= t - 30]
        for s in window:
            for cid in s.characters_present + [ln.speaker for ln in s.lines if ln.speaker and ln.start <= t]:
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


_DATA_FILES = ("movie.json", "characters.json", "knowledge/scenes.json", "knowledge/character_states.json",
               "knowledge/looks.json")


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
