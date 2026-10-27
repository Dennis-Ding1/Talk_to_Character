---
version: 1
slug: "presentation-index-html"
primary_target: "docs/index.html"
related_targets: []
---

# Presentation deck (docs/index.html)

Scope: a 10-minute hackathon pitch deck, 1920×1080 HTML slides, click to advance. Mode: Persuade.
Audience: Boson AI Higgs hackathon judges on a projector. Job: remember one idea (a character stuck at the pause) and believe the anti-spoiler mechanism is real. Action: score it; ask about it.
Content: English slides, English speaker notes with per-slide timing (~10:10 total). Live demo via a cue slide; no embedded video. No film frames or faces (copyright); no invented metrics.
Constraints: House Lights world from DESIGN.md unchanged; fonts self-hosted in docs/fonts.

## Direction contract

THESIS: The deck is the auditorium, and every mechanism is shown in motion, never stated as a bullet. It refuses the category default of title, bullets and icon cards on a dark template.

OWN-WORLD: Claret velvet room, projector-silver type and one silver screen slide, gold only for what is live (pause timecode, lived strip, playhead, voice bars). Hairline rules, intertitle cards between double rules, follow-spots that darken everything outside them, redacted shimmer bars for unchecked lines, square corners, marquee caps over a plain grotesk.

STORY: A curtain opens on a paused film; a generic bot spoils it; ours checks first. The judge watches the app flow, sees the live demo, then watches three filters act on real-looking data, the latency budget, the tests by name, and the honest limits. The curtain closes.

FIRST VIEWPORT: Full-bleed curtain parts over 2.6 s onto a dark house; a follow-spot lands on TALK TO CHARACTER set at 230px marquee caps, centred; below it the lived strip, led by the gold pause timecode, draws to 26% (minute 47 of a three-hour film, the one scale every strip in the deck shares), and the credit line closes the stack. No buttons; a click advances.

FORM: Cinema programme in reels, slide-by-slide builds; form 1 of 1, fixed by the user-approved outline and sample (the dealt structures were not put to a vote). seed:6e0d781b1e576358

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Surface-local decisions (documented 2026-10-24, not system tokens)

Checked against DESIGN.md: all 14 colour tokens, the three font stacks, the 700ms house and `cubic-bezier(0.16, 1, 0.3, 1)` ease, the screen-throw, front-row and follow-spot shadows, and square corners with circles kept for light and voice. All are reused unchanged. These choices hold for this deck only:

- Projection scale on a 1920×1080 canvas: titles 104px, marquee-xl 180–250px, reading text 22–40px, labels 20–26px, live dot 12px.
- Letterbox: `#12040a` (`--house-dark`) behind the stage and `#070203` page ground outside it. Neither is a palette token.
- Curtains: flat two-tone velvet/velvet-sunk stripes (48px), a velvet-fold valance, and soft ambient curtain shadows.
- The slide 04 synthetic frame and the portrait silhouette use their own SVG fills (`#5b4a3c`, `#2a1d17`, `#e9d9b8`, `#140d0a`, `#3a0b14`, ...). They are illustration colours, not palette.
- `.intertitle.key`: Hanken 600 sentence case at 36px between the double rules, for one key statement per slide. In the app, intertitles stay in marquee caps.
- Every lived strip shows one film: `--lived: 26.2%` (00:47:12 of 3h).
- Deck-only devices: 6% film-grain overlay, a gold talk-progress hairline (`#reel`), and blurred entrance builds. All are removed under reduced motion.
- On the silver screen slide (03), the lived fill and timecode are velvet, not gold, because gold does not read on silver.
- Danger coral also marks the spoiler verdict (`.intertitle.spoil`, `.vd.flag`), the failure state of the guard.
- Latency bars are filled with silver, text-2 and text-3 to grade speed. They are chart fills, not pressable silver surfaces.
