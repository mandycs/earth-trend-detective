# SPEC — Earth Trend Detective, hero / demo film

GOAL:    the viewer sees three real places change over 22 years and is left with the question
         "Is it the climate?" and an honest answer for one of them.
OUTPUT:  HyperFrames, 1920 x 1080, 30 fps. Two renders: `film` (30 s, text and music) and `loop`
         (0–24.5 s, no text, for the website hero, which adds its own HTML text).
TIME:    30 s x 30 = 900 frames.
LOOK:    ground #0B0907; ink "bone" #EDE3D1; one accent, ember #C8792E, only on the climate share.
         Letterbox 2.39:1: black bars 138 px top and bottom; nothing sits on the bars except the
         small source line.
         Display: League Gothic 400, caps, year at 300 px, case titles at 150 px, tracking 0.01em.
         Small: Oswald 500 caps 26 px, tracking 0.14em, bone at 78%.
         Medium: real aerial and satellite imagery only. Grade on every image: deep contrast,
         saturation −0.35, warm bronze, vignette 0.35, grain 0.16.
OBJECTS: Lake Mead's water (drawn at the USBR level of each year on the 2018 lidar); the Aletsch
         glacier tongue (swisstopo photos per year); Doñana's lagoons (PNOA photos per flight).
MOTION:  camera: one continuous push per case, scale 1.00 → 1.14, `power1.inOut`, plus a 2–3% drift.
         Year changes are hard cuts with a 4-frame cross-dissolve (time-lapse flicker).
         Titles enter as a whole line, blur 10 px → 0 and opacity 0 → 1 in 6 frames, then hold dead
         still; exit blur-out in 5 frames.
SHOTS:
  1. 0.0–9.0   Lake Mead 2003 → 2014, 12 frames x 0.6 s. Year top-left 300 px.
               "LAKE MEAD" at 0.5 s; "TOTAL WATER STORED  −6.5 CM PER DECADE" at 4.5 s.
               Source line: "Water drawn at the yearly USBR level on 2018 USGS lidar".
  2. 9.0–17.5  Aletsch 2003 → 2024, 19 photos x 0.4 s. "ALETSCH GLACIER" at 9.4 s;
               "AIR TEMPERATURE  +1.0 °C PER DECADE" at 13.0 s. Source: "swisstopo SWISSIMAGE".
  3. 17.5–24.5 Doñana 2004 → 2022, 8 photos x 0.75 s. "DOÑANA WETLANDS" at 17.9 s;
               "TOPSOIL MOISTURE  FALLING, FOR REAL" at 21.0 s. Source: "IGN Spain PNOA".
  4. 24.5–30.0 Lake Mead 2014 held, darkened 55%. "IS IT THE CLIMATE?" at 24.8 s (190 px);
               "AT LAKE MEAD, 54–84% IS NOT." at 26.4 s (ember on 54–84%);
               "A CLUE, NOT PROOF." at 27.4 s; wordmark "EARTH TREND DETECTIVE" at 28.4 s, held.
  Sound: war drums with low strings; hits at 0.0, 9.0, 17.5; riser into 24.5; out on 30.0.
BANNED:  dark void with floating elements; glow, flares, particles; everything centred; fade-and-
         slide-up; text moving while read; corner brackets or HUD; logo docked in a corner;
         any figure not in sites/<id>/site.json; "proof" or "cause" claims.
QA:      frames 0.3 (2003 full lake, year legible), 8.5 (2014 shrunken), 13.5 (Aletsch title +
         figure), 21.5 (Doñana figure), 27.0 (question + range), 29.5 (wordmark).
