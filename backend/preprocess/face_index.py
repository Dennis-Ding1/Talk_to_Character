"""Offline face index for a whole film: who is on screen when, and how good each shot of their face is.

1. scan:     decode the film at ~1 fps (parallel ffmpeg pipes), detect faces (YuNet), score quality,
             compute identity embeddings (SFace)            -> cache/face_index.npz
2. identify: label faces with characters, using the subtitles as weak supervision: when a character
             is speaking and exactly one face is on screen, that face is probably them. Clean those
             samples, then label every face by nearest neighbours           -> (in the npz)
3. looks:    per scene and character, cut the best few head-and-shoulders crops (full resolution)
                                                            -> cache/looks/*.jpg + knowledge/looks.json
At runtime the app picks the best look of a character in the current scene *before* the pause point.
"""

import json
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

MODELS = Path(__file__).resolve().parents[1] / "models"
DET_MODEL = MODELS / "face_detection_yunet_2023mar.onnx"
REC_MODEL = MODELS / "face_recognition_sface_2021dec.onnx"
W, H = 1280, 720  # analysis resolution
SAME_PERSON = 0.40  # SFace cosine similarity; OpenCV suggests 0.363


# ---------------------------------------------------------------- 1. scan

def _quality(img: np.ndarray, f: np.ndarray) -> tuple[float, float, float, float]:
    """(overall, sharpness, frontal, size) — higher is better."""
    x, y, w, h = (float(v) for v in f[:4])
    rex, rey, lex, ley, nx, ny = (float(v) for v in f[4:10])
    eye_dist = float(np.hypot(lex - rex, ley - rey))
    frontal = min(eye_dist / max(w, 1) / 0.42, 1.0)
    mid = (rex + lex) / 2
    centred = 1.0 - min(abs(nx - mid) / max(eye_dist, 1), 1.0)
    roi = img[max(int(y), 0): int(y + h), max(int(x), 0): int(x + w)]
    sharp = float(cv2.Laplacian(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()) if roi.size else 0.0
    size = min(h / H / 0.22, 1.0)  # a face ~1/4.5 of the frame height or bigger is "big enough"
    conf = float(f[14])
    overall = conf * (0.3 + 0.7 * frontal * (0.5 + 0.5 * centred)) * (0.25 + 0.75 * size) \
        * min(sharp / 120, 1.0) ** 0.6
    return overall, sharp, frontal * centred, size


def _scan_chunk(args: tuple[str, float, float, float]) -> list[dict]:
    video, start, dur, fps = args
    det = cv2.FaceDetectorYN.create(str(DET_MODEL), "", (W, H), 0.75, 0.3, 50)
    rec = cv2.FaceRecognizerSF.create(str(REC_MODEL), "")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
           "-i", video, "-vf", f"fps={fps},scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    out: list[dict] = []
    i = 0
    frame_bytes = W * H * 3
    while True:
        buf = proc.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        img = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        t = start + i / fps
        i += 1
        rows = np.flatnonzero(img.mean(axis=(1, 2)) > 12)  # letterbox
        top, bottom = (int(rows[0]), int(rows[-1]) + 1) if len(rows) else (0, H)
        _, faces = det.detect(img)
        if faces is None:
            continue
        faces = [f for f in faces if f[3] >= 40 and f[1] >= top - 2 and f[1] + f[3] <= bottom + 4]
        for f in faces:
            q, sharp, frontal, size = _quality(img, f)
            aligned = rec.alignCrop(img, f)
            emb = rec.feature(aligned).flatten()
            out.append({
                "t": round(t, 2), "box": [round(float(v), 1) for v in f[:4]],
                "q": round(q, 4), "sharp": round(sharp, 1), "frontal": round(frontal, 3),
                "size": round(size, 3), "n": len(faces), "top": top, "bottom": bottom,
                "emb": emb / (np.linalg.norm(emb) + 1e-9),
            })
    proc.wait()
    return out


def scan(video: Path, duration: float, out: Path, fps: float = 1.0, workers: int = 8) -> int:
    n = workers * 4  # more chunks than workers -> better load balance
    step = duration / n
    jobs = [(str(video), k * step, step, fps) for k in range(n)]
    faces: list[dict] = []
    with ProcessPoolExecutor(workers) as pool:
        for k, chunk in enumerate(pool.map(_scan_chunk, jobs)):
            faces.extend(chunk)
            print(f"  chunk {k + 1}/{n}: {len(chunk)} faces")
    faces.sort(key=lambda r: r["t"])
    np.savez_compressed(
        out,
        t=np.array([r["t"] for r in faces], np.float32),
        box=np.array([r["box"] for r in faces], np.float32).reshape(-1, 4),
        q=np.array([r["q"] for r in faces], np.float32),
        sharp=np.array([r["sharp"] for r in faces], np.float32),
        frontal=np.array([r["frontal"] for r in faces], np.float32),
        size=np.array([r["size"] for r in faces], np.float32),
        n=np.array([r["n"] for r in faces], np.int16),
        top=np.array([r["top"] for r in faces], np.int16),
        bottom=np.array([r["bottom"] for r in faces], np.int16),
        emb=np.array([r["emb"] for r in faces], np.float32).reshape(-1, 128),
    )
    return len(faces)


# ---------------------------------------------------------------- 2. identify

def _speaker_at(lines: list[tuple[float, float, str]], t: float) -> str | None:
    for a, b, spk in lines:
        if a - 0.3 <= t <= b + 0.3:
            return spk
    return None


def identify(index: Path, scenes: list[dict], cast_ids: list[str], min_votes: int = 8) -> dict:
    d = dict(np.load(index))
    emb, t, n, q = d["emb"], d["t"], d["n"], d["q"]
    lines = sorted((ln["start"], ln["end"], ln["speaker"]) for s in scenes for ln in s["lines"]
                   if ln.get("speaker") in cast_ids)
    # weak labels: speaker talking + exactly one decent face on screen
    seeds: dict[str, list[int]] = {}
    for i in range(len(t)):
        if n[i] != 1 or q[i] < 0.15:
            continue
        spk = _speaker_at(lines, float(t[i]))
        if spk:
            seeds.setdefault(spk, []).append(i)

    # 1) within-character cleaning: keep seeds that agree with the bulk of that character's seeds
    #    (a reaction shot of the listener is an outlier among many shots of the speaker)
    report: dict[str, dict] = {}
    core: dict[str, np.ndarray] = {}
    for cid, idx in seeds.items():
        report[cid] = {"seeds": len(idx), "kept": 0}
        if len(idx) < min_votes:
            continue
        E = emb[idx]
        support = (E @ E.T >= SAME_PERSON).sum(1) / len(idx)
        keep = np.array(idx)[support >= max(0.25, float(np.median(support)) * 0.7)]
        core[cid] = keep

    def score(vecs: np.ndarray, cid: str, k: int = 5) -> np.ndarray:
        """Similarity of each vector to a character = mean of its k most similar core samples."""
        S = vecs @ emb[core[cid]].T
        k = min(k, S.shape[1])
        return np.sort(S, axis=1)[:, -k:].mean(1)

    # 2) cross-character cleaning, twice: drop seeds that look more like someone else
    #    (e.g. Kitty speaking off-screen over a shot of Robert)
    for _ in range(2):
        cids = list(core)
        for cid in cids:
            if len(core[cid]) == 0:
                continue
            own = score(emb[core[cid]], cid, k=6)
            other = np.max([score(emb[core[cid]], o) for o in cids if o != cid] or [np.zeros(len(own))], axis=0)
            core[cid] = core[cid][own > other + 0.02]
    for cid in core:
        report[cid]["kept"] = int(len(core[cid]))
    core = {c: v for c, v in core.items() if len(v) >= 5}
    # what each character looks like, for recognising faces live at the pause point (app/faces.py)
    np.savez_compressed(index.parent / "face_cores.npz", **{c: emb[v] for c, v in core.items()})

    # 3) label every face: most similar character, clearly better than the runner-up
    labels = np.full(len(t), "", dtype=object)
    conf = np.zeros(len(t), np.float32)
    if core:
        cids = list(core)
        scores = np.stack([score(emb, c) for c in cids], axis=1)  # faces x characters
        order = np.argsort(-scores, axis=1)
        best, second = order[:, 0], order[:, 1] if len(cids) > 1 else order[:, 0]
        s1 = scores[np.arange(len(t)), best]
        s2 = scores[np.arange(len(t)), second] if len(cids) > 1 else np.zeros(len(t))
        ok = (s1 >= 0.45) & (s1 - s2 >= 0.06)
        for i in np.flatnonzero(ok):
            labels[i] = cids[best[i]]
            conf[i] = s1[i]
        # 4) one person per frame: if two faces in the same frame got the same name, keep the surer one
        by_frame: dict[tuple[float, str], int] = {}
        for i in np.flatnonzero(ok):
            key = (float(t[i]), labels[i])
            j = by_frame.get(key)
            if j is None or conf[i] > conf[j]:
                if j is not None:
                    labels[j], conf[j] = "", 0.0
                by_frame[key] = i
            else:
                labels[i], conf[i] = "", 0.0
    d["label"] = labels.astype("U32")
    d["label_conf"] = conf
    np.savez_compressed(index, **d)
    for cid in cast_ids:
        report.setdefault(cid, {"seeds": 0, "kept": 0})
        report[cid]["faces"] = int((d["label"] == cid).sum())
    return report


# ---------------------------------------------------------------- 3. looks

def _crop_box(box, top, bottom, src_w, src_h) -> tuple[int, int, int]:
    sx, sy = src_w / W, src_h / H
    x, y, w, h = box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy
    top, bottom = top * sy, bottom * sy
    side = min(h * 2.3, bottom - top, src_w)
    cx, cy = x + w / 2, y + h * 0.6
    x0 = int(min(max(cx - side / 2, 0), src_w - side))
    y0 = int(min(max(cy - side / 2, top), bottom - side))
    return x0, y0, int(side)


_cut_models: tuple | None = None


def _grab(video: str, t: float, src_w: int, src_h: int) -> np.ndarray | None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(t, 0):.2f}", "-i", video,
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True)
    if len(r.stdout) < src_w * src_h * 3:
        return None
    return np.frombuffer(r.stdout[: src_w * src_h * 3], np.uint8).reshape(src_h, src_w, 3)


