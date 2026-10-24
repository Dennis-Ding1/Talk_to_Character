# Movie data

One folder per film: `data/movies/<id>/`. The folder name is the movie id (lowercase, no spaces) and
must match `"id"` in `movie.json`. Only `data/movies/demo/` is in the repository: a **made-up
placeholder** ("The Last Heist") used by the tests and as a format example. Real films are
copyrighted, so their folders are git-ignored and shared separately.

```
data/movies/<id>/
├─ movie.json              required
├─ video.mp4               required (H.264 MP4 plays in every browser)
├─ subtitles.srt           required
├─ screenplay.pdf          recommended: speakers, presence, on-screen action, scene times
├─ characters.json         required
├─ story_years.json        optional: story year per screenplay scene (non-linear films)
├─ poster.jpg              optional: shown before playback starts
├─ knowledge/
│  ├─ scenes.json             generated (screenplay / scenes, summarize)
│  ├─ character_states.json   generated (summarize, inner)
│  ├─ looks.json              generated (faceindex)
│  ├─ moments.json            optional, hand-written
│  ├─ fixes.json              optional, hand-written
│  └─ animation_faces.json    optional, for animated films
├─ characters/<char_id>/   voice_ref.wav (+ face.png): generated, or your own
└─ cache/                  generated: looks/, faces/, face_cores.npz, idle/
```

A **demo cut** is a separate folder with just `movie.json`, `video.mp4` and an optional poster (see
below). It uses the full film's characters and knowledge.

## movie.json

```json
{ "id": "oppenheimer", "title": "Oppenheimer", "language": "en", "video": "video.mp4",
  "subtitles": "subtitles.srt", "duration_s": 10822.1 }
```

| Field | |
|---|---|
| `language` | main spoken language (ISO 639-1), used when transcribing voice clips |
| `poster` | optional image file in the folder, shown on the player before playback |
| `avatar_speech` | `"realtime"` (default: Avatar is driven by the Realtime reply audio) or `"tts3"` (Avatar speech from text with Higgs TTS 3 and emotion/style tags). Voice mode always uses Realtime. |

Demo cut:

```json
{ "id": "oppenheimer_demo", "title": "Oppenheimer — Demo Cut", "video": "video.mp4",
  "poster": "poster.jpg", "source": "oppenheimer",
  "segments": [
    { "key": "apple", "title": "The Poisoned Apple", "emoji": "🍎",
      "src_start": 371, "src_end": 441, "start": 0, "duration": 70.0 }
  ] }
```

`segments` map demo time `[start, start + duration)` to film time `[src_start, src_end)`; they also
appear as chapter buttons in the player.

## subtitles.srt

Standard SRT, UTF-8. Lines without a speaker are fine when there is a screenplay (speakers come from
the alignment). Without one, prefixes help: `NAME: line`, `NAME：line` or `[NAME] line`, where NAME is
a character's `id`, `name` or one of its `aliases`.

## screenplay.pdf

The shooting script as a PDF with selectable text. `python -m preprocess.cli screenplay <id>` aligns
it to the subtitles. `--list` prints its scene numbers (used by `story_years.json`);
`--first-person <char_id>` names the character a first-person script calls "I".

## characters.json

```json
[
  {
    "id": "kitty",
    "name": "Kitty Oppenheimer",
    "aliases": ["Kitty", "Katherine"],
    "bio": "Background as of the START of the film (no spoilers).",
    "personality": "Traits.",
    "speech_style": "Tone, rhythm, habits.",
    "core": "Deep drives and beliefs that hold across the whole story (still no spoilers).",
    "relationships": { "oppenheimer": "how she sees him at the start" },
    "voice_clip": [1931.2, 1944.6],
    "voice_ref_text": "exact transcript of the clip",
    "voice_id": "voice_…",
    "face_image": "face.png"
  }
]
```

- **id**: lowercase, one word; used everywhere (subtitle prefixes, `characters/<id>/`, moments).
- **voice_clip**: 5–30 s where only this character speaks. Optional: without it, `voices` picks a
  clean line from the speaker-attributed scenes. `voice_ref_text` and `voice_id` are filled in.
- **face_image** / **face_at_s**: a portrait, used when there is no face index (e.g. animation).
- Optional delivery controls for Higgs TTS 3: `delivery_profile` (`expressive` or `subtle`) and
  `tts_emotion` (fallback emotion tag).

## story_years.json (non-linear films)

When each screenplay scene happens *in the story*, so a character in a flashback lives in that year.
`threads` match words in the scene heading first; `ranges` then set scenes by number (from
`screenplay --list`), later entries winning. Scenes without a thread are on the main timeline
(`"past"`). A heading with `SAME` continues the previous scene.

```json
{
  "threads": { "hearing_1954": { "match": ["ROOM 2022"], "year": 1954.3 } },
  "ranges": [
    { "scenes": "4-6", "year": 1926.0, "note": "Cambridge, Blackett's lab, Bohr lecture" },
    { "scenes": "8-10", "year": 1947.0, "thread": "strauss_past" }
  ]
}
```

See `data/movies/oppenheimer/story_years.json` for the full example with comments.

## knowledge/moments.json (hand-written, optional)

A character's private thought at an exact moment, for pauses in the middle of a scene. Shown to the
character as "what's going through your head right now" once film time passes `t`.

```json
[{ "character_id": "oppenheimer", "t": "7:05.0", "curated": true,
   "text": "He raised it to his mouth and I grabbed it out of his hand and dropped it in the wastebasket." }]
```

## knowledge/fixes.json (hand-written, optional)

Corrections applied on load, so re-running preprocessing keeps them:

```json
{ "line_speakers": [{ "t": "6:25.3", "speaker": "oppenheimer" }],
  "drop_beats": ["text of a junk beat to remove"] }
```

`t` is the subtitle line's start in film time (`h:mm:ss.s` or `m:ss.s`).

## Generated files

`knowledge/scenes.json`:
```json
[{ "id": "s007", "start": 369.0, "end": 542.0, "story_year": 1926.2, "thread": "past",
   "slug": "INT. LABORATORY, CAMBRIDGE -- DAY",
   "characters_present": ["oppenheimer", "bohr"], "summary": "...", "key_events": ["..."],
   "lines": [{ "start": 371.5, "end": 372.2, "text": "Are you all right?", "speaker": "blackett", "vo": false }],
   "beats": [{ "t": 372.4, "text": "Between them on the workbench, the POISONED APPLE..." }] }]
```

`knowledge/character_states.json` (one per character per scene):
```json
[{ "character_id": "oppenheimer", "scene_id": "s007", "t": 542.0,
   "goals": "...", "stance": "...", "emotion": "...", "relationships": { "bohr": "..." },
   "did": "...", "why": "...", "felt": "...", "hiding": "..." }]
```

Hand-editing `characters_present`, a few states, or adding moments is the fastest way to improve a
specific demo moment.
