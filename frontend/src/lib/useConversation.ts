import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, KnowledgeMode, OutputMode, SessionResponse } from "../types";
import { api } from "./api";
import { Mic } from "./audio/mic";
import { PcmPlayer } from "./audio/pcm-player";
import { RealtimeSession, detectLanguage } from "./realtime";
import { SentenceChunker } from "./sentences";

export type Status = "idle" | "connecting" | "ready" | "listening" | "thinking" | "speaking" | "error";

/** Hands-free echo guard: while the character is talking, mic audio quieter than this (RMS, 0..1)
 *  is sent as silence, so their voice from the speakers doesn't interrupt them. */
const ECHO_GATE = 0.04;

interface Args {
  movieId: string;
  characterId: string;
  t: number;
  mode: OutputMode;
  knowledge: KnowledgeMode;
  /** lip_sync mode: called with each finished reply, to render as a talking-avatar clip.
   *  Call onShown once the clip starts moving (or fails): that's when the subtitle appears. */
  onAvatar?: (drive: { text?: string; audio_b64?: string }, onShown: () => void) => void;
  /** the user took the turn: stop anything the avatar is still saying */
  onInterrupt?: () => void;
}

/**
 * One conversation with one character, opened at playback time t.
 *
 * voice_first (hands-free): the mic stays on. Higgs Realtime hears the user, detects when they have
 * finished (semantic VAD) and speaks the reply itself in the cloned voice (~1 s). Talking over the
 * character interrupts them. Each sentence of the reply is spoiler-checked as it streams; if one
 * reveals something, the character stops and says the safe version instead.
 *
 * lip_sync (avatar): push-to-talk. Realtime writes the reply as text, the whole reply is
 * spoiler-checked, then the avatar speaks it.
 */