def _cut_one(args) -> float | None:
    """Cut a head-and-shoulders crop, verifying it's the same face the index saw.

    The scan's frame times can be off by up to ~0.5 s, which in a shot/reverse-shot dialogue lands on
    the *other* person. So we re-detect at full resolution, match the face embedding, and step back
    in time (never forward) until it matches. Returns the time actually used, or None."""
    global _cut_models
    video, t, box, top, bottom, src_w, src_h, out, ref_emb = args
    if _cut_models is None:
        _cut_models = (cv2.FaceDetectorYN.create(str(DET_MODEL), "", (W, H), 0.75, 0.3, 50),
                       cv2.FaceRecognizerSF.create(str(REC_MODEL), ""))
    det, rec = _cut_models
    for dt in (0.0, -0.4, -0.8, 0.4):
        full = _grab(video, t + dt, src_w, src_h)
        if full is None:
            continue
        small = cv2.resize(full, (W, H), interpolation=cv2.INTER_AREA)
        _, faces = det.detect(small)
        if faces is None:
            continue
        best, best_sim = None, 0.0
        for f in faces:
            e = rec.feature(rec.alignCrop(small, f)).flatten()
            sim = float(e @ ref_emb / (np.linalg.norm(e) + 1e-9))
            if sim > best_sim:
                best, best_sim = f, sim
        if best is None or best_sim < 0.55:
            continue
        x0, y0, side = _crop_box(best[:4], top, bottom, src_w, src_h)
        crop = cv2.resize(full[y0: y0 + side, x0: x0 + side], (640, 640), interpolation=cv2.INTER_LANCZOS4)
        cv2.imwrite(out, crop, [cv2.IMWRITE_JPEG_QUALITY, 93])
        return round(t + dt, 2)
    return None


