import { useState } from "react";
import { api } from "../lib/api";
import type { Character, FaceCrop } from "../types";

interface Props {
  movieId: string;
  characters: Character[];
  faces: FaceCrop[] | null; // null = still detecting
  onPick: (c: Character, face: FaceCrop | null) => void;
  onClose: () => void;
}

/** Step 1: who do you want to talk to?  Step 2: which face on screen is them (their look right now)? */
export function CharacterPicker({ movieId, characters, faces, onPick, onClose }: Props) {
  const [chosen, setChosen] = useState<Character | null>(null);

  const pickCharacter = (c: Character) => {
    if (faces && faces.length === 0) onPick(c, null);
    else setChosen(c);
  };

  return (
    <div className="picker">
      <div className="picker-head">
        <span>{chosen ? `Which one is ${chosen.name}?` : "Who do you want to talk to?"}</span>
        <button className="ghost" onClick={chosen ? () => setChosen(null) : onClose} aria-label="close">
          {chosen ? "←" : "✕"}
        </button>
      </div>

      {!chosen && (
        <div className="picker-list">
          {characters.map((c) => (
            <button key={c.id} className="picker-item" onClick={() => pickCharacter(c)}>
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

      {chosen && (
        <div className="picker-list">
          {faces === null && <div className="muted">Finding faces on screen…</div>}
          {faces?.map((f) => (
            <button key={f.id} className="picker-item face" onClick={() => onPick(chosen, f)}>
              <img src={f.url} alt="" />
            </button>
          ))}
          <button className="picker-item" onClick={() => onPick(chosen, null)}>
            <div className="face-placeholder">?</div>
            <span className="muted">None of these</span>
          </button>
        </div>
      )}
    </div>
  );
}
