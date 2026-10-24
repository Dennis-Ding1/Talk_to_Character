import { useEffect, useRef, useState } from "react";
import { useConversation } from "../lib/useConversation";
import type { Character, FaceCrop, KnowledgeMode, OutputMode } from "../types";
import { AvatarView, type AvatarHandle } from "./AvatarView";
import { MicButton } from "./MicButton";

interface Props {
  movieId: string;
  character: Character;
  face: FaceCrop | null;
  t: number;
  mode: OutputMode;
  knowledge: KnowledgeMode;
  onClose: () => void;
}

function fmt(t: number) {
  const s = Math.floor(t);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function ChatPanel({ movieId, character, face, t, mode, knowledge, onClose }: Props) {
  const avatar = useRef<AvatarHandle>(null);
  const { messages, status, error, session, startMic, stopMic, sendText } = useConversation({
    movieId,
    characterId: character.id,
    t,
    mode,
    knowledge,
    onAvatar: (d) => avatar.current?.drive(d), // lip_sync mode only
    onInterrupt: () => avatar.current?.interrupt(),
  });
  const [draft, setDraft] = useState("");
  const [avatarTalking, setAvatarTalking] = useState(false);

  // while the user records, the reply that's still talking is turned down (not picked up by the mic)
  useEffect(() => {
    avatar.current?.duck(status === "listening");
  }, [status]);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  return (
    <aside className="chat">
      <header>
        <div>
          <strong>{character.name}</strong>
          <span className="muted">
            {" "}
            · at {fmt(t)}
            {knowledge === "omniscient"
              ? " · knows the whole story"
              : session?.as_of_year != null && ` · ${Math.floor(session.as_of_year)}`}
          </span>
          {session?.anchored && (
            <div className="muted small">
              Flash-forward scene: so nothing gets spoiled, you're talking to {character.name} as of{" "}
              {Math.floor(session.as_of_year ?? 0)}, as far as you've followed the main story.
            </div>
          )}
        </div>
        <button className="ghost" onClick={onClose} aria-label="close">
          ✕
        </button>
      </header>

      <AvatarView
        ref={avatar}
        movieId={movieId}
        character={character}
        face={face}
        mode={mode}
        speaking={status === "speaking" || avatarTalking}
        onPlayingChange={setAvatarTalking}
      />
      <div className="badge">AI-generated voice & likeness</div>

      <div className="messages" ref={listRef}>
        {messages.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>
            {m.text}
          </div>
        ))}
        {status === "connecting" && <div className="muted">Connecting…</div>}
        {status === "thinking" && <div className="muted">{character.name} is thinking…</div>}
        {status === "ready" && messages.length === 0 && (
          <div className="muted">
            {knowledge === "omniscient"
              ? `${character.name} knows how everything turns out. Try a "what if…?" question.`
              : `${character.name} only knows the story up to this moment.`}{" "}
            Type a question, or tap 🎙 Speak, talk, then tap again to send.
          </div>
        )}
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