def build_looks(index: Path, video: Path, scenes: list[dict], out_dir: Path, per_scene: int = 3,
                min_q: float = 0.35, min_gap_s: float = 3.0, workers: int = 8,
                min_frontal: float = 0.45, min_sharp: float = 40.0) -> list[dict]:
    d = dict(np.load(index))
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    src_w, src_h = (int(v) for v in probe.stdout.strip().split(",")[:2])
    out_dir.mkdir(parents=True, exist_ok=True)
    looks, jobs = [], []
    t, lab, q = d["t"], d["label"], d["q"]
    for s in scenes:
        in_scene = (t >= s["start"]) & (t < s["end"])
        for cid in sorted(set(lab[in_scene]) - {""}):
            idx = np.flatnonzero(in_scene & (lab == cid) & (q >= min_q)
                                 & (d["frontal"] >= min_frontal) & (d["sharp"] >= min_sharp))
            chosen: list[int] = []
            for i in idx[np.argsort(-q[idx])]:  # best first, spread out in time
                if all(abs(t[i] - t[j]) >= min_gap_s for j in chosen):
                    chosen.append(int(i))
                if len(chosen) == per_scene:
                    break
            for k, i in enumerate(chosen):
                look_id = f"{s['id']}_{cid}_{k}"
                looks.append({"id": look_id, "scene_id": s["id"], "character_id": cid,
                              "t": float(t[i]), "q": round(float(q[i]), 3)})
                jobs.append((str(video), float(t[i]), d["box"][i], int(d["top"][i]), int(d["bottom"][i]),
                             src_w, src_h, str(out_dir / f"{look_id}.jpg"), d["emb"][i]))
    with ProcessPoolExecutor(workers) as pool:
        used = list(pool.map(_cut_one, jobs, chunksize=4))
    kept = []
    for lk, t_used in zip(looks, used):
        if t_used is not None:
            lk["t"] = t_used
            kept.append(lk)
    print(f"  verified {len(kept)}/{len(looks)} crops (others didn't match the indexed face)")
    return kept


def contact_sheet(index: Path, video_looks: Path, looks: list[dict], character_id: str, out: Path, n: int = 24):
    """Grid of a character's looks across the film, to eyeball whether identification is right."""
    mine = [lk for lk in looks if lk["character_id"] == character_id]
    step = max(1, len(mine) // n)
    tiles = [cv2.resize(cv2.imread(str(video_looks / f"{lk['id']}.jpg")), (160, 160)) for lk in mine[::step][:n]]
    if not tiles:
        return False
    while len(tiles) % 8:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + 8]) for i in range(0, len(tiles), 8)]
    cv2.imwrite(str(out), np.vstack(rows))
    return True


def save_looks(path: Path, looks: list[dict]) -> None:
    path.write_text(json.dumps(looks, indent=1), encoding="utf-8")
