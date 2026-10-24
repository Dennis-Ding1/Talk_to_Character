# Talk to Character 🎬🗣️

**Pause a movie. Click on a face. Talk to that character, in their own voice, with a face that moves,
and they only know what they've lived up to that moment.**

A generic "chat with a movie character" bot knows the whole plot. Ours is a person stuck at minute 47.
Pause *Oppenheimer* right after he snatches the poisoned apple and ask him why: he'll tell you about
Blackett, the cyanide and how close he came to killing Niels Bohr. Ask him whether the bomb works and
he has no idea what you mean, because for him it's 1926 in Cambridge and Los Alamos doesn't exist yet.
Switch to the other mode and the same character looks back on his whole life, ready for "what if".

Built for the Boson AI hackathon, entirely on the **Higgs** models.

## Core features

**Spoiler-safe characters ("Up to now").** A character's knowledge is cut at the exact paused
second and limited to the scenes they were actually in. They remember what was said, what happened
on screen and what they felt at the time, from a screenplay aligned to the subtitles plus first-person
inner notes. Each sentence is also checked against the rest of the film before you hear it. If it
gives something away, it never reaches you.

**Omniscience.** The same character, knowing how their story ends. Made for "what would you do
differently?" and "what if you had said no?".

**Click a face to talk.** When you pause, the faces in that exact frame are recognised and lit up.
Click one and the conversation opens with that character as they look *in this scene*. This also
works for animation (Rick and Morty).

**Voice mode: a real conversation.** Hands-free. You just talk, and the character answers in their
cloned voice about a second after you stop. Cut in at any time and they stop to listen. Each reply
is spoiler-checked before it plays.

**Avatar mode: a talking face.** The reply becomes a lip-synced talking head made from the
character's look at that moment. We drive Higgs Avatar with finished audio instead of text, so it
starts playing **2–5 s sooner**. See the [benchmark](backend/model_speed_test/README.md).

**Any language.** Ask in Chinese, get the answer in Chinese, in the same cloned voice.

**Any film.** Movies are data folders. A *demo cut* (e.g. three key scenes of *Oppenheimer*) jumps
straight to the good moments, while every answer stays exactly what it would be in the full film.

## How the Higgs models are used

| Model | What it does here |
|---|---|
| **Higgs Realtime** (`higgs-realtime-1.5-preview`) | The character's mind and voice: listens, decides when you've finished, answers in the cloned voice, handles interruptions |
| **Higgs STT 3.1** | Transcribes your question so the right memories can be attached to it |
| **Higgs TTS 3** | Voice cloning from a few seconds of each character's dialogue; emotion and style tags for avatar speech |
| **Higgs Avatar** | Talking-head video, streamed and played as it renders |
| **Higgs Realtime** (text) | The spoiler checker, and the offline step that writes scene summaries and inner notes |

```
offline   screenplay + subtitles ─► timed scenes, on-screen actions, who was there, story year
          ─► per-scene character states and inner notes;  faces ─► face index;  dialogue ─► cloned voices

pause at t ─► knowledge cut at t and filtered to what this character saw
          ─► Higgs Realtime (your voice in, their voice out) ─► spoiler check ─► speaker / Higgs Avatar
```

More: [docs/architecture.md](docs/architecture.md) · data format: [docs/data-spec.md](docs/data-spec.md)

## Run it

You need Python 3.10+, Node 18+, ffmpeg, and a [Boson AI API key](https://docs.boson.ai/set-up-your-account).

```bash
cp .env.example .env                 # put your BOSON_API_KEY in it

cd backend
python -m venv .venv
.venv\Scripts\activate               # macOS / Linux: source .venv/bin/activate
pip install -e .
uvicorn app.main:app --port 8000

cd frontend                          # in a second terminal
npm install
npm run dev                          # open http://localhost:5173
```

**Movie data is not in the repo** (copyright, see below). Put the movie folders you were given
into `data/movies/` (e.g. `oppenheimer/` and `oppenheimer_demo/`). Cloned voices belong to the API
key that created them, so register them once under your own key, then restart the backend:

```bash
cd backend
python -m preprocess.cli voices oppenheimer --redo
```

## Movie data

### What a film needs

For the best conversations a film needs **both subtitles and the screenplay**:

- **Subtitles** (`subtitles.srt`) give every line with its exact time, so a character can remember
  what was said right up to the paused second.
- **The screenplay** (`screenplay.pdf`) adds what subtitles can't: who is speaking, who is in the
  scene without speaking, what happens on screen (the poisoned apple is never mentioned out loud),
  and where and when each scene takes place. It is aligned to the subtitles automatically.

Subtitles alone still work, but characters only know dialogue, not actions, and may guess wrong
about who said what.

### Folder and file names

Each film is one folder, `data/movies/<id>/`. The folder name is the movie's `id` (lowercase, no
spaces) and must match `"id"` in `movie.json`. Use these file names:

```
data/movies/<id>/
├─ movie.json              required  id, title, language; optional "poster": "poster.jpg"
├─ video.mp4               required  H.264 MP4 plays in every browser
├─ subtitles.srt           required  UTF-8; "NAME: line" prefixes help (NAME = id, name or alias)
├─ screenplay.pdf          recommended
├─ characters.json         required  the main characters: id, name, aliases, bio, personality, speech style
├─ story_years.json        optional  story year per screenplay scene, for non-linear films
├─ poster.jpg              optional  shown before playback starts
├─ knowledge/              generated by preprocess
├─ characters/<char_id>/   generated; voice_ref.wav is needed to re-register voices
└─ cache/                  generated (face crops, face index, avatar idle loops)
```

- **Character ids** are lowercase, one word (`oppenheimer`, `kitty`, `rick`) and are used
  everywhere: subtitle prefixes, `characters/<char_id>/`, `moments.json`.
- **A demo cut** is its own folder with just `movie.json`, `video.mp4` and an optional poster. Its
  `movie.json` names the full film in `"source"` and lists `"segments"` (demo time → film time), so
  it shares the film's characters and knowledge and behaves exactly like the full film.

Full field reference: [docs/data-spec.md](docs/data-spec.md).

### About `data/movies/demo`

`data/movies/demo` ("The Last Heist") is a **made-up placeholder**: a few invented lines and
characters used by the automated tests. It is not one of the films in our demo. The films we
presented (*Oppenheimer*, *Rick and Morty*) are copyrighted, so their video, subtitles, screenplay
and everything derived from them stay out of the repository and are shared separately.

<details>
<summary>Preparing a new film from scratch</summary>

With the files above in `data/movies/<id>/`, run from `backend/`:

```bash
python -m preprocess.cli screenplay <id>   # scenes, speakers, timed on-screen actions (or: scenes <id>, subtitles only)
python -m preprocess.cli summarize <id>    # scene summaries + each character's state per scene
python -m preprocess.cli inner <id> --only a,b   # first-person inner notes (did, why, felt, hid) for these characters
python -m preprocess.cli faceindex <id>    # recognise faces, best look of each character per scene
python -m preprocess.cli voices <id>       # clone each character's voice from a clean line of dialogue
```
`LLM_BACKEND` in `.env` picks the model for the text steps: `higgs_text` (Boson) or `ollama` (local).
</details>

> Voices and faces are cloned from films for a hackathon demo. Only use material you have the
> rights to. Everything a character says or shows is labelled as AI-generated in the UI.
