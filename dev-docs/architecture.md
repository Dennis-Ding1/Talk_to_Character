# Architecture

## Goals

1. Pause at time **t**, click a face (or pick a character), talk by voice or text, in any language.
2. The character answers **as they are at t**, from **their own point of view**: nothing after t,
   nothing from scenes they weren't in. An *Omniscience* mode lifts this for "what if" questions.
3. The character speaks in a **cloned voice**, optionally as a **talking-head avatar** built from
   their look in that very scene.
4. It should feel like a conversation: about a second to the first word, interruptions allowed.

## Higgs models

| Model | Where | Used for |
|---|---|---|
| `higgs-realtime-1.5-preview` | `wss://api.boson.ai/v1/realtime` | The conversation. Audio output in the cloned voice (`voice_<id>`); text output only for movies whose avatar speech uses TTS 3. Semantic VAD in voice mode. |
| `higgs-stt-3.1` | inside Realtime | Transcript of the user's question (memories are looked up from it; echo/noise is filtered on it) |
| `higgs-realtime` (text) | same socket, text only | The spoiler checker, and the optional `higgs_text` LLM backend of the offline pipeline |
| `higgs-tts-3` | `POST /v1/audio/voices`, `/v1/audio/speech` | Voice cloning (reference clip + transcript). Avatar speech with emotion/style tags for `avatar_speech: "tts3"` movies |
| `higgs-avatar` | `POST /v1/videos/stream` | Talking-head clips (fMP4, streamed) and the silent "listening" idle loop |

Browser auth: the backend mints an ephemeral key (`POST /v1/realtime/client_secrets`); the browser
opens the socket with subprotocols `["realtime", "bai-client-secret.<key>"]`. The API key never
reaches the browser.

Model names are set in `.env`: `REALTIME_MODEL`, `GUARD_MODEL`, `REALTIME_TOOLS` (tool calls are
off for 1.5-preview, which sometimes writes them as text; the same context is attached to each
question instead, see *Question notes*).

## Offline pipeline (`backend/preprocess`, `python -m preprocess.cli <step> <movie>`)

| Step | Input | Output |
|---|---|---|
| `screenplay` | `screenplay.pdf` + `subtitles.srt` (+ `story_years.json`) | `knowledge/scenes.json`: scenes aligned to the subtitles (n-gram matching + Viterbi), speaker per line, who is present (minus voice-over narrators), **timed on-screen beats** (action paragraphs placed between aligned lines), story year and thread per scene |
| `scenes` | `subtitles.srt` only | simpler scenes (silence gaps or `scene_marks.json`) when there is no screenplay |
| `summarize` | scenes + cast | per-scene summary and key events; one **first-person state per character per scene** (goals, stance, emotion, relationships) |
| `inner --only a,b` | scenes + summaries | private **inner notes** per scene: what they did, why, what they felt, what they hid |
| `moments` | scenes | time-anchored thoughts inside scenes (`knowledge/moments.json`); hand-curated ones work best |
| `faceindex` | video + scenes | face index (YuNet + SFace), speaker-vote identification, `cache/face_cores.npz`, best **look** of each character per scene (`knowledge/looks.json`, `cache/looks/`) |
| `faces` | `face_at_s` | `characters/<id>/face.png` (a single portrait, when there is no face index) |
| `voices` | a clean line of dialogue | `voice_ref.wav` (ffmpeg → demucs), its transcript, `voice_id` from `/v1/audio/voices`. `--redo` re-registers the existing `voice_ref.wav` under a new API key in seconds |

