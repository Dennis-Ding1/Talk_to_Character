# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two audiences, both confirmed:

- **Hackathon judges (first).** Boson AI Higgs hackathon. They watch a live demo on a laptop or projector and have a few minutes to understand the idea and remember it.
- **Film viewers at home (must hold up too).** Someone watching a movie on a computer pauses it and talks to a character on screen, in any language.

## Product Purpose

Pause any movie and talk to the character on screen, in their cloned voice and with a talking-head avatar, while they know **only what they know at that moment** in the story. Success: the conversation feels like meeting the person inside the scene, and it never spoils what the viewer hasn't seen.

## Positioning

The anti-spoiler mechanism is the product. Knowledge is cut at the pause time t and filtered to the scenes that character witnessed. Non-linear films are anchored to the viewer's progress through the main timeline, and every spoken sentence is spoiler-checked and rewritten before it is voiced. A generic "chat with a movie character" bot knows the whole plot. This one is a person stuck at minute 47.

## Operating Context

- Flow: watch → pause ("Talk to a character") → faces in the exact paused frame are recognised and clickable, with a picker of characters in the scene as an alternative → a conversation panel with the character's avatar → push-to-talk mic or typed questions → the reply is spoken sentence by sentence in the cloned voice.
- Two knowledge modes: **Present** (spoiler-safe, as of the pause) and **Omniscient** (the character knows how it all ends, for "what if" questions).
- Two avatar modes: **Voice first** (fast; still portrait plus cloned voice) and **Lip-sync** (slower; Higgs Avatar talking-head video with an idle loop).
- Demo cuts: a film can carry `segments` (chapters) that jump playback to prepared moments.
- Story time vs. screen time: in flash-forward scenes the character is "anchored" to an earlier year, and the UI says so.
- The conversation experience is the centre of gravity; the film is the doorway into it (confirmed).

## Capabilities and Constraints

- React 18 + Vite frontend (`frontend/src`), FastAPI backend; Boson Higgs Realtime (text "thinking"), Higgs TTS (cloned voice), Higgs Avatar (fMP4 stream played via MSE).
- Latency is real: first audio arrives after a spoiler check (~0.6 s+); a lip-sync avatar clip needs ~3 s of buffer; frame face recognition takes ~1.5 s. The UI must show these states honestly.
- Push-to-talk only (automatic voice activity detection made the character hear itself).
- Avatar renders one clip at a time per account.
- Any language in, the reply comes back in the user's language.

## Brand Commitments

- Name: "Talk to Character".
- Generated voice and likeness must be labelled as AI-generated wherever the avatar appears.

## Evidence on Hand

- `data/movies/demo/`: a made-up demo movie (subtitles plus hand-written knowledge, no video).
- Real films (e.g. Oppenheimer) are used locally and never committed. Their frames and faces are copyrighted and must not ship in the repo or in marketing.
- No user testimonials, metrics or benchmarks exist; none may be invented.

## Product Principles

1. Never spoil. Every surface that shows or says story content respects the pause point.
2. The character is a person in a moment, not an assistant. Nothing in the UI should frame them as a chatbot.
3. Show the machinery's state honestly (recognising, thinking, speaking, anchored), because waiting is part of the experience.
4. Any language, no setup: pause, click a face, talk.

## Accessibility & Inclusion

Multilingual input and output (CJK included); typed input is always available as an alternative to the mic.
