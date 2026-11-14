# Earth Trend Detective — design system

Accepted for the NASA Space Apps 2026 demo (14 Nov 2026). One system for the cover (`/`), the
story mode (`/story/<id>`) and the explorer (`/explore`).

## Audience and task

Jurors and visitors who give the demo a minute. They need to see a real place change, read a
verdict at a glance, and trust it. So the satellite pictures and the 3D relief lead; text is short
and every number comes from `site.json` or the API.

## Direction

A detective's case file laid over satellite imagery. The interface stays out of the way: near-black
ground, one ink, one marker-yellow accent. The pictures carry the colour.

- **Idea:** the 2003–2024 record is the central gesture. In story mode, the year scrubber *is* the
  chart of the selected record; the 3D map follows the year when a yearly layer exists.
- **Verdict as a stamp:** `↓ Real` (solid yellow), `↑ Likely` (yellow outline), `? Can't tell yet`
  (grey dashed outline). Icon + words + fill strength, never colour alone.

## Tokens (`frontend/src/app/globals.css`)

| Role | Value |
| --- | --- |
| Ground / surfaces | `#0b0d10`, `#13171c`, `#1b2027`, `#252b33` (tone steps, no lines or shadows) |
| Ink | `#eef0ea`; secondary `#b7bec6`; tertiary `#8c949d` (all ≥ 4.5:1 on the ground) |
| Accent | `#ffd23f` on `#14120a`. Used for primary actions, the active case, the cursor and the stamp |
| Data | from the pipeline's RdBu_r stops in the layer `.json`; climate share `#46586b` |

## Type

Archivo (Google Fonts, variable, with a width axis), one family. Condensed (`font-stretch: 75%`)
and heavy for headlines and big figures; wide (112%) for the wordmark; normal for text. Body text
≥ 16 px, tabular figures.

## Layout and components

- Square corners, flat fills. Buttons: one fill, 48 px tall. Every target ≥ 44 px.
- No eyebrows, no gradients, no glass, no shadows at rest (only text scrims on photographs).
- Story mode: relief full height on the left, case file on the right (460 px); below 1100 px the
  relief sits on top, then the layer picker, the timeline and the case file.
- Map legends are stepped colour blocks with the pipeline's own words at both ends.

## 3D relief

Heights decoded at full precision (16-bit PNG or terrain-RGB), CPU mesh, slab with earth sides,
low raking sun with soft shadows, fog, fly-in from overhead, slow drift until touched. The
vertical exaggeration is shown on screen ("Heights ×N") and can be changed.
Yearly and trend layers are multiplied over the satellite picture so the water and the ice stay
readable.

## Motion

Rise-in for headings and panel content, a slow drift on the cover picture, the camera fly-in.
`prefers-reduced-motion` drops the travel and stops autoplay.
