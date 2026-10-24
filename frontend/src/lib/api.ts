import type { Character, FaceCrop, FrameFace, KnowledgeMode, Movie, OutputMode, SessionResponse } from "../types";

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

  /** faces in the exact paused frame, recognised (click a face to talk) */
  frameFaces: (movieId: string, t: number) =>
    fetch(`/api/movies/${movieId}/frame_faces?t=${t.toFixed(3)}`).then(json<FrameFace[]>),

  videoUrl: (movieId: string) => `/api/movies/${movieId}/video`,
  posterUrl: (movieId: string) => `/api/movies/${movieId}/poster`,
  subtitlesUrl: (movieId: string) => `/api/movies/${movieId}/subtitles`,
  faceUrl: (movieId: string, characterId: string) => `/api/movies/${movieId}/characters/${characterId}/face`,

  session: (movieId: string, characterId: string, t: number, mode: OutputMode, knowledge: KnowledgeMode) =>
    post("/api/session", { movie_id: movieId, character_id: characterId, t, mode, knowledge }).then(
      json<SessionResponse>,
    ),

  tool: (name: string, movieId: string, characterId: string, t: number, knowledge: KnowledgeMode, args: unknown) =>
    post(`/api/tools/${name}`, { movie_id: movieId, character_id: characterId, t, knowledge, arguments: args }).then(
      json<{ result: string }>,
    ),

  /** one sentence -> spoiler check -> cloned-voice PCM stream (X-Spoken-Text = what was said) */
  speak: (
    body: { movie_id: string; character_id: string; t: number; knowledge: KnowledgeMode; text: string; question: string },
    signal?: AbortSignal,
  ) =>
    fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    }),

  /** spoiler check only (lip-sync mode) */
  check: (body: { movie_id: string; character_id: string; t: number; knowledge: KnowledgeMode; text: string; question: string }) =>
    post("/api/check", body).then(json<{ spoiler: boolean; text: string }>),

  /** context to attach to one question: relevant memories + "you've never met X" notes */
  questionNotes: (movieId: string, characterId: string, t: number, knowledge: KnowledgeMode, question: string) =>
    post("/api/question_notes", { movie_id: movieId, character_id: characterId, t, knowledge, question }).then(
      json<{ notes: string[] }>,
    ),

  saveTurn: (
    movieId: string,
    characterId: string,
    knowledge: KnowledgeMode,
    role: "user" | "assistant",
    text: string,
    t: number,
  ) => post(`/api/memory/${movieId}/${characterId}?knowledge=${knowledge}`, { role, text, t }),

  /** Returns the raw fMP4 stream response (play with lib/mse.ts). */
  avatarStream: (body: {
    movie_id: string;
    character_id: string;
    t: number;
    face_id?: string;
    text?: string;
    audio_b64?: string;
  }, signal?: AbortSignal) =>
    fetch("/api/avatar/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    }),
};