LLM steps see one scene (plus the character's earlier notes) at a time, so generated knowledge never
contains the future. `LLM_BACKEND` picks `higgs_text` or a local `ollama` model.

Hand-written files that are applied on load (never overwritten by preprocessing):
`knowledge/moments.json` (curated thoughts) and `knowledge/fixes.json` (speaker corrections, beats
to drop). Animated films use `knowledge/animation_faces.json` (colour/eye profile per character)
instead of the face index.

## Runtime

```
Browser                               Backend (FastAPI)                         Boson
pause at t ─ GET frame_faces?t ─────►  recognise faces in this movie's frame
click a face ─ POST /api/session ───►  demo time → film time; knowledge cut at t;
                                       persona.build_instructions(); history at t
                                       ─ client_secrets ──────────────────────►  ephemeral key
          ◄── {secret, session.update, turn_note, history} ──
open WS ──────────────────────────────────────────────────────────────────────►  Realtime 1.5
mic (always on in voice mode) ────────────────────────────────────────────────►  semantic VAD + STT
          ◄────────────────────────────────────────── transcript of the question ─
POST /api/question_notes ───────────►  relevant memories, inner notes, who is who
notes + turn note + response.create ──────────────────────────────────────────►
          ◄──────────────────────────────────── reply audio + transcript (fast) ─
POST /api/check (per sentence) ─────►  spoiler checker ────────────────────────►  Realtime (text)
play when checked  /  POST /api/avatar/stream (wav or text) ──────────────────►  Higgs Avatar
          ◄──────────────────────────────────────────────────── fMP4 chunks (MSE) ─
```

Main endpoints: `GET /api/movies`, `/api/movies/{id}/video|poster|characters?t=|frame_faces?t=|faces/{id}.jpg`,
`POST /api/session`, `/api/question_notes`, `/api/check`, `/api/avatar/stream`, `GET /api/avatar/idle`,
`/api/memory/{movie}/{character}`. (`/api/tools/*` and `/api/speak`, the earlier TTS-per-sentence
path, are still mounted but unused by the current UI.)

### What the character is told (`app/context/persona.py`)

The session instructions, rebuilt for every pause:

- **How you talk**: their real lines as voice samples; plain speech, 2–4 short sentences.
- **Who you are**: bio, personality, `core` (deep drives), the year it is for them.
- **What's going through your head right now**: the latest curated moments before t.
- **What has been going on inside you lately**: inner notes of their last few scenes.
- **Relationships**: only with people they have actually met on screen.
- **Memories**: the scenes they witnessed, oldest first.
- **What just happened**: the last lines and on-screen beats before t.
- **Rules**: these memories are your whole life; nothing after them has happened; stay in
  character; the visitor saw what you did, so be honest about your reasons.

Every turn also gets:

- **Question notes** (`/api/question_notes`): the memories most relevant to *this* question
  (BM25 over the scenes they know), their inner notes for those scenes, and who the people named
  in the question are ("you have never met X", or "they mean Robert, who is right here with you").
- **Turn note**: the year again, plus "you don't know how anything turns out unless it's in your
  memories". The model follows the end of the conversation far better than the system prompt.

### Spoiler safety (Up to now mode)

1. **Knowledge cut** (`knowledge.py`): scenes starting after t are dropped; the scene in progress
   keeps only lines and beats before t and loses its summary; scenes the character wasn't in are
   dropped; the state is the latest one among scenes they were seen in.
2. **Question notes** use the same filter.
3. **Spoiler check** (`guard.py`): each reply sentence is judged against what the viewer has seen
   (finished scenes' key events and on-screen beats, the character's own moments, the current scene
   so far) and what they haven't (upcoming beats of this scene, key events of unseen scenes). To flag
   a sentence the checker must cite the future event it gives away; a safe rewrite may not contain
   names from that event.
4. **Conversation memory** is replayed only at the same pause point (±2 s of film time), so an
   earlier "it hasn't happened yet" is never carried past the moment it happened.

Omniscience mode builds the instructions from the whole story and skips the check.

### Voice mode (hands-free)

- The mic stays open. Semantic VAD ends the turn when the user has finished; `create_response` is
  off, so the browser asks for the reply once the transcript and question notes are in (~0.3 s).
- **Check before speaking**: Realtime writes the transcript several times faster than real time.
  The reply's audio is held until its first sentence passes the check, and never released within
  1.2 s of the user's last words (so a pause mid-question can't produce a half-answer). A later
  sentence that gives something away ends the reply just before it; a first sentence that does is
  replaced with the safe version before anything is heard. First audio: about 1.6–2 s.
- **One answer per question**: if the user carries on talking after a pause, only the full
  question is answered; short or echoed "questions" right after the character spoke are dropped
  and deleted from the conversation.
- **Interruptions**: talking over the character stops them. While they speak, the mic only lets
  through sustained loud speech (a short pre-roll is kept so the first words aren't lost), so their
  own voice from the speakers doesn't interrupt them.

### Avatar mode

- Push-to-talk. The reply is generated as audio in the cloned voice and held; once every sentence
  has passed the check, the **finished audio drives Higgs Avatar** (rendering starts ~2 s sooner
  than from text and runs faster than real time, so 1 s of buffer is enough; see
  `backend/model_speed_test`). About 6–9 s from question to moving lips.
- Movies with `avatar_speech: "tts3"` get text from Realtime instead and render with Higgs TTS 3,
  which adds emotion/style tags (`app/context/delivery.py`); slower, more expressive.
- The face is the character's look in the current scene (face index) or the portrait. A silent
  "listening" loop is rendered once per face and cross-faded under the talking clips. Boson renders
  one clip at a time per API key, so renders are serialised and a superseded one is aborted.

### Demo cuts

A demo cut (`movie.json` with `source` and `segments`) is a short video of chosen scenes. Every
request maps demo time to film time, so knowledge, memories and spoiler checks are exactly those of
the full film. Face recognition grabs the frame from the cut's own video, so the full film's video
isn't needed.

## Tests

`backend/tests`: knowledge cut and point of view, non-linear films, omniscient mode, conversation
history, demo time mapping, delivery tags. `pytest` from `backend/`.

## Measured

| | |
|---|---|
| Voice mode, end of question → first audio | ~1.0 s raw, ~1.6–2 s with check-before-speaking |
| Avatar mode, question → lips moving | ~6–9 s (Realtime audio), ~10 s (TTS 3) |
| Higgs Avatar, audio- vs text-driven | smooth playback 2.3–5.0 s sooner; see `backend/model_speed_test/README.md` |
| Spoiler check per sentence | ~0.5–0.9 s, run in parallel |
| Face recognition on a paused frame | ~1–1.5 s |
