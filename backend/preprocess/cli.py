"""Offline pipeline. Run from backend/:  python -m preprocess.cli --help

  scenes     subtitles.srt -> knowledge/scenes.json (no LLM)
  summarize  scenes.json   -> scene summaries + knowledge/character_states.json (local LLM)
  voices     characters.json voice_clip -> characters/<id>/voice_ref.wav -> Boson voice_id
  faces      characters.json face_at_s  -> characters/<id>/face.png
  all        everything above
"""

import json
from pathlib import Path

import typer

from app.config import get_settings
from app.context.subtitles import parse_srt
from app.schemas import Character, CharacterState, Movie, Scene
from preprocess import faces as faces_mod
from preprocess import voice_clips
from preprocess.scenes import split_scenes
from preprocess.summarize import annotate_scenes, build_states

app = typer.Typer(no_args_is_help=True)


def _folder(movie_id: str) -> Path:
    p = get_settings().movies_dir / movie_id
    if not (p / "movie.json").exists():
        raise typer.BadParameter(f"{p}/movie.json not found")
    return p


def _load(movie_id: str):
    folder = _folder(movie_id)
    movie = Movie(**json.loads((folder / "movie.json").read_text(encoding="utf-8")))
    chars_path = folder / "characters.json"
    cast = [Character(**c) for c in json.loads(chars_path.read_text(encoding="utf-8"))]
    return folder, movie, cast


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_cast(folder: Path, cast: list[Character]) -> None:
    _save_json(folder / "characters.json", [c.model_dump(exclude_none=True) for c in cast])


@app.command()
def scenes(movie_id: str, gap_s: float = 8.0):
    folder, movie, cast = _load(movie_id)
    lines = parse_srt(folder / movie.subtitles, cast)
    marks_path = folder / "scene_marks.json"
    marks = json.loads(marks_path.read_text()) if marks_path.exists() else None
    result = split_scenes(lines, gap_s=gap_s, marks=marks)
    _save_json(folder / "knowledge" / "scenes.json", [s.model_dump() for s in result])
    typer.echo(f"{len(lines)} lines -> {len(result)} scenes")


@app.command()
def screenplay(
    movie_id: str,
    first_person: str = typer.Option(None, help="character id the script's 'I/ME' refers to"),
    list_scenes: bool = typer.Option(False, "--list", help="only print screenplay scene indices"),
):
    """screenplay.pdf + subtitles.srt -> knowledge/scenes.json with speakers, presence, story years."""
    from preprocess.build_scenes import build
    from preprocess.screenplay import load_screenplay

    folder, movie, cast = _load(movie_id)
    if list_scenes:
        for s in load_screenplay(folder / "screenplay.pdf"):
            typer.echo(f"{s.index:4d} {s.timeline:6s} {s.slug}")
        return
    result = build(folder, cast, movie.subtitles, movie.duration_s, first_person)
    _save_json(folder / "knowledge" / "scenes.json", [s.model_dump() for s in result])
    attributed = sum(1 for s in result for ln in s.lines if ln.speaker)
    total = sum(len(s.lines) for s in result)
    typer.echo(f"{len(result)} scenes, {total} lines, {attributed / max(total, 1):.0%} with speaker")


@app.command()
def summarize(movie_id: str, context: str = ""):
    folder, movie, cast = _load(movie_id)
    path = folder / "knowledge" / "scenes.json"
    scs = [Scene(**s) for s in json.loads(path.read_text(encoding="utf-8"))]
    synopsis = folder / "synopsis.txt"  # optional hand-written notes (no spoilers needed: used per-scene only)
    extra = context or (synopsis.read_text(encoding="utf-8")[:2000] if synopsis.exists() else "")
    typer.echo("annotating scenes...")
    scs = annotate_scenes(scs, cast, extra)
    _save_json(path, [s.model_dump() for s in scs])
    typer.echo("building character states (one per scene per character present)...")
    states_path = folder / "knowledge" / "character_states.json"
    existing = [CharacterState(**s) for s in json.loads(states_path.read_text(encoding="utf-8"))] \
        if states_path.exists() else []
    existing = [s for s in existing if s.scene_id]  # resumable; drop hand-written checkpoints
    states = build_states(scs, cast, existing)
    _save_json(states_path, [s.model_dump() for s in states])


@app.command()
def voices(
    movie_id: str,
    register: bool = True,
    only: str = typer.Option(None, help="comma-separated character ids"),
    redo: bool = typer.Option(False, help="re-clone characters that already have a voice_id"),
):
    """Clone each character's voice. Without a hand-picked voice_clip, one is found automatically
    from speaker-attributed scenes (run `screenplay` first)."""
    from preprocess.voice_auto import find_voice_clips

    folder, movie, cast = _load(movie_id)
    video = folder / movie.video
    wanted = set(only.split(",")) if only else None
    scenes_path = folder / "knowledge" / "scenes.json"
    scs = [Scene(**s) for s in json.loads(scenes_path.read_text(encoding="utf-8"))] if scenes_path.exists() else []
    for c in cast:
        if (wanted and c.id not in wanted) or (c.voice_id and not redo):
            continue
        if not c.voice_clip:
            found = find_voice_clips(scs, c.id) or find_voice_clips(scs, c.id, min_s=4.0)
            if not found:
                typer.echo(f"skip {c.id}: no clean solo line found; set voice_clip by hand")
                continue
            c.voice_clip = found[0][:2]
            c.voice_ref_text = None
        cdir = folder / "characters" / c.id
        raw = voice_clips.cut_clip(video, *c.voice_clip, cdir / "voice_raw.wav")
        ref = voice_clips.separate_vocals(raw)
        if not c.voice_ref_text:
            c.voice_ref_text = voice_clips.transcribe(ref, movie.language)
        if register:
            c.voice_id = voice_clips.register_voice(ref, c.voice_ref_text, f"{movie.id}-{c.id}")
        typer.echo(f"{c.id}: clip={c.voice_clip} voice_id={c.voice_id} ref_text={c.voice_ref_text[:60]!r}")
        _save_cast(folder, cast)  # save as we go: each clone takes a while on CPU


@app.command()
def faces(movie_id: str, size: str = "640x640"):
    folder, movie, cast = _load(movie_id)
    for c in cast:
        if c.face_at_s is None:
            continue
        out = faces_mod.grab_face(folder / movie.video, c.face_at_s, folder / "characters" / c.id / "face.png", size)
        c.face_image = out.name
        typer.echo(f"{c.id}: {out}")
    _save_cast(folder, cast)


@app.command("all")
def run_all(movie_id: str):
    scenes(movie_id)
    summarize(movie_id)
    faces(movie_id)
    voices(movie_id)


if __name__ == "__main__":
    app()
