# Alibi — 29.5 s submission video

The NASA Space Apps demo video (hard limit 30.0 s, see `docs/submission/video-30s.md`), cut down from the 71.2 s
web pitch film in `video/alibi-pitch/`. HyperFrames, 1920 x 1080, 30 fps, H.264.

## Render (one command)

```bash
cd video/pitch-30s
./render.sh                                                # no track -> renders/alibi-30s-nomusic.mp4
LIVE_URL=https://alibi.example.org ./render.sh             # fill the end-card URL
# with music: copy the Artlist file to assets/music/track.mp3, then the same command
LIVE_URL=https://alibi.example.org ./render.sh             # -> renders/alibi-30s-music.mp4
NOMUSIC=1 LIVE_URL=https://alibi.example.org ./render.sh   # force the silent version
```

`render.sh` cuts `track.mp3` to 29.5 s (40 ms fade-in, 1.8 s fade-out from 27.7 s, loudness -16 LUFS), regenerates
`index.html` + `compositions/*.html` with `build.py`, renders, and fails if the file is longer than 29.6 s.
`LIVE_URL` defaults to the literal text `[LIVE_URL]`. The track and its cut are git-ignored (licence terms);
credit the track in the submission description.

Edit the film in `build.py` only: every composition and `index.html` are generated from it (`TIMELINE` holds the
cut points). `npm run check` lints, `npx hyperframes@0.9.47 snapshot --at 4,9,15` shows frames.

## Shots

| Time | Scene | On screen |
|---|---|---|
| 0.0–3.9 | `mead` | Lake Mead, yearly water level 2003→2014 (USBR level on USGS lidar + NAIP) |
| 3.9–5.6 | `saw` | "The satellites saw it all." |
| 5.6–10.9 | `jargon` | "But reading it takes tools few people speak." → wall of real pipeline terms → "Nobody told the story." |
| 10.9–12.7 | `turn` | "So we built" + Alibi mark + ALIBI |
| 12.7–17.0 | `ask` | "Is the water going down where I live?" typed; Lake Mead chip; four satellite/test chips in the app's wording |
| 17.0–19.4 | `stack` | Real evidence-stack screenshot: "Every record on the same ground." |
| 19.4–23.1 | `answer` | "Total water stored fell about 6.5 cm per decade. A real drop." / "A clue, not proof." |
| 23.1–25.2 | `close` | "NASA-level tools. Everyday words." |
| 24.8–29.5 | `sting` | Mark draws itself, ALIBI, "Ask anywhere.", end card `[LIVE_URL]` + github.com/mandycs/earth-trend-detective (held 2.6 s) |

**Figures:** only one, "about 6.5 cm per decade", from the recorded run of 15 Nov 2026 (`/detective?replay=mead`),
matching `sites/lake_mead/site.json` (`sen_slope_per_decade` -6.47). No NASA logos, no AI imagery, no people.
Sources of every image: see `video/alibi-pitch/SPEC.md` (same files, Lake Mead only).

## Music brief (for Artlist)

The film is silent by design (text carries it), so the track only sets pace. Look for:

- **Tempo:** 110–125 BPM, steady pulse from bar one (no long intro: the first cut lands at 0.27 s per year).
- **Mood:** curious → confident. Minimal electronic / modern cinematic pulse: muted plucks or ticking synth,
  light percussion, a lift or drop around **10.9 s** ("So we built ALIBI") and a resolved, warm ending by 29 s.
- **Avoid:** vocals, epic trailer hits, "corporate ukulele", lo-fi hip-hop, anything that sounds like a news
  sting. Instrumental only.
- **Length:** anything ≥ 30 s; `render.sh` takes the first 29.5 s. If the best part starts later, trim it first
  (`ffmpeg -ss <start> -i in.mp3 -t 31 assets/music/track.mp3`).
- Check the Artlist licence covers online/competition use and keep the licence certificate.
