# Story mode (Next.js)

The 3D case-study viewer. `../sites/<id>/` is the only input: a `site.json` plus PNGs.
Nothing here invents numbers — every figure on screen comes from `site.json`.

## Run it

```bash
npm install
npm run dev       # http://127.0.0.1:5180
npm run build     # production build
npm run start     # serve the build on :5180
npm run typecheck # tsc --noEmit
```

`predev` and `prebuild` run `scripts/sync-sites.mjs`, which mirrors the repo's
top-level `sites/` into `public/sites` (Next only serves static files from
`public/`). The folder is generated and gitignored: the pipeline keeps owning
`sites/`, nobody copies files by hand. If `sites/` is missing the build still
succeeds and the UI shows its "this case has no assets yet" state.

## Two Next-specific traps

1. **`allowedDevOrigins`.** Next 16 blocks dev resources (`/_next/hmr`) requested
   from a host name it does not recognise. Loading `http://127.0.0.1:5180`
   instead of `localhost` makes the dev client fail silently: the page renders
   (server-rendered HTML) but never hydrates, so every button is dead. That is
   why `next.config.ts` lists `127.0.0.1` and `localhost`.
2. **`sites/` is outside the app.** There is no way to serve it directly; the
   sync script is the bridge. If the deploy platform only uploads `frontend/`
   (Vercel "Root Directory"), run `npm run sync-sites` before the build or commit
   `public/sites` for the demo.

## What the scene expects

| File | Format | Notes |
|---|---|---|
| `heightmap.png` | 8-bit grayscale, square (512² or 1024²) | white = high. Displaces the mesh and drives the hillshading. |
| `base.jpg` | square, same aspect as the bbox | satellite or hillshaded surface |
| `trend_<var>.png` | RGBA, same size | alpha is the **significance mask**; transparent pixels stay unpainted |
| `year_<var>_<YYYY>.png` | RGBA, one per year | anomaly frames, crossfaded on the timeline |
| `site.json` | see `src/story/types.ts` | narrative, steps, variables, verdicts, sources |

Every asset except `site.json` is optional for a given variable: a variable with no
`trend_<id>` still appears in the panel, it just has no surface to paint. That is on
purpose — an honest incomplete case beats a broken complete one.

`site.json` fields used for the camera and the relief:

```jsonc
{
  "bbox": [-6.60, 36.85, -6.25, 37.15],  // west, south, east, north
  "elevation_m": [0, 40],                // min, max: sets the vertical scale
  "vertical_exaggeration": 8             // honest relief is nearly flat at this scale
}
```

## Routes

- `/` cover page (server component, reads `public/sites/*/site.json` and `layers.json` at build time)
- `/story/<id>` story mode for `lake_mead`, `aletsch`, `donana`, `great_barrier_reef` (`/story` redirects to Lake Mead)
- `/explore` click any point, calls the API's `/sweep`

## Code map

```
src/app/layout.tsx          metadata, Archivo font, <html lang="en">
src/app/globals.css         design tokens and shared pieces (stamp, buttons, evidence, before/after)
src/app/page.tsx            cover page
src/app/landing/            cover styles and the hero year scrubber
src/app/story/[id]/page.tsx static story routes
src/lib/                    shared: cases + number formatting, Stamp, SeriesLine, Evidence, BeforeAfter
src/story/StoryApp.tsx      'use client' boundary: bar, layer picker, year playback
src/story/heights.ts        16-bit PNG / terrain-RGB decoder (full-precision metres)
src/story/Terrain.tsx       CPU relief mesh + slab sides; shader for hillshade, trend and yearly layers
src/story/StoryScene.tsx    canvas, raking sun with shadows, fog, fly-in camera
src/story/StoryPanel.tsx    the case file: verdict, three questions, narrator
src/story/Timeline.tsx      the year scrubber, drawn as the selected record's chart
src/story/useSite.ts        site.json, legends, textures (picks base_hq when sharper)
src/story/story.css         story-mode styles
src/features/explore/       explore mode (MapLibre over NASA Blue Marble)
scripts/sync-sites.mjs      sites/ -> public/sites
```

The visual system is described in `DESIGN.md` at the repo root.

## Placeholder assets

`../sites/_example/` is generated, not measured. Regenerate with:

```bash
uv run --python 3.11 --with pillow --with numpy python ../sites/_example/make_fake_assets.py
```

The preview case is no longer listed in the UI: only real cases appear.
