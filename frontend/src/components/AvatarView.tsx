import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { api } from "../lib/api";
import { playFmp4Stream } from "../lib/mse";
import type { Character, FaceCrop, OutputMode } from "../types";

export interface AvatarHandle {
  /** A new reply to speak. If the previous reply is still playing, it keeps talking until this one
   *  is ready, then this one cross-fades over it (no silent gap). */
  drive: (d: { text?: string; audio_b64?: string }, onShown?: () => void) => void;
  /** The user took the turn: forget replies that haven't started yet; whatever is speaking now
   *  carries on until the next reply is ready (see drive). */
  interrupt: () => void;
  /** Turn the speaking clip down while the user records with the mic. */
  duck: (on: boolean) => void;
}

interface Props {
  movieId: string;
  t: number;
  character: Character;
  face: FaceCrop | null; // look at the pause point; falls back to the portrait
  mode: OutputMode;
  speaking: boolean;
  onPlayingChange?: (playing: boolean) => void;
}

/**
 * The character's face, never a black screen and never a hard cut. Stacked layers:
 *   photo        — shown instantly
 *   idle loop    — (lip_sync) Higgs Avatar driven by silence: blinks, small head motion, mouth closed;
 *                  a forward-only cross-faded loop. Fades in once loaded.
 *   talk A / B   — reply clips, streamed. A new clip fades in on top only once it is playing; the one
 *                  underneath (an older reply still talking, or the idle loop) stays until then.
 * All clips are rendered from the same photo, so the cross-fades are nearly invisible.
 * Boson renders one clip at a time per account, so each reply is a single clip.
 */
export const AvatarView = forwardRef<AvatarHandle, Props>(function AvatarView(
  { movieId, t, character, face, mode, speaking, onPlayingChange },
  ref,
) {
  const talk = [useRef<HTMLVideoElement>(null), useRef<HTMLVideoElement>(null)];
  const [idleOn, setIdleOn] = useState(false);
  const [shown, setShown] = useState<[boolean, boolean]>([false, false]);
  const [top, setTop] = useState<0 | 1>(0);
  const [err, setErr] = useState<string | null>(null);

  const playingSlot = useRef<0 | 1 | null>(null); // which talk layer is currently speaking
  const pending = useRef<AbortController | null>(null); // the next reply, rendering / buffering
  const slotCtrl = useRef<(AbortController | null)[]>([null, null]); // per talk layer: kill it
  const slotFinish = useRef<(AbortController | null)[]>([null, null]); // per talk layer: stop download
  const ducked = useRef(false);
  const onPlayingRef = useRef(onPlayingChange);
  onPlayingRef.current = onPlayingChange;

  const show = (slot: 0 | 1, on: boolean) => setShown((s) => (slot === 0 ? [on, s[1]] : [s[0], on]));

  // onShown: called once, when this clip's first frame is on screen, or when it fails / is dropped
  const start = async (body: { text?: string; audio_b64?: string }, onShown?: () => void) => {
    setErr(null);
    let shownCalled = false;
    const shown = () => {
      if (shownCalled) return;
      shownCalled = true;
      onShown?.();
    };
    // only the newest reply matters: a reply that hasn't started playing yet is dropped
    pending.current?.abort();
    const ctrl = new AbortController();
    pending.current = ctrl;
    const slot: 0 | 1 = playingSlot.current === 0 ? 1 : 0;
    slotCtrl.current[slot] = ctrl;
    const finish = new AbortController();
    slotFinish.current[slot] = finish;
    const el = talk[slot].current!;
    el.pause();
    el.muted = mode === "voice_first";
    el.volume = ducked.current ? 0.15 : 1;
    try {
      const res = await api.avatarStream(
        { movie_id: movieId, character_id: character.id, t, face_id: face?.id, ...body },
        ctrl.signal,
      );
      await playFmp4Stream(el, res, {
        signal: ctrl.signal,
        finish: finish.signal,
        // driven by finished audio, Higgs Avatar renders ~1.3x faster than real time, so playback
        // never catches up and 1 s of buffer is enough; from text it renders at ~1x and needs 3 s
        startBuffer: body.audio_b64 ? 1.0 : 3.0,
        onStart: () => {
          if (ctrl.signal.aborted) return;
          // cross-fade over whatever is underneath, then silence and hide the previous reply
          const prev = playingSlot.current;
          playingSlot.current = slot;
          pending.current = null;
          setTop(slot);
          show(slot, true);
          onPlayingRef.current?.(true);
          shown(); // the lips are moving: now the subtitle may appear
          if (prev !== null && prev !== slot) {
            window.setTimeout(() => {
              talk[prev].current?.pause();
              show(prev, false);
              slotCtrl.current[prev]?.abort(); // stop downloading the superseded reply
            }, 300);
          }
        },
      });
    } catch (e) {
      if (!ctrl.signal.aborted) setErr(String(e));
    } finally {
      shown(); // failed or dropped before it started: show the words anyway
      if (playingSlot.current === slot && !ctrl.signal.aborted) {
        // finished speaking: fade out to the idle loop (unless a newer reply already took over)
        playingSlot.current = null;
        show(slot, false);
        onPlayingRef.current?.(false);
      }
      if (pending.current === ctrl) pending.current = null;
    }
  };

  useImperativeHandle(ref, () => ({
    drive: (d, onShown) => {
      void start(d, onShown);
    },
    interrupt: () => {
      pending.current?.abort(); // a reply that hasn't started playing is obsolete now
      pending.current = null;
      // The reply that is speaking keeps going with what's already buffered (~3 s), but stops
      // downloading: Boson renders one clip at a time, and this frees the slot for the next reply
      // right away instead of after the old one is fully rendered.
      const s = playingSlot.current;
      if (s !== null) slotFinish.current[s]?.abort();
    },
    duck: (on) => {
      ducked.current = on;
      talk.forEach((v) => {
        if (v.current) v.current.volume = on ? 0.15 : 1;
      });
    },
  }));

  useEffect(() => {
    setIdleOn(false);
    setErr(null);
    return () => {
      pending.current?.abort();
      talk.forEach((v) => v.current?.pause());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [character.id, face?.id]);

  const photo = face ? face.url : character.face_image ? api.faceUrl(movieId, character.id) : null;
  const idleSrc =
    mode === "lip_sync" && photo
      ? `/api/avatar/idle?movie_id=${movieId}&character_id=${character.id}${face ? `&face_id=${face.id}` : ""}`
      : null;

  return (
    <div className={`avatar ${speaking ? "speaking" : ""}`}>
      {photo ? (
        <img className="avatar-layer on" src={photo} alt={character.name} />
      ) : (
        <div className="face-placeholder big avatar-layer on">{character.name[0]}</div>
      )}
      {idleSrc && (
        <video
          key={idleSrc}
          className={`avatar-layer ${idleOn ? "on" : ""}`}
          src={idleSrc}
          autoPlay
          loop
          muted
          playsInline
          onPlaying={() => setIdleOn(true)}
        />
      )}
      {[0, 1].map((i) => (
        <video
          key={i}
          ref={talk[i]}
          className={`avatar-layer talk ${shown[i] ? "on" : ""}`}
          style={{ zIndex: top === i ? 3 : 2 }}
          playsInline
        />
      ))}
      {err && (
        <div className="avatar-err" title={err}>
          avatar unavailable
        </div>
      )}
    </div>
  );
});
