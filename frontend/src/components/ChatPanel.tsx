import { useEffect, useRef, useState } from "react";
import { useConversation } from "../lib/useConversation";
import type { Character, OutputMode } from "../types";
import { AvatarView, type AvatarHandle } from "./AvatarView";
import { MicButton } from "./MicButton";

interface Props {
  movieId: string;
  character: Character;
  t: number;
  mode: OutputMode;
  avatarEnabled: boolean;
  onClose: () => void;
}

function fmt(t: number) {
  const s = Math.floor(t);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function ChatPanel({ movieId, character, t, mode, avatarEnabled, onClose }: Props) {
  const avatar = useRef<AvatarHandle>(null);
  const { messages, status, error, startMic, stopMic, sendText } = useConversation({
    movieId,
    characterId: character.id,
    t,
    mode,
    onAvatar: (d) => {
      if (avatarEnabled || mode === "lip_sync") avatar.current?.drive(d);
    },
  });
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  return (
    <aside className="chat">
      <header>
        <div>
          <strong>{character.name}</strong>
          <span className="muted"> · at {fmt(t)}</span>
        </div>
        <button className="ghost" onClick={onClose} aria-label="close">
          ✕
        </button>
      </header>

      <AvatarView ref={avatar} movieId={movieId} character={character} mode={mode} speaking={status === "speaking"} />
      <div className="badge">AI-generated voice & likeness</div>

      <div className="messages" ref={listRef}>
        {messages.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>
            {m.text}
          </div>
        ))}
        {status === "connecting" && <div className="muted">Connecting…</div>}
        {error && <div className="error">{error}</div>}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) void sendText(draft.trim());
          setDraft("");
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Ask ${character.name} anything, any language…`}
          disabled={status === "connecting" || status === "error"}
        />
        <MicButton
          listening={status === "listening"}
          disabled={status === "connecting" || status === "error"}
          onStart={() => void startMic()}
          onStop={stopMic}
        />
      </form>
    </aside>
  );
}
