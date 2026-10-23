# Talk to Character 🎬🗣️

Pause any movie and talk to the character on screen — in their cloned voice, with a talking-head
avatar, knowing **only what they know at that moment** in the story. Ask in any language.

Built on Boson AI's Higgs models for the Boson AI hackathon:

| Higgs model | Role here |
|---|---|
| **Higgs Realtime** | The character's brain + voice: speech-to-speech, barge-in, tool calls, auto language |
| **Higgs TTS 3** | Voice cloning from a 5–30 s clip of the character (`voice_<id>`) |
| **Higgs Avatar** | Talking-head video from a still of the character (fMP4 stream) |

## How it works (short)

```
offline:  subtitles.srt ──► scenes ──► local LLM (Ollama/Qwen) ──► scene summaries + character state timeline
          video ──► voice clip ──► demucs ──► Higgs voice clone (voice_id);  frame ──► face.png

runtime:  pause at t ──► pick character ──► backend filters knowledge to (≤ t ∩ scenes the character saw)
          ──► instructions + ephemeral key ──► browser ⇄ Higgs Realtime (mic, cloned voice, tools)
          ──► Higgs Avatar renders the reply as video
```

Details: [docs/architecture.md](docs/architecture.md). Data you need to provide: [docs/data-spec.md](docs/data-spec.md).

## Quick start

Prereqs: Python 3.10+, Node 18+, ffmpeg. Optional for preprocessing: [Ollama](https://ollama.com) (`ollama pull qwen2.5:7b-instruct`).

```bash
cp .env.example .env            # add BOSON_API_KEY

# backend
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows; on mac/linux: . .venv/bin/activate
pip install -e ".[dev]"          # add ,preprocess for whisper/demucs
pytest                           # anti-spoiler tests
uvicorn app.main:app --reload --port 8000

# frontend (new terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

Or run both: `scripts/dev.ps1` (Windows) / `scripts/dev.sh`.

The `demo` movie ships with subtitles + hand-written knowledge (no video). Drop any `video.mp4` into
`data/movies/demo/` to try the UI.

## Add a movie

```bash
cd backend
python -m preprocess.cli scenes    <movie_id>   # subtitles -> knowledge/scenes.json
python -m preprocess.cli summarize <movie_id>   # local LLM -> summaries + character_states.json
python -m preprocess.cli faces     <movie_id>   # face_at_s -> characters/<id>/face.png
python -m preprocess.cli voices    <movie_id>   # voice_clip -> cloned voice_id
```

## Repo layout

```
backend/app/          FastAPI: session, tools, avatar proxy, anti-spoiler knowledge filter
backend/preprocess/   offline CLI (scenes, LLM summaries, voice clone, faces)
backend/tests/        spoiler-safety tests
frontend/src/         React: player, character picker, chat + Realtime audio, avatar (MSE)
data/movies/<id>/     movie.json, subtitles.srt, characters.json, knowledge/, characters/<id>/
docs/                 architecture + data spec
```

## Team split

| Owner | Area | Main files |
|---|---|---|
| A | Preprocessing pipeline | `backend/preprocess/*` |
| B | Context, persona, tools, Boson client | `backend/app/context/*`, `backend/app/routers/*` |
| C | Realtime voice in the browser | `frontend/src/lib/realtime.ts`, `lib/audio/*`, `useConversation.ts` |
| D | Avatar + assets | `frontend/src/lib/mse.ts`, `AvatarView.tsx`, voice/face assets |

> ⚠️ Voice and likeness cloning: only use material you have the rights to. The UI labels all
> character output as AI-generated.
