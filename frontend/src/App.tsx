import { useEffect, useRef, useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { FaceOverlay } from "./components/FaceOverlay";
import { Icon } from "./components/Icon";
import { VideoPlayer } from "./components/VideoPlayer";
import { api } from "./lib/api";
import { fmtTime } from "./lib/format";
import type { Character, FaceCrop, FrameFace, KnowledgeMode, Movie, OutputMode } from "./types";

export default function App() {
  const [movies, setMovies] = useState<Movie[]>([]);
  const [movie, setMovie] = useState<Movie | null>(null);
  const [pausedAt, setPausedAt] = useState<number | null>(null);
  const [talkingTo, setTalkingTo] = useState<Character | null>(null);
  const [face, setFace] = useState<FaceCrop | null>(null);
  const [frameFaces, setFrameFaces] = useState<FrameFace[] | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [mode, setMode] = useState<OutputMode>("voice_first");
  const [knowledge, setKnowledge] = useState<KnowledgeMode>("present");
  const [err, setErr] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [clock, setClock] = useState({ t: 0, duration: 0 });
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    api
      .movies()
      .then((ms) => {
        setMovies(ms);
        setMovie(ms.find((m) => m.segments?.length) ?? ms[0] ?? null); // demo cut first
      })
      .catch((e) => setErr(`Backend not reachable: ${e}`));
  }, []);

  /** "Talk to a character": pause here, then find who's on screen and their faces. */
  const startTalk = async () => {
    const v = videoRef.current;
    if (!movie || !v) return;
    v.pause();
    const t = v.currentTime;
    setPausedAt(t);
    setTalkingTo(null);
    setFrameFaces(null);
    setHovered(null);
    // recognising the exact frame takes ~1.5 s; you talk by clicking a lit face on the screen
    api
      .frameFaces(movie.id, t)
      .then((fs) => setFrameFaces((cur) => (videoRef.current?.currentTime === t ? fs : cur)))
      .catch(() => setFrameFaces([]));
  };

  const pick = (c: Character, f: FaceCrop | null) => {
    setFace(f);
    setTalkingTo(c);
  };

  const handlePlay = () => {
    setPlaying(true);
    setPausedAt(null);
    setTalkingTo(null);
  };

  const paused = pausedAt !== null;
  const duration = Number.isFinite(clock.duration) ? clock.duration : 0;
  const lived = paused && duration ? Math.min(pausedAt / duration, 1) : 0;

  return (
    <div className="app" data-house={paused ? "up" : "down"}>
      <header className="topbar">
        <div className="brand">
          <h1>Talk to Character</h1>
          {movies.length > 1 ? (
            <select
              className="movie-select"
              aria-label="Movie"
              value={movie?.id ?? ""}
              onChange={(e) => setMovie(movies.find((m) => m.id === e.target.value) ?? null)}
            >
              {movies.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title}
                </option>
              ))}
            </select>
          ) : (
            movie && <span className="movie-title">{movie.title}</span>
          )}
        </div>
        <div
          className="control"
          title="Present: no spoilers, the character only knows the story up to the pause. Omniscient: they know how it all ends, ask what-if questions."
        >
          <span className="control-label">They know</span>
          <Segmented
            label="What the character knows"
            value={knowledge}
            onChange={setKnowledge}
            options={[
              { value: "present", label: "Up to now" },
              { value: "omniscient", label: "The ending" },
            ]}
          />
        </div>
        <div className="control">
          <span className="control-label">Avatar</span>
          <Segmented
            label="Avatar"
            value={mode}
            onChange={setMode}
            options={[
              { value: "voice_first", label: "Voice" },
              { value: "lip_sync", label: "Lip-sync" },
            ]}
          />
        </div>
      </header>

      {err && <div className="error banner">{err}</div>}

      {movie?.segments && movie.segments.length > 0 && (
        <nav className="chapters" aria-label="Demo chapters">
          {movie.segments.map((s, i) => (
            <button
              key={s.key}
              onClick={() => {
                const v = videoRef.current;
                if (!v) return;
                setPausedAt(null);
                setTalkingTo(null);
                v.currentTime = s.start + 0.6; // just past the fade-in
                void v.play();
              }}
            >
              <span className="chapter-n">{i + 1}</span>
              {s.title}
            </button>
          ))}
        </nav>
      )}

      <main className={talkingTo ? "with-chat" : ""}>
        <div className="stage">
          <div className="screen">
            {movie && (
              <VideoPlayer
                ref={videoRef}
                src={api.videoUrl(movie.id)}
                onPlay={handlePlay}
                onPause={() => setPlaying(false)}
                onTime={(t, d) => setClock({ t, duration: d })}
              />
            )}
            {movie && paused && (
              <FaceOverlay
                videoRef={videoRef}
                faces={frameFaces}
                hoveredId={hovered}
                chosenId={talkingTo?.id ?? null}
                onHover={setHovered}
                onPick={(c) =>
                  pick(c, c.look_id && c.look_url ? { id: c.look_id, url: c.look_url, frame_t: pausedAt, score: 1 } : null)
                }
              />
            )}
          </div>

          {movie && paused && (
            <div className="timeline lived" aria-label={`Paused at ${fmtTime(pausedAt)}. The character knows the story up to here.`}>
              <span className="tc gold">{fmtTime(pausedAt)}</span>
              <div className="lived-track" aria-hidden>
                <div className="lived-fill" style={{ width: `${lived * 100}%` }} />
              </div>
              <span className="lived-label">{knowledge === "omniscient" ? "They know the ending" : "Not yet"}</span>
            </div>
          )}
          {movie && !paused && (
            <div className="timeline transport">
              <button
                className="play-btn"
                aria-label={playing ? "Pause" : "Play"}
                onClick={() => {
                  const v = videoRef.current;
                  if (v) v.paused ? void v.play() : v.pause();
                }}
              >
                <Icon name={playing ? "pause" : "play"} size={18} />
              </button>
              <span className="tc">{fmtTime(clock.t)}</span>
              <input
                type="range"
                className="scrub"
                aria-label="Seek"
                min={0}
                max={duration || 0}
                step={0.1}
                value={Math.min(clock.t, duration || 0)}
                style={{ ["--p" as string]: `${duration ? (clock.t / duration) * 100 : 0}%` }}
                onChange={(e) => {
                  const v = videoRef.current;
                  if (v) v.currentTime = Number(e.target.value);
                }}
              />
              <span className="tc dim">{fmtTime(duration)}</span>
              <button className="talk-btn" onClick={() => void startTalk()}>
                <Icon name="pauseTalk" />
                Pause &amp; talk
              </button>
            </div>
          )}
        </div>
        {movie && talkingTo && paused && (
          <ChatPanel
            key={`${talkingTo.id}@${pausedAt}/${knowledge}`}
            movieId={movie.id}
            character={talkingTo}
            face={face}
            t={pausedAt}
            mode={mode}
            knowledge={knowledge}
            onClose={() => setTalkingTo(null)}
          />
        )}
      </main>
    </div>
  );
}

function Segmented<T extends string>({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          className={value === o.value ? "on" : ""}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
