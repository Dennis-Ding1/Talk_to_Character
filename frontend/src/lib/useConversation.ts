import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, KnowledgeMode, OutputMode, SessionResponse } from "../types";
import { api } from "./api";
import { Mic } from "./audio/mic";
import { base64ToBytes, bytesToBase64, pcm16ToWav } from "./audio/pcm";
import { PcmPlayer } from "./audio/pcm-player";
import { RealtimeSession, detectLanguage } from "./realtime";
import { SentenceChunker } from "./sentences";

export type Status = "idle" | "connecting" | "ready" | "listening" | "thinking" | "speaking" | "error";

/** Hands-free echo guard: while the character is talking, mic audio quieter than this (RMS, 0..1)
 *  is sent as silence, so their voice from the speakers doesn't interrupt them. */
const ECHO_GATE = 0.04;
/** Hands-free: if the first sentence's spoiler check takes longer than this, speak anyway. */
const FIRST_CHECK_MS = 1200;
/** Hands-free: a reply stays silent until the user has been quiet this long, so a pause mid-question
 *  (which ends the turn early) never lets a half-answer be heard before they carry on. */
const AFTER_USER_MS = 1200;

/** One hands-free reply as it streams. Realtime writes the transcript several times faster than the
 *  audio plays, so each sentence is checked long before it is heard: the reply's audio is held until
 *  its first sentence passes, and a later sentence that gives something away is cut before it starts. */
interface Reply {
  id: string;
  checked: boolean; // spoiler-checked sentence by sentence (false: trusted rewrite / ending mode)
  released: boolean; // audio may play
  held: string[]; // audio waiting for the first sentence's check
  playStart: number | null; // AudioContext time the reply starts sounding
  textLen: number; // transcript characters so far
  emitted: number; // characters handed to the checker so far
  audioS: number; // seconds of audio received
  sentences: number;
  ok: string; // text that passed (what the chat shows)
  done: boolean; // response finished
  saved: boolean; // written to the conversation memory (once)
  chunker?: SentenceChunker;
  // avatar mode: the whole reply is checked before the avatar renders it
  checks: Promise<{ index: number; spoiler: boolean; text: string; sentence: string }>[];
}

