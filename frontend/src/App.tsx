import { useEffect, useRef, useState } from "react";
import { CharacterPicker } from "./components/CharacterPicker";
import { ChatPanel } from "./components/ChatPanel";
import { FaceOverlay } from "./components/FaceOverlay";
import { VideoPlayer } from "./components/VideoPlayer";
import { api } from "./lib/api";
import type { Character, FaceCrop, FrameFace, KnowledgeMode, Movie, OutputMode } from "./types";

export default function App() {
  const [movies, setMovies] = useState<Movie[]>([]);
  const [movie, setMovie] = useState<Movie | null>(null);
  const [pausedAt, setPausedAt] = useState<number | null>(null);
  const [onScreen, setOnScreen] = useState<Character[]>([]);
  const [talkingTo, setTalkingTo] = useState<Character | null>(null);
  const [face, setFace] = useState<FaceCrop | null>(null);
  const [frameFaces, setFrameFaces] = useState<FrameFace[] | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [mode, setMode] = useState<OutputMode>("voice_first");
  const [knowledge, setKnowledge] = useState<KnowledgeMode>("present");
  const [err, setErr] = useState<string | null>(null);
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
    // recognising the exact frame takes ~1.5 s; the character cards (precomputed) show instantly
    api
      .frameFaces(movie.id, t)
      .then((fs) => setFrameFaces((cur) => (videoRef.current?.currentTime === t ? fs : cur)))
      .catch(() => setFrameFaces([]));
    setOnScreen(await api.charactersAt(movie.id, t));
  };

  const pick = (c: Character, f: FaceCrop | null) => {
    setFace(f);
    setTalkingTo(c);
  };

  /** Faces recognised in the frame come first in the cards, then everyone else in the scene. */
  const recognised = (frameFaces ?? []).flatMap((f) => (f.character ? [f.character] : []));
  const cards = [...recognised, ...onScreen.filter((c) => !recognised.some((r) => r.id === c.id))];

  const handlePlay = () => {
    setPausedAt(null);
    setTalkingTo(null);
  };

  return (
    <div className="app">
      <header className="topbar">
        <h1>Talk to Character</h1>
        <select value={movie?.id ?? ""} onChange={(e) => setMovie(movies.find((m) => m.id === e.target.value) ?? null)}>
          {movies.map((m) => (
            <option key={m.id} value={m.id}>
              {m.title}
            </option>
          ))}
        </select>
        <label title="Present: no spoilers, the character only knows the story up to the pause. Omniscient: they know how it all ends, ask what-if questions.">
          Knowledge{" "}
          <select value={knowledge} onChange={(e) => setKnowledge(e.target.value as KnowledgeMode)}>
            <option value="present">Present (no spoilers)</option>
            <option value="omniscient">Omniscient (what if…?)</option>
          </select>
        </label>
        <label>
          Avatar{" "}
          <select value={mode} onChange={(e) => setMode(e.target.value as OutputMode)}>
            <option value="voice_first">Voice first (fast)</option>
            <option value="lip_sync">Lip-sync avatar (slower)</option>
          </select>
        </label>
      </header>

      {err && <div className="error">{err}</div>}

      {movie?.segments && movie.segments.length > 0 && (
        <nav className="chapters">
          {movie.segments.map((s) => (
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
              <span>{s.emoji}</span> {s.title}
            </button>
          ))}
        </nav>
      )}

      <main className={talkingTo ? "with-chat" : ""}>
        <div className="stage">
          {movie && (
            <VideoPlayer ref={videoRef} src={api.videoUrl(movie.id)} onPlay={handlePlay} />
          )}
          {movie && pausedAt === null && (
            <button className="talk-btn" onClick={() => void startTalk()}>
              💬 Talk to a character
            </button>
          )}
          {movie && pausedAt !== null && !talkingTo && (
            <>
              <FaceOverlay
                videoRef={videoRef}
                faces={frameFaces}
                hoveredId={hovered}
                onHover={setHovered}
                onPick={(c) =>
                  pick(c, c.look_id && c.look_url ? { id: c.look_id, url: c.look_url, frame_t: pausedAt, score: 1 } : null)
                }
              />
              <CharacterPicker
                movieId={movie.id}
                t={pausedAt}
                characters={cards}
                hoveredId={hovered}
                onHover={setHovered}
                onPick={pick}
                onClose={() => setPausedAt(null)}
              />
            </>
          )}
        </div>
        {movie && talkingTo && pausedAt !== null && (
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
