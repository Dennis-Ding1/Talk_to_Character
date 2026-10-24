---
name: Talk to Character
description: Pause the film, the house lights come up, and a character steps into the front row to talk.
colors:
  velvet-deep: "#1c060b"
  velvet-sunk: "#2a0910"
  velvet-panel: "#360c15"
  velvet: "#4a111c"
  velvet-fold: "#5e1724"
  silver: "#eee9e2"
  text-2: "#d9bfbb"
  text-3: "#b08f8d"
  line: "rgba(238, 233, 226, 0.16)"
  line-strong: "rgba(238, 233, 226, 0.32)"
  gold: "#f2c27a"
  gold-ink: "#2b1405"
  danger: "#ff9a88"
  screen-black: "#000000"
typography:
  display:
    fontFamily: "Big Shoulders Display, Arial Narrow, sans-serif"
    fontSize: "clamp(52px, 4.7vw, 76px)"
    fontWeight: 800
    lineHeight: 0.86
    letterSpacing: "0.01em"
  headline:
    fontFamily: "Big Shoulders Display, Arial Narrow, sans-serif"
    fontSize: "30px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.02em"
  title:
    fontFamily: "Big Shoulders Display, Arial Narrow, sans-serif"
    fontSize: "28px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.04em"
  intertitle:
    fontFamily: "Big Shoulders Display, Arial Narrow, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "0.14em"
  dialogue:
    fontFamily: "Hanken Grotesk Variable, Hanken Grotesk, system-ui, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.55
  body:
    fontFamily: "Hanken Grotesk Variable, Hanken Grotesk, system-ui, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Big Shoulders Display, Arial Narrow, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    letterSpacing: "0.12em"
  timecode:
    fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: "15px"
    fontWeight: 400
    fontFeature: "tnum"
rounded:
  none: "0px"
  circle: "50%"
spacing:
  hair: "4px"
  xs: "8px"
  sm: "14px"
  md: "18px"
  lg: "22px"
  xl: "28px"
components:
  button-default:
    backgroundColor: "transparent"
    textColor: "{colors.silver}"
    rounded: "{rounded.none}"
    padding: "8px 14px"
  talk-button:
    backgroundColor: "{colors.silver}"
    textColor: "{colors.velvet-deep}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "10px 18px 9px 14px"
  segmented-switch:
    backgroundColor: "transparent"
    textColor: "{colors.text-2}"
    rounded: "{rounded.none}"
    padding: "6px 14px"
  segmented-switch-on:
    backgroundColor: "{colors.silver}"
    textColor: "{colors.velvet-deep}"
  mic:
    backgroundColor: "{colors.silver}"
    textColor: "{colors.velvet-deep}"
    rounded: "{rounded.circle}"
    size: "56px"
  mic-recording:
    backgroundColor: "{colors.gold}"
    textColor: "{colors.gold-ink}"
  composer-field:
    backgroundColor: "{colors.velvet-sunk}"
    textColor: "{colors.silver}"
    rounded: "{rounded.none}"
    padding: "13px 14px"
  front-row-panel:
    backgroundColor: "{colors.velvet-panel}"
    textColor: "{colors.silver}"
    rounded: "{rounded.none}"
    width: "clamp(360px, 30vw, 440px)"
  intertitle-card:
    backgroundColor: "transparent"
    textColor: "{colors.silver}"
    typography: "{typography.intertitle}"
    padding: "11px 8px 9px"
  ai-tag:
    backgroundColor: "rgba(28, 6, 11, 0.7)"
    textColor: "{colors.silver}"
    rounded: "{rounded.none}"
    padding: "4px 8px 3px"
  character-card:
    backgroundColor: "{colors.velvet-sunk}"
    textColor: "{colors.silver}"
    rounded: "{rounded.none}"
    width: "116px"
---

# Design System: Talk to Character

## Overview

**Creative North Star: "House Lights"**

