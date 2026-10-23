import { useEffect, useRef, useState } from "react";
import { CharacterPicker } from "./components/CharacterPicker";
import { ChatPanel } from "./components/ChatPanel";
import { VideoPlayer } from "./components/VideoPlayer";
import { api } from "./lib/api";
import type { Character, FaceCrop, Movie, OutputMode } from "./types";

export default function App() {
  const [movies, setMovies] = useState<Movie[]>([]);
  const [movie, setMovie] = useState<Movie | null>(null);
  const [pausedAt, setPausedAt] = useState<number | null>(null);
  const [onScreen, setOnScreen] = useState<Character[]>([]);
  const [talkingTo, setTalkingTo] = useState<Character | null>(null);
  const [faces, setFaces] = useState<FaceCrop[] | null>(null);
  const [face, setFace] = useState<FaceCrop | null>(null);
  const [mode, setMode] = useState<OutputMode>("voice_first");
  const [err, setErr] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    api
      .movies()
      .then((ms) => {
        setMovies(ms);
        setMovie(ms[0] ?? null);
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
    setFaces(null);
    // faces take a few seconds (frame sampling + detection); don't block the picker on them
    api
      .faces(movie.id, t)
      .then(setFaces)
      .catch(() => setFaces([]));
    setOnScreen(await api.charactersAt(movie.id, t));
  };

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
        <label>
          Mode{" "}
          <select value={mode} onChange={(e) => setMode(e.target.value as OutputMode)}>
            <option value="voice_first">Voice first (fast)</option>
            <option value="lip_sync">Lip-sync avatar (slower)</option>
          </select>
        </label>
      </header>

      {err && <div className="error">{err}</div>}

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
            <CharacterPicker
              movieId={movie.id}
              characters={onScreen}
              faces={faces}
              onPick={(c, f) => {
                setFace(f);
                setTalkingTo(c);
              }}
              onClose={() => setPausedAt(null)}
            />
          )}
        </div>
        {movie && talkingTo && pausedAt !== null && (
          <ChatPanel
            key={`${talkingTo.id}@${pausedAt}`}
            movieId={movie.id}
            character={talkingTo}
            face={face}
            t={pausedAt}
            mode={mode}
            onClose={() => setTalkingTo(null)}
          />
        )}
      </main>
    </div>
  );
}
