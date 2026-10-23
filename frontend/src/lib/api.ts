import type { Character, FaceCrop, Movie, OutputMode, SessionResponse } from "../types";

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.url}: ${await r.text()}`);
  return r.json() as Promise<T>;
}

const post = (url: string, body: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  movies: () => fetch("/api/movies").then(json<Movie[]>),

  charactersAt: (movieId: string, t: number) =>
    fetch(`/api/movies/${movieId}/characters?t=${t}`).then(json<Character[]>),

  faces: (movieId: string, t: number) =>
    fetch(`/api/movies/${movieId}/faces?t=${t.toFixed(2)}`).then(json<FaceCrop[]>),

  videoUrl: (movieId: string) => `/api/movies/${movieId}/video`,
  subtitlesUrl: (movieId: string) => `/api/movies/${movieId}/subtitles`,
  faceUrl: (movieId: string, characterId: string) => `/api/movies/${movieId}/characters/${characterId}/face`,

  session: (movieId: string, characterId: string, t: number, mode: OutputMode) =>
    post("/api/session", { movie_id: movieId, character_id: characterId, t, mode }).then(json<SessionResponse>),

  tool: (name: string, movieId: string, characterId: string, t: number, args: unknown) =>
    post(`/api/tools/${name}`, { movie_id: movieId, character_id: characterId, t, arguments: args }).then(
      json<{ result: string }>,
    ),

  saveTurn: (movieId: string, characterId: string, role: "user" | "assistant", text: string, t: number) =>
    post(`/api/memory/${movieId}/${characterId}`, { role, text, t }),

  /** Returns the raw fMP4 stream response (play with lib/mse.ts). */
  avatarStream: (body: {
    movie_id: string;
    character_id: string;
    face_id?: string;
    text?: string;
    audio_b64?: string;
  }) =>
    post("/api/avatar/stream", body),
};
