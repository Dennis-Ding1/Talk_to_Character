import type { Character } from "../types";
import { api } from "../lib/api";

interface Props {
  movieId: string;
  characters: Character[];
  onPick: (c: Character) => void;
  onClose: () => void;
}

export function CharacterPicker({ movieId, characters, onPick, onClose }: Props) {
  return (
    <div className="picker">
      <div className="picker-head">
        <span>Who do you want to talk to?</span>
        <button className="ghost" onClick={onClose} aria-label="close">
          ✕
        </button>
      </div>
      <div className="picker-list">
        {characters.map((c) => (
          <button key={c.id} className="picker-item" onClick={() => onPick(c)}>
            {c.face_image ? (
              <img src={api.faceUrl(movieId, c.id)} alt="" />
            ) : (
              <div className="face-placeholder">{c.name[0]}</div>
            )}
            <span>{c.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
