# Earth Trend Detective — design system

Accepted on 14 Nov 2026 (evening), replacing the yellow case-file direction. One system with two
modes: **Documentary** to tell a case, **Instrument** to explore it. Visual reference for both:
the "Direcciones de diseño ETD" artifact (directions B and C).

## Audience and task

Jurors and visitors who give the demo a minute. First they need to *follow* one case without
effort: see a real place change, read the verdict, trust it. Only then do some of them want to
*explore*: layers, years, the drone, their own question. The design separates those two moments
instead of showing every control at once.

## The two modes

| Mode | Where | What the screen holds |
| --- | --- | --- |
| **Documentary** (C) | Cover (`/`) and the entry to a case (`/story/<id>`) | The map full screen, one subtitle, the chapter names, the year, a progress line. Nothing else. |
| **Instrument** (B) | Free mode of a case, `/investigate`, `/explore` | Map full bleed with a dark scrim on the reading side, one big thin figure, a quiet stepper, panels folded until asked for. |

### Flow of a case

1. Enter a case: Documentary. Three chapters, one question each: **What is changing? → Is it
   real? → Is it the climate?** Each chapter sets the map (layer, year, camera) and shows one
   subtitle: a headline and one short line. It advances on its own and can be paused; "Next" moves
   on by hand.
2. After chapter 3 (or "Explore" at any time, a quiet text button): Instrument mode. Layers,
   year scrubber, drone view and "Ask the map" appear here and only here.

### Rules that keep it calm

- **One primary action per screen.** In Documentary it is Next/Pause. In Instrument it is the
  current task (Ask, Investigate). Everything else is a quiet text button.
- **No accent colour in the interface.** Interface is ink on ground. Colour belongs to the data
  (map layers, legends, the climate split). Nothing in the chrome is yellow, red or blue.
- **One year on screen.** The timeline owns the year; no second year label.
- **Panels start folded.** Layers, sources and the evidence of an investigation open on demand.
- **Each figure once per view.** If the big figure shows 54–84 %, the text around it does not
  repeat it.

## Tokens (`frontend/src/app/globals.css`)

| Role | Value |
| --- | --- |
| Ground / surfaces | `#0e1012`, `#15181b`, `#1c2024`, `#262b30` (tone steps; no shadows at rest) |
| Ink | `#e9ecee`; secondary `#aeb6bc`; tertiary `#8f989f` (≥ 4.5:1 on the ground) |
| Lines | `#3a4146` (stepper track, dividers when a tone step is not enough) |
| Scrim on photographs | `linear-gradient(90deg, rgba(14,16,18,.92) 0%, rgba(14,16,18,.55) 34%, transparent 58%)` for side text; bottom fade `rgba(0,0,0,.85) → 0` for subtitles |
| Data | the pipeline's own ramp stops from each layer `.json` (RdBu_r for trends) |
| Climate split | not explained by climate: ink `#e9ecee`; explained by climate: `#46586b`; model range: hatched ink |

## Verdict stamp

Icon + words + fill strength, never colour alone, all in ink:
`↓ Real` (solid ink, dark text) · `↑ Likely` (ink outline) · `? Can't tell yet` (tertiary dashed outline).

## Type

- **Archivo** (variable, width axis): condensed (`font-stretch: 75%`) and heavy for Documentary
  headlines, subtitles and the year. Wide (112 %) for the wordmark only.
- **Manrope**: interface text, labels and the big thin figures of Instrument mode (weight 300 at
  display size, tabular figures).
- Body text ≥ 16 px. Uppercase labels with 0.08–0.12em tracking, used for chapter names and keys.

## Layout

- Square corners, flat fills, 48 px buttons, every target ≥ 44 px.
- Documentary: chapters top centre, year top right, subtitle bottom centre (max ~70 % width),
  progress line under it.
- Instrument: reading column on the left over the scrim (about 38 % wide on desktop); map controls
  bottom right; stepper or timeline along the bottom. Below 1100 px the map sits on top and the
  reading column follows.
- No eyebrows, gradients (other than scrims), glass or decorative shadows.

## Map layers

- **Smooth at the data's own resolution.** Upsample each layer from its native grid (MODIS 1 km,
  GRACE ~300 km) with bilinear/bicubic filtering, then colour it with the continuous ramp. Never
  stretch the 8-bit block image with nearest filtering. The legend says "1 km pixels, smoothed for
  display" (or the layer's own resolution).
- Not significant stays faded; no data stays transparent.
- **One coloured layer at a time.** A second layer is seen through the **curtain** (a vertical
  divider dragged across the map: left one layer, right the other). The same curtain does
  then-and-now pictures. No stacking of two coloured layers with transparency.
- Legends: the continuous ramp with the pipeline's words at both ends.

## 3D relief

Heights at full precision (16-bit PNG or terrain-RGB), CPU mesh, slab with earth sides, low raking
sun with soft shadows, fog, fly-in from overhead, slow drift until touched. The vertical
exaggeration is shown on screen ("Heights ×N"). Data layers are multiplied over the satellite
picture so water and ice stay readable.

## Motion

Documentary chapters crossfade (map and subtitle, ~600 ms) and the camera moves between chapter
views. Instrument mode has no ambient motion. `prefers-reduced-motion` drops camera travel and
autoplay; chapters then change only on "Next".
