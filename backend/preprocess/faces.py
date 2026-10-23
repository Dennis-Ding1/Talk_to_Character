"""Reference image for Higgs Avatar: grab a frame and crop to the output aspect ratio.

Pick a timestamp with a clear, frontal, well-lit face. Crop is centered unless you pass a box.
"""

import subprocess
from pathlib import Path

ASPECTS = {"640x640": (1, 1), "640x480": (4, 3), "480x640": (3, 4)}


def grab_face(
    video: Path,
    at_s: float,
    out: Path,
    size: str = "640x640",
    box: tuple[int, int, int, int] | None = None,  # x, y, w, h in source pixels
) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = ASPECTS[size]
    if box:
        x, y, bw, bh = box
        crop = f"crop={bw}:{bh}:{x}:{y}"
    else:
        # largest centered crop with the target aspect ratio
        crop = f"crop='min(iw,ih*{w}/{h})':'min(ih,iw*{h}/{w})'"
    ow, oh = size.split("x")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at_s), "-i", str(video), "-frames:v", "1",
         "-vf", f"{crop},scale={ow}:{oh}", str(out)],
        check=True,
    )
    return out
