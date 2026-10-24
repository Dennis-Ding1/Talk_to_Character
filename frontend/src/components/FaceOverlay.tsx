import { useEffect, useState, type RefObject } from "react";
import type { Character, FrameFace } from "../types";

interface Props {
  videoRef: RefObject<HTMLVideoElement>;
  faces: FrameFace[] | null; // null = still recognising
  hoveredId: string | null;
  /** the character you are talking to: only their spot stays, lit solid */
  chosenId?: string | null;
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
export function FaceOverlay({ videoRef, faces, hoveredId, chosenId, onHover, onPick }: Props) {
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
      {faces === null && !chosenId && <div className="intertitle-chip">Finding faces</div>}
      {faces !== null && !chosenId && !faces.some((f) => f.character) && (
        <div className="intertitle-chip still">No one to talk to in this frame. Play on and pause again.</div>
      )}
      {faces?.map((f, i) => {
        if (chosenId && f.character?.id !== chosenId) return null;
        const [x, y, w, h] = f.box;
        // a follow-spot: a circle around the face box, in frame-relative units
        const d = Math.max(w * rect.width, h * rect.height) * 1.35;
        const style = {
          left: `calc(${(x + w / 2) * 100}% - ${d / 2}px)`,
          top: `calc(${(y + h / 2) * 100}% - ${d / 2}px)`,
          width: d,
          height: d,
          animationDelay: `${i * 90}ms`,
        };
        const c = f.character;
        if (!c) return <div key={f.face_id} className="spot unknown" style={style} aria-hidden />;
        if (chosenId) return <div key={f.face_id} className="spot chosen" style={style} aria-hidden />;
        return (
          <button
            key={f.face_id}
            className={`spot ${hoveredId === c.id ? "hovered" : ""}`}
            style={style}
            onClick={() => onPick(c)}
            onMouseEnter={() => onHover(c.id)}
            onMouseLeave={() => onHover(null)}
            onFocus={() => onHover(c.id)}
            onBlur={() => onHover(null)}
            aria-label={`Talk to ${c.name}`}
          >
            <span className="spot-name">{c.name}</span>
          </button>
        );
      })}
    </div>
  );
}
