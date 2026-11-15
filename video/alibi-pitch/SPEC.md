# SPEC — Alibi, web pitch film

GOAL:    sell Alibi on the landing page: NASA-level tools in everyday words. Not a product demo. A curious
         16-year-old should want to try it. Works muted: the text carries the whole story.
OUTPUT:  HyperFrames, 1920 x 1080, 30 fps, 71.2 s. Web copy: `frontend/public/video/alibi-hero.mp4`
         (+ `alibi-hero-poster.jpg`), transcoded with ffmpeg (CRF 27, faststart).
LOOK:    act 1 keeps the look of `video/hero-alibi` (bronze grade, letterbox, League Gothic / Oswald).
         From act 2 on, the Alibi brand (DESIGN.md): ink #e9ecee on #0e1012, Archivo condensed 800 for
         headlines, Manrope for words and UI, thread red only inside the mark.
SOURCES: photos from `video/hero-alibi/assets` (USBR level on USGS lidar + NAIP, swisstopo, IGN PNOA);
         `assets/sat/mead-hls.jpg` and `assets/years/*.jpg` from `sites/lake_mead/` (HLS, MODIS yearly
         daytime ground temperature); `assets/ui/*` are real screenshots of `/detective?replay=mead`
         (recorded run of 15 Nov 2026), taken with Chrome DevTools at 1920 x 1080.
FIGURES: only two, both from that recorded run: "about 6.5 cm per decade" (site.json: −6.47) and
         "77.5%" (inside site.json's residual range 53.6–83.7). Nothing else is a number.
MUSIC:   `assets/music/pitch-71.mp3` = the first 71.2 s of `video/hero-alibi/assets/music/lyria-hero.mp3`
         (the track the current hero film already uses), 3 s fade-out. Provenance of that track is not
         documented in the repo; the file name suggests Google Lyria. Check before the submission video.

SHOTS:
  0.0–13.0  Cold open. Lake Mead 2003→2014, Aletsch 2003→2024, Doñana 2004→2022, years flicker by.
 13.0–16.0  "The satellites saw it all."
 16.0–22.5  "NASA has watched every place on Earth for decades." Wall of 22 yearly MODIS maps of Lake
            Mead over the HLS image. "The data is public."
 22.5–31.5  "But reading it takes tools few people speak." Then the jargon wall: real pipeline terms
            (MOD11A2 v061, GRACE-FO mascons RL06.3, Mann–Kendall · Hamed & Rao, Sen slope, ERDDAP,
            GLDAS Noah v2.1, AppEEARS, false discovery rate…) pile up faster and faster, then cut:
            "Nobody told the story."
 31.5–34.1  "So we built" + Alibi mark and wordmark.
 34.1–42.1  "Ask in your own words": "Is the water going down where I live?" typed; place chip; "Alibi
            picks the satellite records": four chips in the app's own wording.
 42.1–47.1  Real evidence-stack screenshot. "Then it lays every record over the same ground."
 47.1–54.1  "And answers in plain words": the recorded run's answer, then "A clue, not proof."
 54.1–61.6  "Ask in your own words. / It picks the satellites and tests what changed. / It tells you
            what's real — and what's only a clue."
 61.6–64.6  "NASA-level tools. Everyday words."
 64.6–71.2  Sting: globe, pins, red thread, loose pin, ALIBI, "Ask anywhere."
BANNED:  NASA logos; AI imagery presented as data; minors; invented figures; "proof" or "cause" claims.
BUILD:   `python3 build.py` (cold-open scenes), `python3 scenes.py` (Alibi scenes); saw.html, watch.html
         and sting.html are hand-written.
