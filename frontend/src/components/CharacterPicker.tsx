import { useState } from "react";
import { api } from "../lib/api";
import type { Character, FaceCrop } from "../types";

interface Props {
  movieId: string;
  t: number;
  characters: Character[];
  hoveredId?: string | null;
  onHover?: (characterId: string | null) => void;
  onPick: (c: Character, face: FaceCrop | null) => void;
  onClose: () => void;
}

/**
 * Who do you want to talk to? Each card shows the character's best shot *in this scene, before the
 * pause* (from the offline face index), so the picture always matches the name and their look now.
 * Films without a face index fall back to: pick a name, then point at their face on screen.
 */
export function CharacterPicker({ movieId, t, characters, hoveredId, onHover, onPick, onClose }: Props) {
  const [askFaceFor, setAskFaceFor] = useState<Character | null>(null);
  const [faces, setFaces] = useState<FaceCrop[] | null>(null);

  const pick = (c: Character) => {
    if (c.look_id && c.look_url) {
      onPick(c, { id: c.look_id, url: c.look_url, frame_t: t, score: 1 });
      return;
    }
    // no indexed face: detect faces around the pause point and let the user point at them
    setAskFaceFor(c);
    setFaces(null);
    api
      .faces(movieId, t)
      .then((fs) => (fs.length ? setFaces(fs) : onPick(c, null)))
      .catch(() => onPick(c, null));
  };

  const withLook = characters.filter((c) => c.look_url);
  const others = characters.filter((c) => !c.look_url);

  return (
    <div className="picker">
      <div className="picker-head">
        <span>
          {askFaceFor ? `Which one is ${askFaceFor.name}?` : "Click a face on screen, or pick someone:"}
        </span>
        <button
          className="ghost"
          onClick={askFaceFor ? () => setAskFaceFor(null) : onClose}
          aria-label={askFaceFor ? "back" : "close"}
        >
          {askFaceFor ? "←" : "✕"}
        </button>
      </div>

      {!askFaceFor && (
        <>
          <div className="picker-list">
            {withLook.map((c) => (
              <button
                key={c.id}
                className={`picker-item card ${hoveredId === c.id ? "hovered" : ""}`}
                onClick={() => pick(c)}
                onMouseEnter={() => onHover?.(c.id)}
                onMouseLeave={() => onHover?.(null)}
              >
                <img src={c.look_url!} alt="" />
                <span>{c.name}</span>
              </button>
            ))}
          </div>
          {others.length > 0 && (
            <div className="picker-list small-list">
              {withLook.length > 0 && <span className="muted">Also in this scene:</span>}
              {others.map((c) => (
                <button key={c.id} className="picker-item" onClick={() => pick(c)}>
                  {c.face_image ? (
                    <img src={api.faceUrl(movieId, c.id)} alt="" />
                  ) : (
                    <div className="face-placeholder">{c.name[0]}</div>
                  )}
                  <span>{c.name}</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}

      {askFaceFor && (
        <div className="picker-list">
          {faces === null && <div className="muted">Finding faces on screen…</div>}
          {faces?.map((f) => (
            <button key={f.id} className="picker-item face" onClick={() => onPick(askFaceFor, f)}>
              <img src={f.url} alt="" />
            </button>
          ))}
          <button className="picker-item" onClick={() => onPick(askFaceFor, null)}>
            <div className="face-placeholder">?</div>
            <span className="muted">None of these</span>
          </button>
        </div>
      )}
    </div>
  );
}
