# Story mode (3D)

The 3D case-study viewer. `../sites/<id>/` is the only input: a `site.json` plus PNGs.
Nothing here invents numbers — every figure on screen comes from `site.json`.

## Run it

```bash
npm install
npm run dev      # http://127.0.0.1:5180
npm run build    # type-check + bundle, copies ../sites into dist/sites
```

The Vite plugin in `vite.config.ts` serves the repo's top-level `sites/` folder at
`/sites/*` in dev and copies it into `dist/sites` on build, so the data pipeline can
keep writing to `sites/` without touching this folder.

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
  "bbox": [-114.9, 35.9, -114.0, 36.6],  // west, south, east, north
  "elevation_m": [300, 1200],            // min, max: sets the vertical scale
  "vertical_exaggeration": 8             // honest relief is nearly flat at this scale
}
```

## Code map

```
src/App.tsx              layout, case switching, year playback
src/story/Terrain.tsx    displaced plane + 3-layer shader (base, trend, yearly)
src/story/StoryScene.tsx canvas, lights, camera, orbit controls
src/story/StoryPanel.tsx the three investigation steps
src/story/Timeline.tsx   play / scrub / crossfade
src/story/useSite.ts     site.json + texture loading, with a per-URL cache
src/story/types.ts       the data contract
```

## Migrating into a Next.js app

`src/story/` is plain React + three.js, no Vite-specific APIs. Copy the folder, add
`'use client'` at the top of the components, and render `StoryScene` through
`dynamic(() => import(...), { ssr: false })`. `useSite` fetches `/sites/<id>/…`, so the
same folder has to end up in Next's `public/sites`.

## Placeholder assets

`../sites/_example/` is generated, not measured. Regenerate with:

```bash
uv run --python 3.11 --with pillow --with numpy python ../sites/_example/make_fake_assets.py
```

The UI shows a "Preview case" flag whenever the site id starts with `_`.
