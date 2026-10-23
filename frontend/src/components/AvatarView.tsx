import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { api } from "../lib/api";
import { playFmp4Stream } from "../lib/mse";
import type { Character, OutputMode } from "../types";

export interface AvatarHandle {
  drive: (d: { text?: string; audio_b64?: string }) => void;
}

interface Props {
  movieId: string;
  character: Character;
  mode: OutputMode;
  speaking: boolean;
}

/**
 * Shows the character's face. Replies are queued and rendered by Higgs Avatar as fMP4 streams.
 * voice_first: audio already played from Realtime, so the lip-sync clip plays muted (a replay).
 * lip_sync:    the avatar clip *is* the voice (Higgs TTS with the cloned voice), so it's unmuted.
 */
export const AvatarView = forwardRef<AvatarHandle, Props>(function AvatarView(
  { movieId, character, mode, speaking },
  ref,
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const queue = useRef<{ text?: string; audio_b64?: string }[]>([]);
  const busy = useRef(false);
  const [showVideo, setShowVideo] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const pump = async () => {
    if (busy.current || !videoRef.current) return;
    const next = queue.current.shift();
    if (!next) return;
    busy.current = true;
    setShowVideo(true);
    try {
      const res = await api.avatarStream({ movie_id: movieId, character_id: character.id, ...next });
      await playFmp4Stream(videoRef.current, res);
    } catch (e) {
      setErr(String(e));
    } finally {
      busy.current = false;
      if (queue.current.length) void pump();
      else setShowVideo(false);
    }
  };

  useImperativeHandle(ref, () => ({
    drive: (d) => {
      queue.current.push(d);
      void pump();
    },
  }));

  useEffect(() => {
    queue.current = [];
  }, [character.id]);

  return (
    <div className={`avatar ${speaking ? "speaking" : ""}`}>
      {character.face_image ? (
        <img className={showVideo ? "hidden" : ""} src={api.faceUrl(movieId, character.id)} alt={character.name} />
      ) : (
        <div className={`face-placeholder big ${showVideo ? "hidden" : ""}`}>{character.name[0]}</div>
      )}
      <video ref={videoRef} className={showVideo ? "" : "hidden"} muted={mode === "voice_first"} playsInline />
      {err && <div className="avatar-err" title={err}>avatar unavailable</div>}
    </div>
  );
});
