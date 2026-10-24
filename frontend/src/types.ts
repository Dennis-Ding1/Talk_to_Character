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
  /** best face of this character as they look at the pause point (face index), if available */
  look_id?: string | null;
  look_url?: string | null;
}

export type OutputMode = "voice_first" | "lip_sync";

/** present: spoiler-safe, as of the pause point. omniscient: knows the whole story (what-if). */
export type KnowledgeMode = "present" | "omniscient";

export interface SessionResponse {
  client_secret: string | null;
  realtime_url: string;
  session: Record<string, unknown>;
  character: Character;
  history: Record<string, unknown>[];
  turn_note: string;
  as_of_year: number | null;
  anchored: boolean;
  knowledge: KnowledgeMode;
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

/** A face in the exact paused frame. box = [x, y, w, h] normalised to the video frame. */
export interface FrameFace {
  box: [number, number, number, number];
  character_id: string | null;
  confidence: number;
  face_id: string;
  face_url: string;
  /** recognised character, with their best photo at this moment as look_url */
  character: Character | null;
}
