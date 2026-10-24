import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, KnowledgeMode, OutputMode, SessionResponse } from "../types";
import { api } from "./api";
import { Mic } from "./audio/mic";
import { PcmPlayer } from "./audio/pcm-player";
import { RealtimeSession } from "./realtime";
import { SentenceChunker } from "./sentences";
import { SpeechQueue } from "./speech";

export type Status = "idle" | "connecting" | "ready" | "listening" | "thinking" | "speaking" | "error";

interface Args {
  movieId: string;
  characterId: string;
  t: number;
  mode: OutputMode;
  knowledge: KnowledgeMode;
  /** lip_sync mode: called with each finished reply, to render as a talking-avatar clip. */
  onAvatar?: (drive: { text?: string; audio_b64?: string }) => void;
  /** the user took the turn: stop anything the avatar is still saying */
  onInterrupt?: () => void;
}

/** One conversation with one character, opened at playback time t. */
export function useConversation({ movieId, characterId, t, mode, knowledge, onAvatar, onInterrupt }: Args) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);

  const rt = useRef<RealtimeSession>();
  const mic = useRef<Mic>();
  const player = useRef<PcmPlayer>();
  const responding = useRef(false);
  const transcriptWaiter = useRef<((text: string) => void) | null>(null);
  const speech = useRef<SpeechQueue>();
  const chunkers = useRef(new Map<string, SentenceChunker>());
  const spokenText = useRef(new Map<string, string>()); // reply id -> checked text spoken so far
  const lastQuestion = useRef("");
  const onAvatarRef = useRef(onAvatar);
  onAvatarRef.current = onAvatar;
  const onInterruptRef = useRef(onInterrupt);
  onInterruptRef.current = onInterrupt;

  const upsert = useCallback((id: string, role: ChatMessage["role"], text: string, append = false) => {
    setMessages((ms) => {
      const i = ms.findIndex((m) => m.id === id);
      if (i < 0) return [...ms, { id, role, text }];
      const copy = ms.slice();
      copy[i] = { ...copy[i], text: append ? copy[i].text + text : text };
      return copy;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    setStatus("connecting");
    setMessages([]);
    player.current = new PcmPlayer();
    const base = { movie_id: movieId, character_id: characterId, t, knowledge };
    // think -> check -> speak: every sentence of the reply is spoiler-checked and spoken with the
    // cloned voice by the backend; the chat shows only the checked text, as it is spoken
    const saveSpoken = () => {
      for (const [id, text] of spokenText.current) {
        if (text.trim()) void api.saveTurn(movieId, characterId, knowledge, "assistant", text.trim(), t);
        spokenText.current.delete(id);
      }
    };
    speech.current = new SpeechQueue(player.current, {
      request: (text, signal) => api.speak({ ...base, text, question: lastQuestion.current }, signal),
      onSpoken: (text, _rewritten, id) => {
        const prev = spokenText.current.get(id) ?? "";
        spokenText.current.set(id, prev ? `${prev} ${text}` : text);
        upsert(id, "assistant", prev ? ` ${text}` : text, true);
      },
      onStart: () => setStatus("speaking"),
      onIdle: () => {
        saveSpoken();
        setStatus((s) => (s === "listening" ? s : "ready"));
      },
    });

    (async () => {
      const s = await api.session(movieId, characterId, t, mode, knowledge);
      if (cancelled) return;
      setSession(s);
      if (!s.client_secret) {
        setStatus("error");
        setError("Backend has no BOSON_API_KEY — set it in .env to talk to characters.");
        return;
      }
      const session = new RealtimeSession({
        onUserTranscript: (id, text) => {
          lastQuestion.current = text;
          transcriptWaiter.current?.(text);
          transcriptWaiter.current = null;
          upsert(id, "user", text);
          void api.saveTurn(movieId, characterId, knowledge, "user", text, t);
        },
        onAssistantDelta: (id, d) => {
          if (mode === "lip_sync") return; // spoken as one clip when complete (see onAssistantDone)
          let c = chunkers.current.get(id);
          if (!c) {
            c = new SentenceChunker((sentence) => speech.current?.enqueue(sentence, id));
            chunkers.current.set(id, c);
          }
          c.push(d);
        },
        onAssistantDone: (id, text) => {
          if (mode === "lip_sync") {
            // check the whole reply, then show it and let the avatar speak it
            void api.check({ ...base, text, question: lastQuestion.current }).then(({ text: safe }) => {
              upsert(id, "assistant", safe);
              void api.saveTurn(movieId, characterId, knowledge, "assistant", safe, t);
              onAvatarRef.current?.({ text: safe });
            });
            return;
          }
          chunkers.current.get(id)?.flush();
          chunkers.current.delete(id);
        },
        onResponseDone: () => {
          responding.current = false;
          if (!speech.current?.busy) setStatus((s) => (s === "listening" || s === "thinking" && mode === "lip_sync" ? s : "ready"));
        },
        onToolCall: async (name, args) => {
          responding.current = true; // a follow-up response is created after the tool result
          return (await api.tool(name, movieId, characterId, t, knowledge, args)).result;
        },
        onError: (e) => {
          console.error("realtime error", e);
          setError(typeof e === "object" && e && "message" in e ? String((e as any).message) : "Realtime error");
        },
        onClose: () => setStatus("idle"),
      });
      session.turnNote = s.turn_note;
      await session.connect(s.realtime_url, s.client_secret, s.session, s.history);
      if (cancelled) return session.close();
      rt.current = session;
      setStatus("ready");
    })().catch((e) => {
      if (!cancelled) {
        setStatus("error");
        setError(String(e));
      }
    });

    return () => {
      cancelled = true;
      mic.current?.stop();
      speech.current?.stop();
      player.current?.stop();
      rt.current?.close();
      rt.current = undefined;
    };
  }, [movieId, characterId, t, mode, knowledge, upsert]);

  /** Context attached to this one question (backend: persona.question_notes): the 2 most relevant
   *  memories (same spoiler filter as the prompt) and "you've never met X" for people named in the
   *  question whom the character hasn't met yet. */
  const recallNotes = useCallback(
    async (question: string): Promise<string[]> => {
      if (!question.trim()) return [];
      try {
        return (await api.questionNotes(movieId, characterId, t, knowledge, question)).notes;
      } catch {
        return [];
      }
    },
    [movieId, characterId, t, knowledge],
  );

  /** Cut the character off if they're still answering (user is taking the turn). */
  const interrupt = useCallback(() => {
    speech.current?.stop();
    chunkers.current.clear();
    player.current?.stop();
    onInterruptRef.current?.();
    if (responding.current) {
      rt.current?.cancel();
      responding.current = false;
    }
  }, []);

  /** Push-to-talk, step 1: start recording. Nothing is sent as a turn until stopMic(). */
  const startMic = useCallback(async () => {
    await player.current?.resume();
    interrupt();
    rt.current?.clearAudio();
    const m = new Mic();
    try {
      await m.start((b64) => rt.current?.appendAudio(b64));
    } catch (e) {
      setError(`Microphone unavailable: ${e}`);
      return;
    }
    mic.current = m;
    setError(null);
    setStatus("listening");
  }, [interrupt]);

  /** Push-to-talk, step 2: stop recording and ask the character to answer. */
  const stopMic = useCallback(() => {
    const m = mic.current;
    mic.current = undefined;
    if (!m) return;
    m.stop();
    if (m.seconds < 0.3) {
      rt.current?.clearAudio(); // accidental tap
      setStatus("ready");
      return;
    }
    responding.current = true;
    setStatus("thinking");
    // wait (briefly) for the transcript of what was said, to look up the relevant memories
    const heard = new Promise<string>((resolve) => {
      transcriptWaiter.current = resolve;
      window.setTimeout(() => resolve(""), 1500);
    });
    rt.current?.commitAudio();
    void heard.then(recallNotes).then((notes) => rt.current?.respond(notes));
  }, [recallNotes]);

  const sendText = useCallback(
    async (text: string) => {
      await player.current?.resume();
      interrupt();
      lastQuestion.current = text;
      upsert(`local-${Date.now()}`, "user", text);
      void api.saveTurn(movieId, characterId, knowledge, "user", text, t);
      responding.current = true;
      setStatus("thinking");
      rt.current?.sendText(text, await recallNotes(text));
    },
    [movieId, characterId, t, knowledge, upsert, interrupt, recallNotes],
  );

  return { messages, status, error, session, startMic, stopMic, sendText };
}
