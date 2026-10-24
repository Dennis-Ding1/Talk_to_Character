import { useEffect, useRef, useState } from "react";
import { fmtTime } from "../lib/format";
import { useConversation } from "../lib/useConversation";
import type { Character, FaceCrop, KnowledgeMode, OutputMode } from "../types";
import { AvatarView, type AvatarHandle } from "./AvatarView";
import { Icon } from "./Icon";
import { MicButton } from "./MicButton";

const SUGGESTIONS: Record<KnowledgeMode, string[]> = {
  present: ["What's on your mind right now?", "What just happened?", "Who here do you trust?"],
  omniscient: ["What would you do differently?", "What if you had said no?", "Any regrets?"],
};

const STATUS_LABEL: Record<string, string> = {
  idle: "Disconnected",
  connecting: "Taking their seat",
  ready: "Your turn",
  listening: "Recording you",
  thinking: "Thinking",
  speaking: "Speaking",
  error: "Can't reach them",
};

interface Props {
  movieId: string;
  character: Character;
  face: FaceCrop | null;
  t: number;
  mode: OutputMode;
  knowledge: KnowledgeMode;
  onClose: () => void;
}

/** The front row: the character, stepped out of the frame, and the conversation. */
export function ChatPanel({ movieId, character, face, t, mode, knowledge, onClose }: Props) {
  const avatar = useRef<AvatarHandle>(null);
  const { messages, status, error, session, pending, handsFree, muted, toggleMute, startMic, stopMic, sendText } =
    useConversation({
    movieId,
    characterId: character.id,
    t,
    mode,
    knowledge,
    onAvatar: (d, onShown) => (avatar.current ? avatar.current.drive(d, onShown) : onShown()), // lip_sync mode only
    onInterrupt: () => avatar.current?.interrupt(),
  });
  const [draft, setDraft] = useState("");
  const [avatarTalking, setAvatarTalking] = useState(false);
  // the character is heard, not read: their lines stay folded to one line until you open them
  const [openLines, setOpenLines] = useState<Set<string>>(() => new Set());
  const toggleLine = (id: string) =>
    setOpenLines((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  // while the user records, the reply that's still talking is turned down (not picked up by the mic)
  useEffect(() => {
    avatar.current?.duck(status === "listening");
  }, [status]);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending, status]);

  const busy = status === "connecting" || status === "error";
  const speaking = status === "speaking" || avatarTalking;
  const live = speaking ? "speaking" : status;
  // hands-free: "your turn" means the mic is listening for you (unless muted)
  const liveLabel =
    handsFree && live === "ready"
      ? muted
        ? "Mic off"
        : "Listening"
      : handsFree && live === "listening"
        ? "Hearing you"
        : STATUS_LABEL[live];
  const send = (text: string) => {
    if (text.trim()) void sendText(text.trim());
  };
  // "J. Robert Oppenheimer" -> "Robert": the first word that isn't an initial
  const callName = character.name.split(" ").find((w) => w.length > 2 && !w.endsWith(".")) ?? character.name;
  const year = session?.as_of_year != null ? Math.floor(session.as_of_year) : null;
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant")?.id;

  return (
    <aside className="chat" aria-label={`Conversation with ${character.name}`}>
      <div className="portrait">
        <AvatarView
          ref={avatar}
          movieId={movieId}
          t={t}
          character={character}
          face={face}
          mode={mode}
          speaking={speaking}
          onPlayingChange={setAvatarTalking}
        />
        <div className="portrait-top">
          <span className="ai-tag">AI voice &amp; likeness</span>
          <button className="close-btn" onClick={onClose} aria-label="Leave the conversation">
            <Icon name="close" size={18} />
          </button>
        </div>
        <div className="portrait-caption">
          <h2 className="lockup">{character.name}</h2>
          <div className={`live-line ${live}`} role="status">
            {speaking ? (
              <span className="voice-bars" aria-hidden>
                <i />
                <i />
                <i />
                <i />
              </span>
            ) : (
              <span className="dot" aria-hidden />
            )}
            {liveLabel}
            <span className="live-sep" aria-hidden />
            <span className="tc">{fmtTime(t)}</span>
          </div>
        </div>
      </div>

      <div className="messages" ref={listRef}>
        <p className="intertitle">
          {knowledge === "omniscient"
            ? "They know how it all ends"
            : year != null
              ? `It is ${year}`
              : `They know the story up to ${fmtTime(t)}`}
        </p>
        {session?.anchored && (
          <p className="intertitle-note">
            This is a flash-forward. So nothing gets spoiled, you are talking to {character.name} as of {year}, as far
            as you have followed the main story.
          </p>
        )}

        {status === "ready" && messages.length === 0 && (
          <div className="opening">
            <p>
              {handsFree
                ? "Ask in any language. Just talk: the mic is on, and you can cut in while they speak. Or type below."
                : "Ask in any language. Type below, or tap the mic, speak, and tap it again to send."}
            </p>
            <div className="suggestions">
              {SUGGESTIONS[knowledge].map((q) => (
                <button key={q} type="button" onClick={() => send(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) =>
          m.role === "assistant" ? (
            <button
              key={m.id}
              type="button"
              className={`line assistant ${openLines.has(m.id) ? "open" : ""} ${m.id === lastAssistant && speaking ? "lit" : ""}`}
              aria-expanded={openLines.has(m.id)}
              onClick={(e) => {
                const el = e.currentTarget;
                toggleLine(m.id);
                requestAnimationFrame(() => el.scrollIntoView({ block: "nearest", behavior: "smooth" }));
              }}
            >
              <span className="line-text">{m.text}</span>
              <span className="line-toggle">{openLines.has(m.id) ? "Hide" : "Show"}</span>
            </button>
          ) : (
            <div key={m.id} className={`line ${m.role}`}>
              <span className="cue">You</span>
              {m.text}
            </div>
          ),
        )}

        {pending > 0 && (
          <div className="checking" aria-label="Checking the next line for spoilers">
            {Array.from({ length: Math.min(pending, 3) }, (_, i) => (
              <i key={i} style={{ width: `${88 - i * 17}%` }} />
            ))}
          </div>
        )}

        {status === "connecting" && <p className="intertitle quiet">Taking their seat</p>}
        {status === "thinking" && pending === 0 && <p className="intertitle quiet thinking">Thinking</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="composer-wrap">
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(draft);
            setDraft("");
          }}
        >
          <div className="composer-field">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={`Ask ${callName} anything`}
              aria-label={`Ask ${character.name}`}
              disabled={busy}
            />
            <button className="send-btn" type="submit" aria-label="Send" disabled={!draft.trim() || busy}>
              <Icon name="send" size={18} />
            </button>
          </div>
          {handsFree ? (
            <MicButton
              listening={!muted}
              handsFree
              disabled={busy}
              onStart={() => void toggleMute()}
              onStop={() => void toggleMute()}
            />
          ) : (
            <MicButton
              listening={status === "listening"}
              disabled={busy}
              onStart={() => void startMic()}
              onStop={() => void stopMic()}
            />
          )}
        </form>
        <p className={`mic-hint ${status === "listening" || muted ? "on" : ""}`} aria-live="polite">
          {handsFree
            ? muted
              ? "Mic off. Tap the mic to talk again."
              : status === "listening"
                ? "Hearing you…"
                : " "
            : status === "listening"
              ? "Recording. Tap the mic again to send."
              : " "}
        </p>
      </div>
    </aside>
  );
}
