// Mirrors backend/app/schemas.py

export interface Movie {
  id: string;
  title: string;
  language: string;
  duration_s?: number | null;
}

export interface Character {
  id: string;
  name: string;
  aliases: string[];
  bio: string;
  face_image?: string | null;
  voice_id?: string | null;
}

export type OutputMode = "voice_first" | "lip_sync";

export interface SessionResponse {
  client_secret: string | null;
  realtime_url: string;
  session: Record<string, unknown>;
  character: Character;
  history: Record<string, unknown>[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  pending?: boolean;
}

/** A face cropped from the frames just before the pause point (the character's look right now). */
export interface FaceCrop {
  id: string;
  url: string;
  frame_t: number;
  score: number;
}