export function useConversation({ movieId, characterId, t, mode, knowledge, onAvatar, onInterrupt }: Args) {
  const handsFree = mode === "voice_first";
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);
  /** lip_sync: a reply is being spoiler-checked / rendered; never shows its text */
  const [pending, setPending] = useState(0);
  /** hands-free: the user turned the mic off */
  const [muted, setMuted] = useState(false);

  const rt = useRef<RealtimeSession>();
  const mic = useRef<Mic>(); // stays open for the whole conversation once opened
  const recording = useRef(false); // push-to-talk: currently recording
  const player = useRef<PcmPlayer>();
  const responding = useRef(false);
  const transcriptWaiter = useRef<((text: string) => void) | null>(null);
  const lastQuestion = useRef("");
  // hands-free reply bookkeeping (keyed by realtime item id)
  const replyId = useRef<string | null>(null); // the reply currently streaming / playing
  const dropped = useRef(new Set<string>()); // interrupted or taken back: ignore late audio/text
  const trusted = useRef(new Set<string>()); // the safe rewrite we asked for: don't check it again
  const trustNext = useRef(false);
  const chunkers = useRef(new Map<string, SentenceChunker>());
  const okText = useRef(new Map<string, string>()); // sentences that passed the check
  const doneTimer = useRef<number>();
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

  /** Context attached to this one question (backend: persona.question_notes): the 2 most relevant
   *  memories (same spoiler filter as the prompt) and who the people named in it are. */
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
    window.clearTimeout(doneTimer.current);
    if (replyId.current) dropped.current.add(replyId.current);
    replyId.current = null;
    chunkers.current.clear();
    setPending(0);
    player.current?.stop();
    onInterruptRef.current?.();
    if (responding.current) {
      rt.current?.cancel();
      responding.current = false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setStatus("connecting");
    setMessages([]);
    setMuted(false);
    dropped.current.clear();
    trusted.current.clear();
    okText.current.clear();
    player.current = new PcmPlayer();
    const base = { movie_id: movieId, character_id: characterId, t, knowledge };
    const checking = knowledge !== "omniscient"; // the ending mode may talk about anything

    const saveReply = (id: string, text: string) => {
      if (text.trim()) void api.saveTurn(movieId, characterId, knowledge, "assistant", text.trim(), t);
      okText.current.delete(id);
    };

    /** A sentence the character already started saying reveals something: stop and say `safe`. */
    const takeBack = (id: string, safe: string) => {
      if (dropped.current.has(id)) return;
      dropped.current.add(id);
      if (replyId.current === id) replyId.current = null;
      chunkers.current.delete(id);
      player.current?.stop();
      if (responding.current) rt.current?.cancel();
      const kept = okText.current.get(id) ?? "";
      upsert(id, "assistant", kept);
      saveReply(id, kept);
      trustNext.current = true;
      responding.current = true;
      rt.current?.say(safe);
    };

    /** hands-free: a reply item is streaming; check its sentences as they complete */
    const checkSentence = (id: string, sentence: string) => {
      void api
        .check({ ...base, text: sentence, question: lastQuestion.current })
        .then((r) => {
          if (r.spoiler) takeBack(id, r.text);
          else if (!dropped.current.has(id)) {
            const prev = okText.current.get(id);
            okText.current.set(id, prev ? `${prev} ${sentence}` : sentence);
          }
        })
        .catch(() => {}); // fail open: never block the conversation on the check
    };

    const startReply = (id: string) => {
      if (replyId.current === id) return;
      replyId.current = id;
      if (trustNext.current) {
        trusted.current.add(id);
        trustNext.current = false;
      } else if (checking) {
        chunkers.current.set(id, new SentenceChunker((s) => checkSentence(id, s), 2, 2));
      }
    };

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
        onSpeechStarted: () => {
          if (!handsFree) return;
          interrupt(); // talking over the character stops them
          setStatus("listening");
        },
        onUserTranscript: (id, text) => {
          if (handsFree) {
            if (!text.trim()) {
              setStatus((st) => (st === "listening" ? "ready" : st)); // noise, not a question
              return;
            }
            lastQuestion.current = text;
            upsert(id, "user", text);
            void api.saveTurn(movieId, characterId, knowledge, "user", text, t);
            responding.current = true;
            setStatus("thinking");
            const lang = detectLanguage(text);
            void recallNotes(text).then((notes) =>
              rt.current?.respond(lang ? [...notes, `(Reply in ${lang}.)`] : notes),
            );
            return;
          }
          lastQuestion.current = text;
          transcriptWaiter.current?.(text);
          transcriptWaiter.current = null;
          upsert(id, "user", text);
          void api.saveTurn(movieId, characterId, knowledge, "user", text, t);
        },
        onAudioDelta: (b64, id) => {
          if (dropped.current.has(id)) return;
          startReply(id);
          window.clearTimeout(doneTimer.current);
          player.current?.push(b64);
          setStatus("speaking");
        },
        onAssistantDelta: (id, d) => {
          if (!handsFree) return; // lip_sync: spoken as one clip when complete (see onAssistantDone)
          if (dropped.current.has(id)) return;
          startReply(id);
          upsert(id, "assistant", d, true);
          chunkers.current.get(id)?.push(d);
        },
        onAssistantDone: (id, text) => {
          if (handsFree) {
            if (dropped.current.has(id)) return;
            const c = chunkers.current.get(id);
            chunkers.current.delete(id);
            c?.flush();
            // saved once the check had its chance on the last sentence
            window.setTimeout(() => {
              if (!dropped.current.has(id)) saveReply(id, text);
            }, c ? 1500 : 0);
            return;
          }
          // lip_sync: check the whole reply, let the avatar speak it, and show the words once its lips move
          setPending(1);
          const settle = () => {
            setPending(0);
            setStatus((st) => (st === "listening" ? st : "ready"));
          };
          void api
            .check({ ...base, text, question: lastQuestion.current })
            .then(({ text: safe }) => {
              let shown = false;
              const reveal = () => {
                if (shown) return;
                shown = true;
                settle();
                upsert(id, "assistant", safe);
                void api.saveTurn(movieId, characterId, knowledge, "assistant", safe, t);
              };
              if (onAvatarRef.current) onAvatarRef.current({ text: safe }, reveal);
              else reveal();
            })
            .catch(settle);
        },
        onResponseDone: () => {
          responding.current = false;
          if (handsFree) {
            // back to "your turn" once the last of the audio has played
            window.clearTimeout(doneTimer.current);
            doneTimer.current = window.setTimeout(
              () => setStatus((st) => (st === "speaking" || st === "thinking" ? "ready" : st)),
              (player.current?.msUntilDone ?? 0) + 80,
            );
            return;
          }
          setStatus((st) => (st === "listening" || st === "thinking" ? st : "ready"));
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
      await player.current?.resume();

      const m = (mic.current ??= new Mic());
      if (handsFree) {
        // hands-free: the mic is on for the whole conversation
        m.gate = () => (player.current?.playing ? ECHO_GATE : 0);
        try {
          await m.start((b64) => rt.current?.appendAudio(b64), { preRoll: false });
          if (cancelled) m.close();
        } catch (e) {
          if (!cancelled) setError(`Microphone unavailable (${e}). You can still type.`);
        }
        return;
      }
      // push-to-talk: if the browser already allows the mic, open it now so the first press is instant
      void navigator.permissions
        ?.query({ name: "microphone" as PermissionName })
        .then((p) => {
          if (p.state === "granted" && !cancelled) return m.open();
        })
        .catch(() => {});
    })().catch((e) => {
      if (!cancelled) {
        setStatus("error");
        setError(String(e));
      }
    });

    return () => {
      cancelled = true;
      window.clearTimeout(doneTimer.current);
      recording.current = false;
      mic.current?.close();
      mic.current = undefined;
      player.current?.stop();
      rt.current?.close();
      rt.current = undefined;
      replyId.current = null;
      chunkers.current.clear();
    };
  }, [movieId, characterId, t, mode, knowledge, handsFree, upsert, interrupt, recallNotes]);

  /** Hands-free: turn the mic off / on. */
  const toggleMute = useCallback(async () => {
    const m = mic.current;
    if (!m) return;
    if (muted) {
      await player.current?.resume();
      rt.current?.clearAudio();
      try {
        await m.start((b64) => rt.current?.appendAudio(b64), { preRoll: false });
        setMuted(false);
        setError(null);
      } catch (e) {
        setError(`Microphone unavailable (${e}). You can still type.`);
      }
    } else {
      await m.stop();
      rt.current?.clearAudio();
      setMuted(true);
      setStatus((st) => (st === "listening" ? "ready" : st));
    }
  }, [muted]);

  /** Push-to-talk, step 1: start recording. Nothing is sent as a turn until stopMic(). */
  const startMic = useCallback(async () => {
    // the half second before the press is sent too, unless the character was still talking
    // (it would be their voice from the speakers)
    const wasTalking = responding.current || !!player.current?.playing;
    await player.current?.resume();
    interrupt();
    rt.current?.clearAudio();
    const m = (mic.current ??= new Mic());
    recording.current = true;
    try {
      await m.start((b64) => rt.current?.appendAudio(b64), { preRoll: !wasTalking });
    } catch (e) {
      recording.current = false;
      mic.current = undefined;
      setError(`Microphone unavailable: ${e}`);
      return;
    }
    if (!recording.current) {
      // stop was pressed while the microphone was still opening
      await m.stop();
      return;
    }
    setError(null);
    setStatus("listening");
  }, [interrupt]);

  /** Push-to-talk, step 2: stop recording and ask the character to answer. */
  const stopMic = useCallback(async () => {
    const m = mic.current;
    if (!m || !recording.current) return;
    recording.current = false;
    await m.stop(); // includes a short tail so the last word isn't cut off
    if (m.seconds < 0.5) {
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

  return { messages, status, error, session, pending, handsFree, muted, toggleMute, startMic, stopMic, sendText };
}
