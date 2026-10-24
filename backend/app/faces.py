"""Faces at a pause point -> avatar reference images that show the character's look *at that moment*
(costume, age, hair), instead of one fixed portrait.

We sample a few frames just before t (never after: no visual spoilers), detect faces with OpenCV
YuNet, group detections of the same person across frames, and keep the sharpest, most frontal
crop per person. Crops are head-and-shoulders squares (Higgs Avatar output is 640x640).
"""

import hashlib
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

MODEL = Path(__file__).resolve().parents[1] / "models" / "face_detection_yunet_2023mar.onnx"
OUT_SIZE = 640


@dataclass
class FaceCrop:
    id: str  # file stem in the cache dir
    frame_t: float
    score: float
    box: tuple[int, int, int, int]  # x, y, w, h in the sampled frame


_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(str(MODEL), "", (320, 320), 0.7, 0.3, 50)
    return _detector


def _sample_frames(video: Path, t: float, window: float, fps: float) -> list[tuple[float, np.ndarray]]:
    start = max(0.0, t - window)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", str(video),
             "-t", f"{t - start:.3f}", "-vf", f"fps={fps},scale=1280:-2", f"{tmp}/f%03d.png"],
            check=True,
        )
        files = sorted(Path(tmp).glob("f*.png"))
        return [(start + i / fps, cv2.imread(str(f))) for i, f in enumerate(files)]


def _content_rows(img: np.ndarray) -> tuple[int, int]:
    """Rows without letterbox bars."""
    rows = img.mean(axis=(1, 2)) > 12
    idx = np.flatnonzero(rows)
    return (int(idx[0]), int(idx[-1]) + 1) if len(idx) else (0, img.shape[0])


def _quality(img: np.ndarray, f: np.ndarray) -> float:
    x, y, w, h = f[:4]
    conf = float(f[14])
    rex, rey, lex, ley, nx, ny = f[4:10]
    eye_dist = np.hypot(lex - rex, ley - rey)
    frontal = min(eye_dist / max(w, 1) / 0.42, 1.0)  # turned heads have eyes close together
    mid = (rex + lex) / 2
    centred = 1.0 - min(abs(nx - mid) / max(eye_dist, 1), 1.0)  # nose between the eyes
    roi = img[max(int(y), 0): int(y + h), max(int(x), 0): int(x + w)]
    sharp = cv2.Laplacian(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() if roi.size else 0
    size = min(w * h / (img.shape[0] * img.shape[1]) / 0.04, 1.0)  # big faces are better, saturates
    return conf * (0.4 + 0.6 * frontal) * (0.5 + 0.5 * centred) * (0.3 + 0.7 * size) * min(sharp / 150, 1.0) ** 0.5


def _crop(img: np.ndarray, f: np.ndarray, top: int, bottom: int) -> np.ndarray:
    x, y, w, h = (float(v) for v in f[:4])
    side = min(h * 2.3, bottom - top, img.shape[1])
    cx, cy = x + w / 2, y + h * 0.6  # a little below the face centre: head, collar and shoulders
    x0 = int(min(max(cx - side / 2, 0), img.shape[1] - side))
    y0 = int(min(max(cy - side / 2, top), bottom - side))
    crop = img[y0: y0 + int(side), x0: x0 + int(side)]
    return cv2.resize(crop, (OUT_SIZE, OUT_SIZE), interpolation=cv2.INTER_CUBIC)


def faces_at(video: Path, t: float, cache_dir: Path, window: float = 6.0, fps: float = 2.0,
             max_faces: int = 4) -> list[FaceCrop]:
    key = hashlib.md5(f"{video.name}:{t:.1f}".encode()).hexdigest()[:10]
    cache_dir.mkdir(parents=True, exist_ok=True)

    det = _get_detector()
    tracks: list[dict] = []  # people: last centre + best detection
    for ft, img in _sample_frames(video, t, window, fps):
        if img is None:
            continue
        top, bottom = _content_rows(img)
        det.setInputSize((img.shape[1], img.shape[0]))
        _, found = det.detect(img)
        if found is None:
            continue
        for f in found:
            if f[1] < top or f[1] + f[3] > bottom + 5:
                continue
            q = _quality(img, f)
            c = np.array([f[0] + f[2] / 2, f[1] + f[3] / 2])
            match = next((tr for tr in tracks if np.linalg.norm(tr["c"] - c) < max(f[2], tr["w"]) * 1.2), None)
            if match is None:
                match = {"c": c, "w": f[2], "q": -1.0}
                tracks.append(match)
            match["c"], match["w"] = c, f[2]
            # prefer the most recent frame on ties: that's the look at the pause point
            if q >= match["q"] * 0.95:
                match.update(q=q, f=f.copy(), img=img, t=ft, top=top, bottom=bottom)

    tracks = sorted((tr for tr in tracks if tr["q"] > 0.05), key=lambda tr: -tr["q"])[:max_faces]
    out = []
    for i, tr in enumerate(tracks):
        fid = f"{key}_{i}"
        cv2.imwrite(str(cache_dir / f"{fid}.jpg"), _crop(tr["img"], tr["f"], tr["top"], tr["bottom"]),
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        x, y, w, h = (int(v) for v in tr["f"][:4])
        out.append(FaceCrop(fid, round(tr["t"], 2), round(float(tr["q"]), 3), (x, y, w, h)))
    return out


# ---------------------------------------------------------------- recognise faces at the pause point

REC_MODEL = Path(__file__).resolve().parents[1] / "models" / "face_recognition_sface_2021dec.onnx"
_W, _H = 1280, 720  # same analysis resolution as the offline index
_rec = None
_cores_cache: dict[str, tuple[int, dict[str, np.ndarray]]] = {}


def _get_recognizer():
    global _rec
    if _rec is None:
        _rec = cv2.FaceRecognizerSF.create(str(REC_MODEL), "")
    return _rec


def _load_cores(path: Path) -> dict[str, np.ndarray]:
    """Per-character face embeddings from `preprocess faceindex` (cached, reloaded if the file changes)."""
    if not path.exists():
        return {}
    mtime = path.stat().st_mtime_ns
    hit = _cores_cache.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    cores = dict(np.load(path))
    _cores_cache[str(path)] = (mtime, cores)
    return cores


def _grab_frame(video: Path, t: float) -> np.ndarray | None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "f.png"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(video),
                        "-frames:v", "1", str(out)], check=False)
        return cv2.imread(str(out)) if out.exists() else None