The interface is the auditorium around a film, not a player with a sidebar. While the film plays the room is almost gone: near-black wine, a quiet marquee, the screen. Pausing brings the house lights up. The claret velvet room fades in over 700ms, the frame dims, follow-spots land on the faces in the paused frame, and the chosen character takes a seat in the front-row panel at the right. Every surface is either room (velvet), screen (projector silver), or light (follow-spots and house-light gold).

Density is low and theatrical. Chrome is hairlines and condensed marquee caps; there are no cards-with-shadows-and-radius, no bubbles, no badges. The machinery's states (finding faces, taking their seat, thinking, the story year) are printed as silent-film intertitle cards set between double hairlines. Replies arrive dim and light to full silver as they are spoken; unspoken lines still under spoiler check appear as redacted shimmer bars, never their text.

The system rejects the category default of a streaming player with a dark chat sidebar of rounded bubbles and a circular avatar. The portrait is full-bleed and square-cornered, with the name set huge over its lower edge.

**Key Characteristics:**
- Three materials only: velvet room, silver screen, gold live light.
- Two states of the room, driven by `data-house="up|down"`: paused (velvet, sconce gradient, dimmed film) and playing (velvet-deep, chrome recedes).
- Tall condensed marquee caps for names, titles, labels and intertitles; plain grotesk for everything read; mono for timecodes.
- Square corners everywhere; circles are reserved for light and voice (follow-spots, the mic, the live dot).
- Motion is slow, eased and theatrical (700ms house transition, `cubic-bezier(0.16, 1, 0.3, 1)`), and fully removed under reduced motion.

## Colors

A monochrome claret room with one cool bright surface and a single warm accent that means "live".

### Primary
- **House-Light Gold** (gold): only what is live right now. The lived portion of the timeline and the pause timecode at its edge, the speaking and listening state line, the voice bars, the recording mic, and its hint. Text set on gold uses **Gold Ink** (gold-ink).

### Neutral
- **Projector Silver** (silver): the screen colour and primary text. Also the "lit" inverse surface: the Talk button, the active segment of a switch, the mic at rest, the hovered spot name. Focus rings are silver.
- **House Down** (velvet-deep): the room while the film plays, page ground, and the ink on silver surfaces.
- **The Sunk Seat** (velvet-sunk): recessed fields (the composer, character cards, placeholders, the error banner).
- **The Front Row** (velvet-panel): the conversation panel.
- **House Up** (velvet): the room once paused.
- **Velvet Fold** (velvet-fold): top of the room's vertical fold gradient and placeholder portraits only.
- **Rose Smoke** (text-2): secondary text, inactive controls, the opening prompt, user lines.
- **Dusty Claret** (text-3): meta text, marquee labels, chapter numbers, unlit assistant lines.
- **Hairline / Strong Hairline** (line, line-strong): silver at 16% and 32%. All structure is drawn with these.
- **Screen Black** (screen-black): the letterbox behind the film, nowhere else.
- **Warning Coral** (danger): errors only.

### Named Rules
**The House Light Rule.** Gold marks what is live now: speaking, recording, the lived span of the film. Never use it for decoration, headings, hover or brand.

**The One Screen Rule.** Silver is the only cool, bright colour. A silver-filled surface means "this is the thing to press" or "this is selected"; there is never more than one per control group.

## Typography

**Display Font:** Big Shoulders Display 600/800 (with Arial Narrow, sans-serif), self-hosted via @fontsource
**Body Font:** Hanken Grotesk Variable (with system-ui, PingFang SC, Microsoft YaHei for CJK)
**Label/Mono Font:** ui-monospace (SF Mono, Menlo, Consolas) for timecodes only

**Character:** A cinema marquee over a plain programme note. The condensed caps carry names and the room's announcements; the grotesk carries everything a person has to read, in any language.

