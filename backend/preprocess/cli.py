"""Offline pipeline. Run from backend/:  python -m preprocess.cli --help

  scenes     subtitles.srt -> knowledge/scenes.json (no LLM)
  summarize  scenes.json   -> scene summaries + knowledge/character_states.json (local LLM)
  voices     characters.json voice_clip -> characters/<id>/voice_ref.wav -> Boson voice_id
  faces      characters.json face_at_s  -> characters/<id>/face.png
  all        everything above
"""

import json
import subprocess
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
    # Keep LLM work from a previous `summarize` run (alignment is deterministic -> same ids/starts),
    # so re-running after editing story_years.json doesn't cost another LLM pass.
    out_path = folder / "knowledge" / "scenes.json"
    seen_faces = _faces_by_scene(folder, result)  # who the face index actually saw in each scene
    if out_path.exists():
        old = {s["id"]: s for s in json.loads(out_path.read_text(encoding="utf-8"))}
        kept = 0
        for s in result:
            o = old.get(s.id)
            if o and abs(o["start"] - s.start) < 0.01 and o.get("summary"):
                s.summary, s.key_events = o["summary"], o.get("key_events", [])
                # presence the LLM inferred from the text only counts if the face index confirms it
                # (or there is no face index): narration over a scene isn't being in it
                llm = set(o.get("characters_present", [])) - set(s.characters_present)
                if seen_faces is not None:
                    llm &= seen_faces.get(s.id, set())
                llm -= {ln.speaker for ln in s.lines if ln.speaker and ln.vo}
                s.characters_present = sorted(set(s.characters_present) | llm)
                kept += 1
        typer.echo(f"kept summaries for {kept} scenes")
    if seen_faces is not None:
        for s in result:
            # a face that only ever speaks voice-over here is an intercut from another time/place
            narrators = {ln.speaker for ln in s.lines if ln.speaker and ln.vo} -                         {ln.speaker for ln in s.lines if ln.speaker and not ln.vo}
            s.characters_present = sorted((set(s.characters_present) | seen_faces.get(s.id, set())) - narrators)
    _save_json(out_path, [s.model_dump() for s in result])
    attributed = sum(1 for s in result for ln in s.lines if ln.speaker)
    total = sum(len(s.lines) for s in result)
    typer.echo(f"{len(result)} scenes, {total} lines, {attributed / max(total, 1):.0%} with speaker")


def _faces_by_scene(folder: Path, scenes: list[Scene]) -> dict[str, set[str]] | None:
    """Characters whose face the offline face index recognised in each scene (None if no index)."""
    path = folder / "cache" / "face_index.npz"
    if not path.exists():
        return None
    import numpy as np

    d = np.load(path)
    if "label" not in d:
        return None
    t, lab = d["t"], d["label"]
    out: dict[str, set[str]] = {}
    for s in scenes:
        m = (t >= s.start) & (t < s.end) & (lab != "")
        names, counts = np.unique(lab[m], return_counts=True)
        out[s.id] = {str(n) for n, k in zip(names, counts) if k >= 2}  # seen at least twice
    return out


@app.command()
def summarize(
    movie_id: str,
    context: str = "",
    redo_states: bool = typer.Option(False, help="regenerate all character states (keeps summaries)"),
):
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
    if redo_states:
        existing = []  # the old file stays in use until the new one is written at the end
    states = build_states(scs, cast, existing)
    _save_json(states_path, [s.model_dump() for s in states])


@app.command()
def inner(movie_id: str, only: str = typer.Option(..., help="comma-separated character ids"), workers: int = 4):
    """Private inner notes (did / why / felt / hiding) per scene for the given characters.
    Needs `screenplay` (beats) and `summarize` (summaries) first."""
    from preprocess.summarize import build_inner_notes

    folder, movie, cast = _load(movie_id)
    scs = [Scene(**s) for s in json.loads((folder / "knowledge" / "scenes.json").read_text(encoding="utf-8"))]
    states_path = folder / "knowledge" / "character_states.json"
    states = [CharacterState(**s) for s in json.loads(states_path.read_text(encoding="utf-8"))]         if states_path.exists() else []
    states = build_inner_notes(scs, cast, states, set(only.split(",")), workers=workers)
    _save_json(states_path, [s.model_dump() for s in states])
    typer.echo(f"saved {sum(1 for s in states if s.why)} inner notes")


