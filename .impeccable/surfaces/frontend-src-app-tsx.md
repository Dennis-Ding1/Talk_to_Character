---
version: 1
slug: "frontend-src-app-tsx"
primary_target: "frontend/src/App.tsx"
related_targets: ["frontend/src/components/ChatPanel.tsx","frontend/src/styles.css"]
---

# Surface: the watch → pause → talk app (frontend/src/App.tsx)

Mode: Experience. The film leads while playing; once paused, the conversation with the character is the work itself.
Audience: hackathon judges at a live demo first, home viewers too. Job: pause, pick a face, talk, never get spoiled.
Constraints: keep all behaviour of useConversation/AvatarView/realtime; AI voice & likeness label must stay visible; honest latency states (recognising ~1.5 s, spoiler check, avatar buffer).
Memorable moment: the house lights come up on pause and the follow-spot lands on a face.
Build path: code-led (no image generation on this machine).

## Direction contract

THESIS: Pausing the film brings the house lights up. The room around the screen appears and the character steps out of the frame into the front row to talk. This refuses the category default of a streaming player with a dark chat sidebar of bubbles and a round avatar.

OWN-WORLD: The room is claret velvet (deep oxblood to near-black wine) and carries the chrome, the panel and the ground. The screen is projector silver-white and is the only cool, bright surface. House-light gold appears only on what is live: the character speaking, your mic recording, the lived part of the timeline. Display type is tall condensed marquee caps (Big Shoulders Display). Text is a plain grotesk (Hanken Grotesk). Timecodes are mono. States are intertitle cards set between hairlines, not badges. Faces get circular follow-spots: dashed when recognised, solid when chosen. Square corners, no pills, no glow halos.

STORY: The visitor watches; nothing but the film and a quiet marquee. They pause; the lights rise and they understand they can step into this moment. They click a lit face; the character takes the front row and answers in their voice, knowing only up to this minute. A strip shows the lived film lit and the rest dark, marked NOT YET.

FIRST VIEWPORT: Desktop 1440. A 64px marquee top bar: the wordmark left, the knowledge and avatar switches right as squared two-way switches. Chapter strip below it. The screen takes the left ~68% with a velvet surround. Paused, the frame dims, the follow-spots sit on the faces, and the lived/not-yet strip runs under the screen with the gold timecode. The front-row panel takes the right ~420px of velvet: a full-bleed portrait whose name sits in 64–76px marquee caps over its lower edge, a live state line, intertitle cards, dialogue in 18–20px with the speaking line lit and checking lines dim, and the composer at the foot with a 56px round mic.

FORM: Screening room / auditorium, candidate 7 of 7 on the ordered list (assigned by roll). seed:a4446486d3c1fb02. Raises: Algorave Source Floor, visible before it sounds; Phosphor Terminal, states print themselves as intertitles; Raku Smoke Flash, gold reserved for live; Sewing Pattern Envelope, dashed until chosen; Skate Deck Wall, portrait full-bleed with a name lockup at chip size; Fletcher Wit Poster, the lived/not-yet strip legible in half a second.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Signature interaction and motion
House lights: on pause the velvet room fades up over ~700 ms while the screen dims; on play it fades back to black and the chrome recedes. Follow-spots fade in staggered as faces resolve. Choosing a face: the panel slides in from the right as the spot goes solid. Reply sentences arrive dim (checking) and light to full as they are spoken.

## Unresolved
- No real film frames can ship in the repo; screenshots use the demo or a local film only.