### Hierarchy
- **Display** (800, clamp(52px, 4.7vw, 76px), 0.86, uppercase): the character's name lockup over the portrait's lower edge; 58px on small screens.
- **Headline** (800, 30px, 1, uppercase, balanced): the picker question under the screen.
- **Title** (800, 28px, 1, 0.04em, uppercase): the wordmark. The Talk button (19px) and spot names (18px) and card lockups (17px, 0.95) are smaller siblings in the same weight.
- **Intertitle** (600, 20px, 1.1, 0.14em, uppercase, centred): state cards in the conversation; quiet variant at 16px in Dusty Claret.
- **Dialogue** (400, 18px, 1.55, max 34em): the character's lines.
- **Body** (400, 15px root, 14px in chrome, 13px for notes, 1.55): prompts, suggestions, user lines, chapter titles.
- **Label** (600, 13-15px, 0.12-0.16em, uppercase, Dusty Claret): names a control or a group in place ("They know", "Avatar", "Not yet", "Also in this scene", the "You" speaker cue, the AI tag).
- **Timecode** (mono, 12-15px, tabular numerals).

### Named Rules
**The Marquee Caps Rule.** Big Shoulders is always uppercase and always tracked (0.01em at display size up to 0.16em at label size). Reading text is never set in it.

**The Label Earns Its Place Rule.** A marquee label names the control, group or speaker beside it. It never floats above a headline as decoration.

## Layout

A full-height column: a 64px top bar (wordmark and film select left, two squared switches right), a horizontally scrolling chapter strip, then the main grid. Main is one column while watching and becomes `minmax(0, 1fr) clamp(360px, 30vw, 440px)` when a character is chosen, so the screen keeps roughly two-thirds and the front row takes the right edge. The stage under the screen holds one timeline row (transport while playing, the lived/not-yet strip once paused) and the picker row (`minmax(180px, 250px) auto minmax(0, 1fr)`: question, faces seen here, everyone else behind a hairline).

Gutters are 28px on desktop and 16px under 900px; the panel's inner gutter is 22px. Spacing steps are 4, 8, 14, 18, 22, 28px.

Under 900px everything stacks: the screen fixes to 16:9, the panel drops below with a hairline top, the portrait caps at 28vh, control labels hide, and the composer becomes sticky at the bottom with safe-area padding.

## Elevation & Depth

Depth is light, not lift. The room gets depth from a layered background (a warm sconce radial from above, a vignette, a vertical velvet fold) that only fades in when the house is up. Shadows are soft, dark and ambient: they sit things into the room, never pop them off it.

### Shadow Vocabulary
- **Screen throw** (`box-shadow: 0 24px 60px -12px rgba(0,0,0,0.75), 0 2px 6px rgba(0,0,0,0.5)`): the screen only.
- **Front row** (`box-shadow: -18px 0 48px -12px rgba(0,0,0,0.55)`): the panel's left edge on desktop; removed on mobile.
- **Pressable lift** (`box-shadow: 0 10px 30px -6px rgba(0,0,0,0.7)` / `0 8px 20px -6px rgba(0,0,0,0.6)`): the Talk button over the film and the mic.
- **Follow-spot** (`box-shadow: 0 0 0 200vmax rgba(8,2,4,0.62), 0 0 60px 20px rgba(8,2,4,0.5) inset`): the hovered or chosen spot darkens everything outside its circle.

### Named Rules
**The Light Lands Rule.** Emphasis is made by darkening the surroundings (dimmed film, follow-spot falloff, unlit lines), not by glowing the subject.

## Shapes

Square corners (0px) on every rectangle: buttons, switches, fields, cards, panels, tags, the portrait. Structure is drawn with 1px silver hairlines rather than filled containers. Circles (50%) belong only to light and voice: follow-spots, the 56px mic and its recording ring, and the 8px live dot. Icons are drawn on a 24px grid with a 1.75px stroke, square caps and mitred joins.

## Components

### Buttons
- **Shape:** squared (0px), 1px strong hairline at rest, silver border on hover, 0.18s colour transitions; disabled at 38% opacity.
- **Talk button:** a silver slab over the film's top right corner, marquee caps 19px in velvet-deep ink with the pause-and-spotlight icon; hover goes pure white.
- **Ghost / icon buttons:** no border, Rose Smoke icon, silver on hover.
- **Focus:** 2px silver outline, 3px offset, everywhere.