@app.command()
def moments(
    movie_id: str,
    only: str = typer.Option(..., help="comma-separated character ids"),
    demo: str = typer.Option(None, help="a demo cut of this movie: write notes for its clips only"),
    ranges: str = typer.Option(None, help="or source-time ranges, e.g. 235-541,1914-2011"),
    workers: int = 4,
):
    """Time-anchored inner thoughts inside scenes (for pauses mid-scene) -> knowledge/moments.json."""
    from preprocess.summarize import build_moment_notes

    folder, movie, cast = _load(movie_id)
    if demo:
        segs = json.loads((get_settings().movies_dir / demo / "movie.json").read_text(encoding="utf-8"))["segments"]
        spans = [(s["src_start"], s["src_end"]) for s in segs]
    elif ranges:
        spans = [tuple(float(x) for x in r.split("-")) for r in ranges.split(",")]
    else:
        raise typer.BadParameter("give --demo or --ranges")
    scs = [Scene(**s) for s in json.loads((folder / "knowledge" / "scenes.json").read_text(encoding="utf-8"))]
    states_path = folder / "knowledge" / "character_states.json"
    states = [CharacterState(**s) for s in json.loads(states_path.read_text(encoding="utf-8"))]
    notes = build_moment_notes(scs, cast, states, set(only.split(",")), spans, workers=workers)
    out = folder / "knowledge" / "moments.json"
    keep = [n for n in (json.loads(out.read_text(encoding="utf-8")) if out.exists() else [])
            if not any(a <= n["t"] < b for a, b in spans) or n["character_id"] not in only.split(",")]
    _save_json(out, sorted(keep + notes, key=lambda n: (n["character_id"], n["t"])))
    typer.echo(f"saved {len(notes)} moment notes")


@app.command()
def voices(
    movie_id: str,
    register: bool = True,
    only: str = typer.Option(None, help="comma-separated character ids"),
    redo: bool = typer.Option(False, help="re-clone characters that already have a voice_id"),
    reclip: bool = typer.Option(False, help="cut and clean the clip from the video again, even if "
                                "characters/<id>/voice_ref.wav already exists"),
):
    """Clone each character's voice. Without a hand-picked voice_clip, one is found automatically
    from speaker-attributed scenes (run `screenplay` first).
    On a new API key (voices belong to the key that created them): `voices <movie> --redo` re-registers
    the existing voice_ref.wav + voice_ref_text in a few seconds, without the video, demucs or whisper."""
    from preprocess.voice_auto import find_voice_clips

    folder, movie, cast = _load(movie_id)
    video = folder / movie.video
    wanted = set(only.split(",")) if only else None
    scenes_path = folder / "knowledge" / "scenes.json"
    scs = [Scene(**s) for s in json.loads(scenes_path.read_text(encoding="utf-8"))] if scenes_path.exists() else []
    for c in cast:
        if (wanted and c.id not in wanted) or (c.voice_id and not redo):
            continue
        cdir = folder / "characters" / c.id
        ready = cdir / "voice_ref.wav"
        if ready.exists() and c.voice_ref_text and not reclip:
            if register:
                c.voice_id = voice_clips.register_voice(ready, c.voice_ref_text, f"{movie.id}-{c.id}")
            typer.echo(f"{c.id}: voice_id={c.voice_id} (from existing voice_ref.wav)")
            _save_cast(folder, cast)
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


@app.command()
def faceindex(
    movie_id: str,
    step: str = typer.Option("all", help="scan | identify | looks | all"),
    workers: int = 8,
    fps: float = 1.0,
):
    """Index every face in the film, recognise who is who, and cut the best looks per scene.
    Needs knowledge/scenes.json with speakers (run `screenplay` or `scenes` first)."""
    import time

    from preprocess import face_index as fi

    folder, movie, cast = _load(movie_id)
    video = folder / movie.video
    index = folder / "cache" / "face_index.npz"
    index.parent.mkdir(parents=True, exist_ok=True)
    scenes = json.loads((folder / "knowledge" / "scenes.json").read_text(encoding="utf-8"))
    if step in ("scan", "all"):
        t0 = time.time()
        dur = movie.duration_s or float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
            capture_output=True, text=True).stdout.strip())
        n = fi.scan(video, dur, index, fps=fps, workers=workers)
        typer.echo(f"scan: {n} faces in {time.time() - t0:.0f}s")
    if step in ("identify", "all"):
        report = fi.identify(index, scenes, [c.id for c in cast])
        for cid, r in report.items():
            typer.echo(f"  {cid:12s} seeds={r['seeds']:4d} kept={r['kept']:4d} labelled faces={r.get('faces', 0)}")
    if step in ("looks", "all"):
        t0 = time.time()
        looks_dir = folder / "cache" / "looks"
        looks = fi.build_looks(index, video, scenes, looks_dir, workers=workers)
        fi.save_looks(folder / "knowledge" / "looks.json", looks)
        sheets = folder / "cache" / "sheets"
        sheets.mkdir(exist_ok=True)
        for c in cast:
            fi.contact_sheet(index, looks_dir, looks, c.id, sheets / f"{c.id}.jpg")
        typer.echo(f"looks: {len(looks)} crops in {time.time() - t0:.0f}s; review cache/sheets/*.jpg")


@app.command("all")
def run_all(movie_id: str):
    scenes(movie_id)
    summarize(movie_id)
    faces(movie_id)
    voices(movie_id)


if __name__ == "__main__":
    app()
