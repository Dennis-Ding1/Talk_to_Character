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
