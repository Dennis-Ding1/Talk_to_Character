import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, OutputMode, SessionResponse } from "../types";
import { api } from "./api";
import { Mic } from "./audio/mic";
import { bytesToBase64, pcm16ToWav } from "./audio/pcm";
import { PcmPlayer } from "./audio/pcm-player";
import { RealtimeSession } from "./realtime";

export type Status = "idle" | "connecting" | "ready" | "listening" | "speaking" | "error";

interface Args {
  movieId: string;
  characterId: string;
  t: number;
  mode: OutputMode;
  /** Called with a reply to render as avatar video (lip_sync: text; voice_first: wav base64). */
  onAvatar?: (drive: { text?: string; audio_b64?: string }) => void;
}

/** One conversation with one character, opened at playback time t. */
export function useConversation({ movieId, characterId, t, mode, onAvatar }: Args) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);

  const rt = useRef<RealtimeSession>();
  const mic = useRef<Mic>();
  const player = useRef<PcmPlayer>();
  const onAvatarRef = useRef(onAvatar);
  onAvatarRef.current = onAvatar;

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

    (async () => {
      const s = await api.session(movieId, characterId, t, mode);
      if (cancelled) return;
      setSession(s);
      if (!s.client_secret) {
        setStatus("error");
        setError("Backend has no BOSON_API_KEY — set it in .env to talk to characters.");
        return;
      }
      const session = new RealtimeSession({
        onSpeechStarted: () => {
          // barge-in: cut the character off (server stops generating on its own; we stop local playback)
          if (player.current?.playing) player.current.stop();
        },
        onUserTranscript: (id, text) => {
          upsert(id, "user", text);
          void api.saveTurn(movieId, characterId, "user", text, t);
        },
        onAudioDelta: (b64) => {
          setStatus("speaking");
          player.current?.push(b64);
        },
        onAssistantDelta: (id, d) => upsert(id, "assistant", d, true),
        onAssistantDone: (id, text) => {
          upsert(id, "assistant", text);
          void api.saveTurn(movieId, characterId, "assistant", text, t);
          if (mode === "lip_sync") onAvatarRef.current?.({ text });
        },
        onResponseDone: (st) => {
          setStatus("ready");
          const pcm = player.current?.takeRecording();
          if (mode === "voice_first" && st === "completed" && pcm?.length) {
            onAvatarRef.current?.({ audio_b64: bytesToBase64(pcm16ToWav(pcm)) });
          }
        },
        onToolCall: async (name, args) => (await api.tool(name, movieId, characterId, t, args)).result,
        onError: (e) => {
          console.error("realtime error", e);
          setError(typeof e === "object" && e && "message" in e ? String((e as any).message) : "Realtime error");
        },
        onClose: () => setStatus("idle"),
      });
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
      player.current?.stop();
      rt.current?.close();
      rt.current = undefined;
    };
  }, [movieId, characterId, t, mode, upsert]);

  const startMic = useCallback(async () => {
    await player.current?.resume();
    mic.current = new Mic();
    await mic.current.start((b64) => rt.current?.appendAudio(b64));
    setStatus("listening");
  }, []);

  const stopMic = useCallback(() => {
    mic.current?.stop();
    mic.current = undefined;
    setStatus("ready");
  }, []);

  const sendText = useCallback(
    async (text: string) => {
      await player.current?.resume();
      upsert(`local-${Date.now()}`, "user", text);
      void api.saveTurn(movieId, characterId, "user", text, t);
      rt.current?.sendText(text);
    },
    [movieId, characterId, t, upsert],
  );

  return { messages, status, error, session, startMic, stopMic, sendText };
}
