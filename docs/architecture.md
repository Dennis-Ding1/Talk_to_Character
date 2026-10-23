# Architecture

## Goals

1. Pause at time **t**, pick a character, talk by voice or text, in any language.
2. The character answers **as of t**, from **their own point of view**: nothing after t, nothing
   from scenes they weren't in.
3. Character speaks in a **cloned voice**, shown as a **talking-head avatar**.
4. Keep Higgs-native features: realtime speech, barge-in, tool calls, automatic language matching.

## Higgs models

| Model | Endpoint | Notes |
|---|---|---|
| `higgs-realtime` | `wss://api.boson.ai/v1/realtime` | audio in → audio **or** text out; `instructions`; `audio.output.voice = voice_<id>`; `semantic_vad`; function tools; no image input |
| `higgs-stt-3.1` | (inside Realtime) | optional transcript of user speech |
| `higgs-tts-3` | `POST /v1/audio/speech`, `POST /v1/audio/voices` | clone from 5–30 s clean audio + transcript; 100 languages; inline emotion tags |
| `higgs-avatar` | `POST /v1/videos/stream` | `ref_image` + (`input` audio ≤60 s **or** `input_tts`); 640x640 / 640x480 / 480x640; fMP4 stream; **not realtime** |

Browser auth: backend mints an ephemeral key via `POST /v1/realtime/client_secrets`; browser
opens the socket with subprotocols `["realtime", "bai-client-secret.<key>"]`.

## Offline pipeline (`backend/preprocess`)

| Step | Input | Output | Tool |
|---|---|---|---|
| `scenes` | `subtitles.srt` (+ `scene_marks.json`) | `knowledge/scenes.json` | rules (gap ≥ 8 s or hand marks) |
| `summarize` | scenes + cast | summaries, key events, presence; `character_states.json` | local LLM (Ollama + Qwen), or Higgs text mode |
| `faces` | `face_at_s` | `characters/<id>/face.png` | ffmpeg, crop to avatar aspect |
| `voices` | `voice_clip` | `voice_ref.wav`, `voice_ref_text`, `voice_id` | ffmpeg → demucs → faster-whisper → `/v1/audio/voices` |

Each LLM call only sees the current scene + previous state, so generated knowledge never
contains the future.

## Runtime

```
Browser                          Backend (FastAPI)                     Boson
──────                           ─────────────────                     ─────
pause at t ─GET characters?t──►  characters on screen near t
pick char ──POST /api/session─►  knowledge.known_scenes(char, t)
                                 persona.build_instructions()
                                 ── client_secrets ──────────────────►  ephemeral key
          ◄── {secret, session.update payload, history} ──
open WS ─────────────────────────────────────────────────────────────►  higgs-realtime
session.update + replay history
mic PCM16 24k ───────────────────────────────────────────────────────►
          ◄──────────────── audio deltas (cloned voice) / transcripts ─
tool call ─POST /api/tools/x──►  BM25 over known_scenes(char, t)
          ◄── result ──  → function_call_output → response.create
reply ─────POST /api/avatar/stream──► /v1/videos/stream ─────────────►  higgs-avatar
          ◄────────────── fMP4 chunks (MSE) ──────────────────────────
```

### Output modes

- **voice_first** (default): Realtime speaks in the cloned voice immediately. Face shows as a
  still with a speaking ring. Optional "avatar replay" sends the reply's audio to Avatar and plays
  the lip-synced clip muted when ready.
- **lip_sync**: Realtime outputs text only; each reply goes to Avatar with
  `input_tts {voice: voice_id}`, so the video carries voice + lips in sync. Slower but best demo.
  Next step: split replies into sentences and stream the first sentence early.

### Anti-spoiler rules (`app/context/knowledge.py`)

- Scenes with `start ≥ t` are dropped.
- A scene in progress at t keeps only lines before t and **loses its summary** (it was written
  with the whole scene in view).
- Scenes where the character isn't in `characters_present` are dropped (POV).
- Character state = latest checkpoint with `t_checkpoint ≤ t`.
- Tools (`recall_scene`, `get_relationship`) use the same filter.
- The prompt also forbids outside knowledge of the film (LLMs may know famous plots).

Tested in `backend/tests/test_knowledge.py`.

## Open questions / TODO

- Exact fMP4 codec string from Higgs Avatar (for `MediaSource.isTypeSupported`).
- Avatar time-to-first-frame → decides whether lip_sync is usable live.
- Context window of `higgs-realtime` → how many scene summaries fit.
- Cross-lingual quality of cloned voices (e.g. Chinese actor speaking English).
- Multi-character group chat; "what if" mode; emotion tags from scene mood.
- SRT → WebVTT to show subtitles in the player.