interface Args {
  movieId: string;
  avatarSpeech: "realtime" | "tts3";
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
export function useConversation({ movieId, avatarSpeech, characterId, t, mode, knowledge, onAvatar, onInterrupt }: Args) {
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
  const replies = useRef(new Map<string, Reply>());
  const current = useRef<string | null>(null); // the reply currently streaming / playing
  const dropped = useRef(new Set<string>()); // interrupted or taken back: ignore late audio/text
  const trustNext = useRef(false); // the next reply is the safe rewrite we asked for
  const secPerChar = useRef(0.06); // speech seconds per transcript character (refined per reply)
  const doneTimer = useRef<number>();
  // hands-free turn taking: one answer per thing the user says
  const turnSeq = useRef(0); // bumped whenever the user starts talking
  const audioEndAt = useRef(0); // when the character last stopped talking (ms)
  const userDoneAt = useRef(0); // when the user's last utterance was transcribed (ms)
  const recentReplies = useRef<string[]>([]); // what the character just said (to spot echo)
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
    if (current.current) dropped.current.add(current.current);
    current.current = null;
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
    replies.current.clear();
    player.current = new PcmPlayer();
    const base = { movie_id: movieId, character_id: characterId, t, knowledge };
    const checking = knowledge !== "omniscient"; // the ending mode may talk about anything
    const transcripts = new Map<string, string>(); // avatar mode: full reply text by item id

    const saveReply = (r: Reply, text: string) => {
      if (r.saved) return;
      r.saved = true;
      if (text.trim()) void api.saveTurn(movieId, characterId, knowledge, "assistant", text.trim(), t);
    };

    /** Hands-free: is this "question" really the character's own voice (echo) or noise? */
    const isNoise = (text: string) => {
      const words = (text.toLowerCase().match(/[\p{L}\p{N}']+/gu) ?? []).filter((w) => w.length > 1 || /\p{Script=Han}/u.test(w));
      if (!words.length) return true;
      const justSpoke = Date.now() - audioEndAt.current < 2500 || !!player.current?.playing;
      if (words.length <= 2 && !text.includes("?") && justSpoke) return true; // "Poor." right after they spoke
      if (words.length >= 3) {
        const said = new Set(recentReplies.current.join(" ").toLowerCase().match(/[\p{L}\p{N}']+/gu) ?? []);
        const echoed = words.filter((w) => said.has(w)).length / words.length;
        if (echoed >= 0.7 && justSpoke) return true; // their own words, heard through the speakers
      }
      return false;
    };

    /** back to "your turn" once the last of the audio has played */
    const scheduleReady = () => {
      window.clearTimeout(doneTimer.current);
      doneTimer.current = window.setTimeout(() => {
        audioEndAt.current = Date.now();
        setStatus((st) => (st === "speaking" || st === "thinking" ? "ready" : st));
      }, (player.current?.msUntilDone ?? 0) + 80);
    };

    const play = (r: Reply, b64: string) => {
      const at = player.current?.push(b64) ?? null;
      if (r.playStart === null && at !== null) r.playStart = at;
      window.clearTimeout(doneTimer.current);
      setStatus("speaking");
    };

    const release = (r: Reply) => {
      if (r.released || dropped.current.has(r.id)) return;
      const wait = userDoneAt.current + AFTER_USER_MS - Date.now();
      if (handsFree && wait > 0) {
        window.setTimeout(() => release(r), wait); // the user may still be mid-question
        return;
      }
      r.released = true;
      for (const b of r.held) play(r, b);
      r.held = [];
      if (r.done) scheduleReady();
    };

    /** The first sentence gives something away and nothing has been heard yet: the character says
     *  the safe version instead (the listener hears one answer). */
    const replaceReply = (r: Reply, safe: string) => {
      if (dropped.current.has(r.id)) return;
      console.info("[spoiler check] first sentence replaced with:", safe);
      dropped.current.add(r.id);
      if (current.current === r.id) current.current = null;
      r.held = [];
      if (responding.current) rt.current?.cancel();
      upsert(r.id, "assistant", "");
      trustNext.current = true;
      responding.current = true;
      rt.current?.say(safe);
    };

    /** A later sentence gives something away: the reply simply ends before it. Nothing is added,
     *  so it still sounds like one answer; the sentences already heard stay in the chat. */
    const endReplyEarly = (r: Reply) => {
      if (dropped.current.has(r.id)) return;
      console.info("[spoiler check] reply ends before a spoiler");
      dropped.current.add(r.id);
      if (current.current === r.id) current.current = null;
      r.held = [];
      player.current?.stop();
      if (responding.current) rt.current?.cancel();
      responding.current = false;
      upsert(r.id, "assistant", r.ok);
      saveReply(r, r.ok);
      recentReplies.current = [...recentReplies.current, r.ok].slice(-2);
      scheduleReady();
    };

    const onSentence = (r: Reply, sentence: string) => {
      const index = r.sentences++;
      const offset = r.emitted; // where this sentence starts in the transcript
      r.emitted += sentence.length + 1;
      const failOpen = index === 0 ? window.setTimeout(() => release(r), FIRST_CHECK_MS) : undefined;
      void api
        .check({ ...base, text: sentence, question: lastQuestion.current })
        .then((res) => {
          window.clearTimeout(failOpen);
          if (dropped.current.has(r.id)) return;
          if (!res.spoiler) {
            r.ok = r.ok ? `${r.ok} ${sentence}` : sentence;
            upsert(r.id, "assistant", r.ok);
            if (index === 0) release(r);
            return;
          }
          if (!r.released || r.playStart === null) return replaceReply(r, res.text); // nothing heard yet
          // end just before this sentence would start sounding
          const startsAt = r.playStart + offset * secPerChar.current;
          const ms = player.current ? player.current.msUntil(startsAt) - 60 : 0;
          window.setTimeout(() => endReplyEarly(r), Math.max(0, ms));
        })
        .catch(() => {
          window.clearTimeout(failOpen);
          if (index === 0) release(r); // never block the conversation on the check
        });
    };

    /** avatar mode: check each sentence as the transcript streams (well before the audio is done) */
    const onAvatarSentence = (r: Reply, sentence: string) => {
      const index = r.sentences++;
      r.checks.push(
        api
          .check({ ...base, text: sentence, question: lastQuestion.current })
          .then((res) => ({ index, spoiler: res.spoiler, text: res.text, sentence }))
          .catch(() => ({ index, spoiler: false, text: sentence, sentence })), // fail open
      );
    };

    /** avatar mode: after the full spoiler check, drive the avatar with Realtime audio by default
     *  or with text for a movie opted into TTS 3. A spoiler triggers a safe rewrite first. */
    const finishAvatar = async (r: Reply, transcript: string) => {
      const results = (await Promise.all(r.checks)).sort((a, b) => a.index - b.index);
      if (dropped.current.has(r.id)) return;
      const bad = results.find((x) => x.spoiler);
      if (bad) {
        console.info("[spoiler check] avatar reply re-said with:", bad.text);
        dropped.current.add(r.id);
        const kept = results.filter((x) => x.index < bad.index).map((x) => x.sentence);
        trustNext.current = true;
        responding.current = true;
        rt.current?.say([...kept, bad.text].join(" "));
        return;
      }
      const text = transcript.trim();
      const settle = () => {
        setPending(0);
        setStatus((st) => (st === "listening" ? st : "ready"));
      };
      let shown = false;
      const reveal = () => {
        if (shown) return;
        shown = true;
        settle();
        upsert(r.id, "assistant", text);
        void api.saveTurn(movieId, characterId, knowledge, "assistant", text, t);
      };
      if (!text || !onAvatarRef.current) return reveal();
      if (avatarSpeech === "tts3") {
        r.held = [];
        onAvatarRef.current({ text }, reveal);
        return;
      }
      const parts = r.held.map(base64ToBytes);
      r.held = [];
      const pcm = new Uint8Array(parts.reduce((n, b) => n + b.length, 0));
      let at = 0;
      for (const b of parts) {
        pcm.set(b, at);
        at += b.length;
      }
      if (!pcm.length) return reveal();
      onAvatarRef.current({ audio_b64: bytesToBase64(pcm16ToWav(pcm)) }, reveal);
    };

    const replyFor = (id: string): Reply => {
      const known = replies.current.get(id);
      if (known) return known;
      const trusted = trustNext.current || !checking;
      trustNext.current = false;
      const r: Reply = {
        id, checked: !trusted, released: trusted, held: [], playStart: null,
        textLen: 0, emitted: 0, audioS: 0, sentences: 0, ok: "", done: false, saved: false, checks: [],
      };
      if (r.checked) {
        r.chunker = new SentenceChunker(
          (sentence) => (handsFree ? onSentence(r, sentence) : onAvatarSentence(r, sentence)),
          2,
          2,
        );
      }
      replies.current.set(id, r);
      current.current = id;
      return r;
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
          turnSeq.current++; // anything not answered yet waits for the end of this
          interrupt(); // talking over the character stops them
          setStatus("listening");
        },
        onUserTranscript: (id, text) => {
          if (handsFree) {
            if (isNoise(text)) {
              console.info("[voice] ignored as echo/noise:", text);
              rt.current?.deleteItem(id); // keep it out of the conversation too
              setStatus((st) => (st === "listening" ? "ready" : st));
              return;
            }
            lastQuestion.current = text;
            userDoneAt.current = Date.now();
            upsert(id, "user", text);
            void api.saveTurn(movieId, characterId, knowledge, "user", text, t);
            setStatus("thinking");
            const seq = turnSeq.current;
            const lang = detectLanguage(text);
            void recallNotes(text).then((notes) => {
              // The user carried on talking after a pause: don't answer the first half on its own.
              // The next transcript answers everything they said, in one reply.
              if (seq !== turnSeq.current) {
                console.info("[voice] user kept talking; one answer at the end");
                return;
              }
              responding.current = true;
              rt.current?.respond(lang ? [...notes, `(Reply in ${lang}.)`] : notes);
            });
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
          const r = replyFor(id);
          r.audioS += (b64.length * 3) / 4 / 48000;
          if (handsFree && r.released) play(r, b64);
          else r.held.push(b64); // avatar mode: the whole reply goes to the avatar once it is checked
        },
        onAssistantDelta: (id, d) => {
          if (dropped.current.has(id)) return;
          const r = replyFor(id);
          r.textLen += d.length;
          if (r.chunker) r.chunker.push(d);
          else if (handsFree) upsert(id, "assistant", d, true); // not checked: show as it comes
        },
        onAssistantDone: (id, text) => {
          if (handsFree) {
            const r = replies.current.get(id);
            if (!r || dropped.current.has(id)) return;
            r.chunker?.flush();
            r.chunker = undefined;
            if (r.sentences === 0) release(r); // nothing to check
            recentReplies.current = [...recentReplies.current, text].slice(-2);
            // saved once the checks had their chance on the last sentences
            window.setTimeout(() => {
              if (!dropped.current.has(id)) saveReply(r, r.checked ? r.ok : text);
            }, r.checked ? 1500 : 0);
            return;
          }
          // avatar mode: the last sentence goes to the checker; the avatar starts once the response is done
          const r = replies.current.get(id);
          if (!r || dropped.current.has(id)) return;
          r.chunker?.flush();
          r.chunker = undefined;
          transcripts.set(id, text);
        },
        onResponseDone: (respStatus) => {
          responding.current = false;
          if (!handsFree) {
            const r = current.current ? replies.current.get(current.current) : undefined;
            if (!r || respStatus === "cancelled" || dropped.current.has(r.id)) return;
            r.done = true;
            setPending(1); // "checking" until the avatar starts speaking
            void finishAvatar(r, transcripts.get(r.id) ?? "");
            return;
          }
          if (handsFree) {
            const r = current.current ? replies.current.get(current.current) : undefined;
            if (r) {
              r.done = true;
              if (r.textLen > 40 && r.audioS > 1) {
                secPerChar.current = 0.7 * secPerChar.current + (0.3 * r.audioS) / r.textLen;
              }
              if (!r.released) return; // audio still held: "ready" is scheduled when it is released
            }
            scheduleReady();
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
      current.current = null;
      replies.current.clear();
    };
  }, [movieId, avatarSpeech, characterId, t, mode, knowledge, handsFree, upsert, interrupt, recallNotes]);

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