def recognise_frame(video: Path, t: float, cores_path: Path, cache_dir: Path,
                    min_sim: float = 0.45, margin: float = 0.06) -> list[dict]:
    """Detect faces in the exact frame at t and say who each one is.

    Returns boxes normalised to the full video frame (so the UI can draw them over the player), the
    character id when recognised (same rule as the offline index: best match, clearly ahead of the
    runner-up), and a head-and-shoulders crop of that face (fallback avatar picture)."""
    full = _grab_frame(video, t)
    if full is None:
        return []
    src_h, src_w = full.shape[:2]
    small = cv2.resize(full, (_W, _H), interpolation=cv2.INTER_AREA)
    det = _get_detector()
    det.setInputSize((_W, _H))
    _, found = det.detect(small)
    if found is None:
        return []
    rec = _get_recognizer()
    cores = _load_cores(cores_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"frame:{video.name}:{t:.2f}".encode()).hexdigest()[:10]
    top, bottom = _content_rows(full)
    sx, sy = src_w / _W, src_h / _H
    out = []
    for i, f in enumerate(sorted(found, key=lambda f: -f[2] * f[3])):  # biggest first
        if f[3] < 28:
            continue
        emb = rec.feature(rec.alignCrop(small, f)).flatten()
        emb = emb / (np.linalg.norm(emb) + 1e-9)
        scores = sorted(((float(np.sort(c @ emb)[-5:].mean()), cid) for cid, c in cores.items()), reverse=True)
        cid, conf = None, 0.0
        if scores and scores[0][0] >= min_sim and (len(scores) == 1 or scores[0][0] - scores[1][0] >= margin):
            conf, cid = scores[0]
        full_box = np.array([f[0] * sx, f[1] * sy, f[2] * sx, f[3] * sy, *f[4:14] * np.tile([sx, sy], 5), f[14]])
        fid = f"{key}_{i}"
        cv2.imwrite(str(cache_dir / f"{fid}.jpg"), _crop(full, full_box, top, bottom), [cv2.IMWRITE_JPEG_QUALITY, 92])
        out.append({
            "box": [round(float(f[0]) / _W, 4), round(float(f[1]) / _H, 4),
                    round(float(f[2]) / _W, 4), round(float(f[3]) / _H, 4)],
            "character_id": cid, "confidence": round(conf, 3), "face_id": fid,
        })
    # one person per frame: if two faces got the same name, keep the more confident one
    best: dict[str, dict] = {}
    for o in out:
        if o["character_id"] and (o["character_id"] not in best or o["confidence"] > best[o["character_id"]]["confidence"]):
            best[o["character_id"]] = o
    for o in out:
        if o["character_id"] and best[o["character_id"]] is not o:
            o["character_id"], o["confidence"] = None, 0.0
    return out