### Segmented switch
- **Style:** two squared segments inside one strong hairline, divided by a hairline. Active segment is filled silver with velvet-deep 600 text; inactive segments are Rose Smoke, brightening on hover with a 6% silver wash.

### Chapter strip
- **Style:** text buttons with a hairline underline, mono chapter number in Dusty Claret; hover turns text and underline silver. Scrolls horizontally, no scrollbar.

### Cards / Containers
- **Character card:** 116px wide, velvet-sunk ground, inset 1px hairline outline, square portrait crop (132px tall) slightly desaturated, marquee name lockup below. Hover: 2px silver outline and the photo warms to full saturation.
- **Front-row panel:** velvet-panel column that slides in from the right (28px, 650ms). Full-bleed square portrait with a top-and-bottom velvet gradient, the AI voice & likeness tag top left, a squared close button top right, the name lockup and live state line over the lower edge.

### Inputs / Fields
- **Composer:** velvet-sunk field in a strong hairline, square, 13px 14px padding, Dusty Claret placeholder, gold caret. Focus moves the border to silver (no outline ring inside the field). The send arrow sits inside the field.
- **Select:** borderless, transparent, Rose Smoke.

### Follow-spot (signature)
Circular spot over each recognised face. Dashed 2px silver with a faint warm pool while recognised; fades in from 125% scale (600ms), staggered 90ms per face. Hover, focus or choice turns it solid and drops the rest of the frame into shadow; the name tag beneath inverts to silver. Unrecognised faces get a 1.5px dotted, non-interactive ring. While recognition runs, a "Finding faces" intertitle chip breathes at the top of the frame.

### Intertitle card (signature)
Centred marquee caps between two strong hairlines with an inner hairline 3px inside each, like a silent-film title card. Used for story-time anchors and machinery states; the quiet variant drops the inner rules and dims to Dusty Claret; the thinking variant breathes.

### Lived strip (signature)
Once paused, the transport becomes a 4px track: gold for the part of the film the character has lived, faint silver for the rest, with the gold pause timecode on the left and a "Not yet" (or "They know the ending") label on the right.

### Dialogue
Assistant lines are 18px silver; while one is being spoken the others fall to Dusty Claret. User lines are right-aligned Rose Smoke with a "You" speaker cue. Lines still under spoiler check render as shimmering redacted bars. Suggestions are a hairline-ruled list that nudges 8px right on hover.

### Mic
56px silver circle with a drawn mic icon. Recording turns it gold with gold ink and a gold ring that expands and fades every 1.4s; the hint line below speaks in gold only while recording.

## Do's and Don'ts

### Do:
- **Do** drive the room from one attribute: velvet-deep while playing, velvet plus the sconce gradient and a dimmed film (brightness 0.78, saturate 0.85) once paused, over 700ms.
- **Do** keep gold for live state only: speaking, recording, the lived span and its timecode.
- **Do** print machinery states as intertitle cards between hairlines, in marquee caps.
- **Do** keep the "AI voice & likeness" tag visible wherever the avatar appears.
- **Do** use mono with tabular numerals for every timecode.
- **Do** strip all animation and transition under `prefers-reduced-motion`.

### Don't:
- **Don't** round rectangles or use pills; circles are only for spots, the mic and the live dot.
- **Don't** render dialogue as chat bubbles or the character as a round avatar.
- **Don't** add glow halos around controls, text or the portrait; the follow-spot's own faint warm pool is the only cast light, and emphasis comes from darkening what surrounds the subject.
- **Don't** use gold for hover, headings, links or decoration.
- **Don't** set reading text in Big Shoulders, or set Big Shoulders in lowercase.
- **Don't** show the text of a line that has not passed the spoiler check.
- **Don't** use status badges; state lives in the intertitle cards and the live line.
