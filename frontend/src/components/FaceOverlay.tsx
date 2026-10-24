import { useEffect, useState, type RefObject } from "react";
import type { Character, FrameFace } from "../types";

interface Props {
  videoRef: RefObject<HTMLVideoElement>;
  faces: FrameFace[] | null; // null = still recognising
  hoveredId: string | null;
  onHover: (characterId: string | null) => void;
  onPick: (c: Character) => void;
}

interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Where the video picture actually is inside the <video> element (object-fit: contain letterboxing). */
function contentRect(v: HTMLVideoElement): Rect | null {
  if (!v.videoWidth || !v.videoHeight) return null;
  const scale = Math.min(v.clientWidth / v.videoWidth, v.clientHeight / v.videoHeight);
  const width = v.videoWidth * scale;
  const height = v.videoHeight * scale;
  return {
    left: v.offsetLeft + (v.clientWidth - width) / 2,
    top: v.offsetTop + (v.clientHeight - height) / 2,
    width,
    height,
  };
}

/** Clickable boxes over the paused frame: click a recognised face to talk to that character. */
export function FaceOverlay({ videoRef, faces, hoveredId, onHover, onPick }: Props) {
  const [rect, setRect] = useState<Rect | null>(null);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const update = () => setRect(contentRect(v));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(v);
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [videoRef]);

  if (!rect) return null;
  return (
    <div className="face-overlay" style={rect}>
      {faces === null && <div className="face-overlay-hint">Recognising faces…</div>}
      {faces?.map((f) => {
        const [x, y, w, h] = f.box;
        const c = f.character;
        const style = { left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` };
        if (!c) return <div key={f.face_id} className="face-box unknown" style={style} title="Not recognised" />;
        return (
          <button
            key={f.face_id}
            className={`face-box ${hoveredId === c.id ? "hovered" : ""}`}
            style={style}
            onClick={() => onPick(c)}
            onMouseEnter={() => onHover(c.id)}
            onMouseLeave={() => onHover(null)}
            title={`Talk to ${c.name}`}
          >
            <span className="face-label">{c.name}</span>
          </button>
        );
      })}
    </div>
  );
}
