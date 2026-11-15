"""Generate every scene and index.html of the 29.5 s submission cut of the Alibi pitch film.

Run: python3 build.py [--music assets/music/track-cut.mp3] [--live-url https://...]
     (normally called by ./render.sh, which also cuts the music and renders)

Cut down from video/alibi-pitch (71.2 s): one site only (Lake Mead), faster pace, same brand.
The only figure on screen is "about 6.5 cm per decade", from the recorded Lake Mead run of
15 Nov 2026 (`/detective?replay=mead`); it matches sites/lake_mead/site.json
(sen_slope_per_decade -6.47). Nothing else is a number.
"""

from __future__ import annotations

import argparse
import html
import pathlib

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "compositions"
TOTAL = 29.5
GITHUB = "github.com/mandycs/earth-trend-detective"
GRADE = (ROOT / "grade.attr").read_text().strip()

# (id, start, duration, track). Overlaps are intentional: the sting fades in over "close".
TIMELINE = [
    ("mead", 0.0, 3.9, 1),
    ("saw", 3.9, 1.7, 1),
    ("jargon", 5.6, 5.3, 1),
    ("turn", 10.9, 1.8, 1),
    ("ask", 12.7, 4.3, 1),
    ("stack", 17.0, 2.4, 1),
    ("answer", 19.4, 3.7, 1),
    ("close", 23.1, 2.1, 1),
    ("sting", 24.8, 4.7, 4),  # ends at 29.5; end card holds from ~26.9 (2.6 s)
]

FONTS = """  @font-face { font-family: "Archivo"; src: url(assets/fonts/archivo.woff2) format("woff2"); font-weight: 100 900; font-stretch: 62% 125%; }
  @font-face { font-family: "Manrope"; src: url(assets/fonts/manrope.woff2) format("woff2"); font-weight: 200 800; }"""

BASE = """  #ID-root .h { position: absolute; left: 96px; font-family: "Archivo", sans-serif; font-stretch: 75%; font-weight: 800;
        text-transform: uppercase; color: #e9ecee; line-height: 0.92; }
  #ID-root .lab { position: absolute; left: 100px; font-family: "Manrope", sans-serif; font-weight: 700; font-size: 34px;
         letter-spacing: 0.12em; text-transform: uppercase; color: #aeb6bc; }
  #ID-root .src { position: absolute; left: 100px; bottom: 56px; font-family: "Manrope", sans-serif; font-weight: 500;
         font-size: 28px; color: #9aa2a8; }"""

MARK = """<svg id="{p}-mark" viewBox="0 0 200 200" aria-hidden="true">
      <g fill="none" stroke="#e9ecee"><circle cx="100" cy="100" r="74" stroke-width="6"/><ellipse cx="100" cy="100" rx="34" ry="74" stroke-width="3.5"/><line x1="26" y1="100" x2="174" y2="100" stroke-width="3.5"/></g>
      <polyline points="56,128 84,88 114,114 146,62" fill="none" stroke="#c8102e" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
      <g fill="#e9ecee"><circle cx="56" cy="128" r="11"/><circle cx="84" cy="88" r="11"/><circle cx="114" cy="114" r="11"/><circle cx="146" cy="62" r="11"/><circle cx="134" cy="148" r="11"/></g>
      <g fill="#0e1012"><circle cx="56" cy="128" r="4"/><circle cx="84" cy="88" r="4"/><circle cx="114" cy="114" r="4"/><circle cx="146" cy="62" r="4"/><circle cx="134" cy="148" r="4"/></g>
    </svg>"""


def dur(cid: str) -> float:
    return next(d for i, _, d, _ in TIMELINE if i == cid)


def blur_in(sel: str, t: float, d: float = 0.22) -> str:
    return (f'tl.fromTo("{sel}", {{opacity: 0, filter: "blur(10px)"}}, '
            f'{{opacity: 1, filter: "blur(0px)", duration: {d}, ease: "power4.out"}}, {t});')


def comp(cid: str, body: str, tweens: list[str], style: str, bg: str = "#0e1012") -> str:
    tl = "\n  ".join(tweens)
    return f"""<template>
<style>
{FONTS}
  #{cid}-root {{ position: absolute; inset: 0; overflow: hidden; background: {bg}; }}
{BASE.replace("ID", cid)}
{style}
</style>
<div id="{cid}-root" data-composition-id="{cid}" data-width="1920" data-height="1080" data-layout-allow-overlap>
{body}
</div>
<script>
  const tl = gsap.timeline({{ paused: true }});
  {tl}
  window.__timelines["{cid}"] = tl;
</script>
</template>
"""


# ---------------------------------------------------------------- 0-5.6 s: one place, changing


PHOTO_STYLE = """
  #mead-root { position: absolute; inset: 0; overflow: hidden; background: #0B0907; }
  .cam { position: absolute; inset: 0; transform-origin: 42% 50%; }
  .shot { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; object-fit: cover; object-position: 41.7% 27%; }
  .bar { position: absolute; left: 0; width: 1920px; height: 138px; background: #000; z-index: 20; }
  .bar.top { top: 0; } .bar.bot { bottom: 0; }
  .scrim { position: absolute; inset: 0; z-index: 8; pointer-events: none;
           background: radial-gradient(120% 70% at 0% 100%, rgba(11,9,7,0.82) 0%, rgba(11,9,7,0.5) 38%, rgba(11,9,7,0) 70%),
                       radial-gradient(60% 55% at 0% 0%, rgba(11,9,7,0.7) 0%, rgba(11,9,7,0) 70%); }
  .year { position: absolute; left: 96px; top: 168px; z-index: 10; font-family: "League Gothic", sans-serif;
          font-size: 300px; line-height: 0.82; color: #EDE3D1; letter-spacing: 0.01em; }
  .title { position: absolute; left: 96px; bottom: 236px; z-index: 10; font-family: "League Gothic", sans-serif;
           font-size: 150px; line-height: 0.9; color: #EDE3D1; text-transform: uppercase; letter-spacing: 0.01em; }
  .source { position: absolute; left: 100px; bottom: 52px; z-index: 30; font-family: "Oswald", sans-serif;
            font-weight: 400; font-size: 24px; color: rgba(237,227,209,0.7); text-transform: uppercase;
            letter-spacing: 0.14em; }
"""

FADE = 4 / 30  # 4-frame cross-dissolve between years
STEP = 0.27


def mead() -> str:
    d = dur("mead")
    ys = sorted(p.stem for p in (ROOT / "assets" / "mead").glob("*.jpg"))
    imgs, labels, tw = [], [], []
    for i, y in enumerate(ys):
        t0 = round(i * STEP, 3)
        last = i == len(ys) - 1
        cd = round(d - t0, 3) if last else round(STEP + FADE, 3)
        imgs.append(f'<img {GRADE} id="mead-{y}" class="clip shot" src="assets/mead/{y}.jpg" alt="" '
                    f'data-start="{t0}" data-duration="{cd}" data-track-index="{i % 2}" style="z-index:{i + 1}" />')
        yd = round(d - t0, 3) if last else round(STEP, 3)
        labels.append(f'<div id="mead-y{y}" class="clip year" data-start="{t0}" data-duration="{yd}" '
                      f'data-track-index="3">{y}</div>')
        if i:
            tw.append(f'tl.fromTo("#mead-{y}", {{opacity: 0}}, {{opacity: 1, duration: {FADE:.3f}, ease: "none"}}, {t0});')
    tw += [
        f'tl.fromTo("#mead-cam", {{scale: 1.22, xPercent: 0}}, {{scale: 1.34, xPercent: -1.5, duration: {d}, ease: "power1.inOut"}}, 0);',
        'tl.fromTo("#mead-title", {opacity: 0, filter: "blur(10px)"}, {opacity: 1, filter: "blur(0px)", duration: 0.2, ease: "power4.out"}, 0.15);',
    ]
    body = f"""  <div id="mead-cam" class="cam">
    {chr(10).join('    ' + x for x in imgs).strip()}
  </div>
  <div class="scrim" data-layout-ignore></div>
  {chr(10).join('  ' + x for x in labels).strip()}
  <h2 id="mead-title" class="title">Lake Mead, USA</h2>
  <div class="bar top"></div>
  <div class="bar bot"></div>
  <p class="source" data-layout-ignore>Water drawn at the yearly USBR level on 2018 USGS lidar · USDA NAIP</p>"""
    return f"""<template>
<style>{PHOTO_STYLE}</style>
<div id="mead-root" data-composition-id="mead" data-width="1920" data-height="1080" data-layout-allow-overlap>
{body}
</div>
<script>
  const tl = gsap.timeline({{ paused: true }});
  {chr(10).join('  ' + x for x in tw).strip()}
  window.__timelines["mead"] = tl;
</script>
</template>
"""


def saw() -> str:
    d = dur("saw")
    return f"""<template>
<style>
  #saw-root {{ position: absolute; inset: 0; overflow: hidden; background: #0B0907; }}
  #saw-cam {{ position: absolute; inset: 0; transform-origin: 42% 50%; }}
  #saw-bg {{ position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; object-fit: cover; object-position: 41.7% 27%; }}
  .bar {{ position: absolute; left: 0; width: 1920px; height: 138px; background: #000; z-index: 20; }}
  .bar.top {{ top: 0; }} .bar.bot {{ bottom: 0; }}
  #saw-dim {{ position: absolute; inset: 0; background: #0B0907; z-index: 5; }}
  #saw-line {{ position: absolute; left: 96px; top: 330px; z-index: 10; font-family: "League Gothic", sans-serif;
        font-size: 230px; line-height: 0.88; color: #EDE3D1; text-transform: uppercase; letter-spacing: 0.01em; }}
</style>
<div id="saw-root" data-composition-id="saw" data-width="1920" data-height="1080" data-layout-allow-overlap>
  <div id="saw-cam">
    <img {GRADE} id="saw-img" class="clip" style="position:absolute;inset:0" src="assets/mead/2014.jpg" alt="" data-start="0" data-duration="{d}" data-track-index="0" />
  </div>
  <div id="saw-dim"></div>
  <h2 id="saw-line">The satellites<br>saw it all.</h2>
  <div class="bar top"></div>
  <div class="bar bot"></div>
</div>
<script>
  const tl = gsap.timeline({{ paused: true }});
  tl.fromTo("#saw-cam", {{scale: 1.34}}, {{scale: 1.4, duration: {d}, ease: "none"}}, 0);
  tl.fromTo("#saw-dim", {{opacity: 0}}, {{opacity: 0.66, duration: 0.25, ease: "power2.inOut"}}, 0);
  tl.fromTo("#saw-line", {{opacity: 0, filter: "blur(10px)"}}, {{opacity: 1, filter: "blur(0px)", duration: 0.2, ease: "power4.out"}}, 0.1);
  window.__timelines["saw"] = tl;
</script>
</template>
"""


# ---------------------------------------------------------------- 5.6-10.9 s: the jargon wall

# Real terms from the pipeline and its docs: (text, x, y, size, opacity).
TERMS = [
    ("MOD11A2 v061", 110, 300, 150, 1.0),
    ("GRACE-FO mascons RL06.3", 640, 560, 104, 1.0),
    ("Mann–Kendall · Hamed &amp; Rao", 180, 780, 96, 1.0),
    ("Sen slope", 1240, 160, 120, 0.9),
    ("ERDDAP", 1380, 820, 130, 0.85),
    ("GLDAS Noah v2.1", 90, 120, 80, 0.8),
    ("AppEEARS", 980, 380, 92, 0.85),
    ("false discovery rate", 120, 520, 70, 0.75),
    ("Benjamini–Hochberg", 1080, 690, 64, 0.7),
    ("MERRA-2", 700, 120, 76, 0.7),
    ("MCD12Q1 IGBP", 80, 940, 58, 0.65),
    ("MOD13A3 NDVI", 1400, 520, 56, 0.65),
    ("IMERG", 620, 900, 88, 0.7),
    ("NASADEM", 1560, 300, 60, 0.6),
    ("HLS S30 / L30", 300, 660, 50, 0.6),
    ("Hydrology Data Rods", 980, 950, 50, 0.6),
    ("OPeNDAP", 520, 250, 54, 0.55),
    ("PO.DAAC", 1640, 640, 52, 0.55),
    ("GES DISC", 90, 400, 48, 0.55),
    ("autocorrelation", 760, 760, 46, 0.5),
    ("LP DAAC", 1180, 280, 44, 0.5),
    ("Theil–Sen", 420, 420, 44, 0.5),
    ("Earthdata Login", 1300, 420, 40, 0.45),
    ("GIBS WMTS", 860, 220, 42, 0.45),
    ("q-value", 1620, 960, 46, 0.45),
]
GAPS = [0.3, 0.24, 0.2, 0.16, 0.13, 0.11, 0.09, 0.08, 0.07, 0.06, 0.05, 0.05, 0.045, 0.04, 0.04,
        0.035, 0.035, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03]
JARGON_START = 2.0


def jargon() -> str:
    t, els, tw = JARGON_START, [], []
    for i, (s, x, y, size, op) in enumerate(TERMS):
        els.append(f'<div id="j{i}" class="term" style="left:{x}px;top:{y}px;font-size:{size}px">{s}</div>')
        tw.append(f'tl.fromTo("#j{i}", {{opacity: 0, scale: 1.12}}, {{opacity: {op}, scale: 1, duration: 0.1, ease: "power3.out"}}, {round(t, 3)});')
        t += 0.6 * (GAPS[i] if i < len(GAPS) else 0.03)
    end = round(t + 0.3, 2)
    body = ('  <h2 id="j-h1" class="h">But reading it takes tools few people speak.</h2>\n  <div id="j-pile">\n    '
            + "\n    ".join(els) + '\n  </div>\n  <h2 id="j-h2" class="h">Nobody told<br>the story.</h2>')
    tweens = [
        blur_in("#j-h1", 0.05, 0.2),
        'tl.to("#j-h1", {opacity: 0, duration: 0.12, ease: "power2.in"}, %.2f);' % (JARGON_START - 0.12),
        *tw,
        'tl.fromTo("#j-pile", {scale: 1}, {scale: 1.06, duration: %.2f, ease: "power1.in"}, %.2f);' % (end - JARGON_START, JARGON_START),
        'tl.set("#j-pile", {opacity: 0}, %.2f);' % end,
        blur_in("#j-h2", round(end + 0.05, 2)),
    ]
    style = """  .term { position: absolute; white-space: nowrap; font-family: "Manrope", sans-serif; font-weight: 700;
           color: #e9ecee; letter-spacing: -0.01em; line-height: 1; transform-origin: 0% 50%; }
  #j-pile { position: absolute; inset: 0; }
  #j-h1 { top: 300px; font-size: 170px; width: 1700px; }
  #j-h2 { top: 300px; font-size: 230px; width: 1700px; }"""
    return comp("jargon", body, tweens, style)


# ---------------------------------------------------------------- 10.9-23.1 s: Alibi


def turn() -> str:
    body = f"""  <p id="t-pre" class="lab" style="top:290px;font-size:64px">So we built</p>
  <div id="t-lock">{MARK.format(p="t")}<div id="t-word">ALIBI</div></div>"""
    tw = [
        blur_in("#t-pre", 0.05, 0.18),
        'tl.fromTo("#t-mark", {opacity: 0, scale: 0.6, rotation: -20}, {opacity: 1, scale: 1, rotation: 0, duration: 0.4, ease: "back.out(1.6)"}, 0.2);',
        'tl.fromTo("#t-word", {clipPath: "inset(0 100% 0 0)"}, {clipPath: "inset(0 0% 0 0)", duration: 0.4, ease: "power3.out"}, 0.4);',
    ]
    style = """  #t-lock { position: absolute; left: 96px; top: 400px; display: flex; align-items: center; gap: 48px; }
  #t-mark { width: 300px; height: 300px; display: block; }
  #t-word { font-family: "Archivo", sans-serif; font-stretch: 112%; font-weight: 800; font-size: 260px; line-height: 0.9;
            letter-spacing: 0.04em; color: #e9ecee; }"""
    return comp("turn", body, tw, style)


QUESTION = "Is the water going down where I live?"
CHIPS = [
    ("Total water stored", "GRACE &amp; GRACE-FO gravity satellites"),
    ("Rainfall", "GPM rain satellites + MERRA-2"),
    ("Air temperature", "MERRA-2 weather model"),
    ("Is it real?", "A trend test on every record"),
]


def ask() -> str:
    chips, tw_chips = [], []
    for i, (a, b) in enumerate(CHIPS):
        r, c = divmod(i, 2)
        chips.append(f'<div id="a-c{i}" class="chip" style="left:{96 + c * 880}px;top:{560 + r * 200}px"><b>{a}</b><span>{b}</span></div>')
        tw_chips.append(f'tl.fromTo("#a-c{i}", {{opacity: 0, y: 24}}, {{opacity: 1, y: 0, duration: 0.25, ease: "power3.out"}}, {round(2.0 + i * 0.18, 2)});')
    keys = "".join(f'<i id="a-k{i}">{ch if ch != " " else "&nbsp;"}</i>' for i, ch in enumerate(QUESTION))
    typing = [f'tl.set("#a-k{i}", {{opacity: 1}}, {round(0.3 + i * 0.028, 3)});' for i in range(len(QUESTION))]
    body = f"""  <p id="a-l1" class="lab" style="top:150px">Ask in your own words</p>
  <div id="a-box"><div id="a-q">{keys}<em id="a-caret"></em></div></div>
  <div id="a-place">Lake Mead, USA</div>
  <p id="a-l2" class="lab" style="top:490px">Alibi picks the satellites and the tests</p>
  """ + "\n  ".join(chips)
    tw = [
        'tl.fromTo("#a-l1", {opacity: 0}, {opacity: 1, duration: 0.15}, 0.0);',
        'tl.fromTo("#a-box", {opacity: 0, y: 20}, {opacity: 1, y: 0, duration: 0.25, ease: "power3.out"}, 0.05);',
        *typing,
        'tl.fromTo("#a-caret", {opacity: 1}, {opacity: 0, duration: 0.01, repeat: 5, yoyo: true, repeatDelay: 0.22}, 0.2);',
        'tl.fromTo("#a-place", {opacity: 0, x: -20}, {opacity: 1, x: 0, duration: 0.25, ease: "power3.out"}, 1.45);',
        'tl.fromTo("#a-l2", {opacity: 0}, {opacity: 1, duration: 0.2}, 1.8);',
        *tw_chips,
    ]
    style = """  #a-box { position: absolute; left: 96px; top: 210px; width: 1728px; height: 170px; border: 3px solid #e9ecee; background: #171a1d;
           display: flex; align-items: center; padding: 0 44px; }
  #a-q { font-family: "Manrope", sans-serif; font-weight: 600; font-size: 84px; color: #e9ecee; white-space: nowrap; display: flex; align-items: center; }
  #a-q i { font-style: normal; opacity: 0; }
  #a-caret { display: inline-block; width: 6px; height: 90px; background: #e9ecee; margin-left: 6px; }
  #a-place { position: absolute; left: 96px; top: 400px; font-family: "Manrope", sans-serif; font-weight: 700; font-size: 38px;
             color: #0e1012; background: #e9ecee; padding: 6px 18px; }
  .chip { position: absolute; width: 848px; height: 172px; border: 2px solid #4a5157; background: #15181b; padding: 26px 34px;
          display: flex; flex-direction: column; justify-content: center; gap: 10px; }
  .chip b { font-family: "Manrope", sans-serif; font-weight: 800; font-size: 58px; color: #e9ecee; line-height: 1; }
  .chip span { font-family: "Manrope", sans-serif; font-weight: 500; font-size: 36px; color: #aeb6bc; line-height: 1.1; }"""
    return comp("ask", body, tw, style)


def stack() -> str:
    d = dur("stack")
    body = """  <img id="s-img" src="assets/ui/stack.png" alt="">
  <h2 id="s-h1" class="h">Every record on the same ground.</h2>
  <p class="src">Real screen: Alibi's evidence stack for Lake Mead</p>"""
    tw = [
        'tl.fromTo("#s-img", {opacity: 0, scale: 0.92, y: 40}, {opacity: 1, scale: 1, y: 0, duration: 0.45, ease: "power3.out"}, 0);',
        f'tl.to("#s-img", {{scale: 1.06, duration: {d - 0.45:.2f}, ease: "none"}}, 0.45);',
        blur_in("#s-h1", 0.25),
    ]
    style = """  #s-img { position: absolute; left: 40px; top: 90px; width: 1012px; height: 874px; object-fit: contain; transform-origin: 50% 55%; }
  #stack-root .h { left: 1120px; top: 300px; font-size: 136px; width: 720px; }"""
    return comp("stack", body, tw, style)


def answer() -> str:
    d = dur("answer")
    body = """  <img id="n-bg" src="assets/ui/map.jpg" alt="">
  <div id="n-dim"></div>
  <p id="n-l" class="lab" style="top:170px">And answers in plain words · Lake Mead, 2003–2024</p>
  <p id="n-1" class="ln">Total water stored fell about 6.5&nbsp;cm per decade. <u>A real drop.</u></p>
  <p id="n-3" class="ln">A clue, not proof.</p>
  <p class="src">From a recorded run of Alibi, 15 Nov 2026 · GRACE &amp; GRACE-FO · every figure checked against the data</p>"""
    tw = [
        f'tl.fromTo("#n-bg", {{scale: 1.04}}, {{scale: 1.1, duration: {d}, ease: "none"}}, 0);',
        'tl.fromTo("#n-l", {opacity: 0}, {opacity: 1, duration: 0.2}, 0.05);',
        blur_in("#n-1", 0.2), blur_in("#n-3", 1.9),
    ]
    style = """  #n-bg { position: absolute; inset: 0; width: 1920px; height: 1080px; object-fit: cover; transform-origin: 70% 50%; }
  #n-dim { position: absolute; inset: 0; background: rgba(14,16,18,0.86); }
  .ln { position: absolute; left: 96px; width: 1700px; font-family: "Manrope", sans-serif; font-weight: 700; color: #e9ecee; line-height: 1.08; }
  #n-1 { top: 250px; font-size: 100px; }
  #n-1 u { text-decoration: none; border-bottom: 6px solid #e9ecee; }
  #n-3 { top: 680px; font-family: "Archivo", sans-serif; font-stretch: 75%; font-weight: 800; font-size: 150px; text-transform: uppercase; }"""
    return comp("answer", body, tw, style)


# ---------------------------------------------------------------- 23.1-29.5 s: promise, mark, end card


def close() -> str:
    body = """  <h2 id="c-1" class="h">NASA-level tools.</h2>
  <h2 id="c-2" class="h">Everyday words.</h2>"""
    tw = [blur_in("#c-1", 0.05), blur_in("#c-2", 0.55)]
    style = """  #c-1, #c-2 { font-size: 200px; white-space: nowrap; }
  #c-1 { top: 280px; }
  #c-2 { top: 530px; }"""
    return comp("close", body, tw, style)


def sting(live_url: str) -> str:
    """The Alibi mark draws itself (timings of video/alibi-pitch sting x0.5), then becomes the end card."""
    url = html.escape(live_url)
    return f"""<template>
<style>
{FONTS}
  #sting-root {{ position: absolute; inset: 0; background: transparent; z-index: 50; }}
  #sting-bg {{ position: absolute; inset: 0; background: #0e1012; opacity: 0; }}
  #sting-root .lockup {{ position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
            display: flex; align-items: center; gap: 56px; }}
  #mark {{ width: 400px; height: 400px; display: block; overflow: visible; }}
  #sting-root .text {{ display: flex; flex-direction: column; }}
  #word {{ font-family: "Archivo", sans-serif; font-stretch: 112%; font-weight: 800; font-size: 210px;
          line-height: 0.9; letter-spacing: 0.04em; color: #e9ecee; clip-path: inset(0 100% 0 0); }}
  #tag {{ margin-top: 22px; font-family: "Manrope", sans-serif; font-weight: 500; font-size: 68px;
         color: #c3cacf; letter-spacing: 0.01em; opacity: 0; white-space: nowrap; }}
  #end {{ position: absolute; left: 0; right: 0; top: 790px; text-align: center; opacity: 0; }}
  #end-url {{ font-family: "Manrope", sans-serif; font-weight: 800; font-size: 76px; color: #e9ecee; letter-spacing: 0.005em; }}
  #end-gh {{ margin-top: 18px; font-family: "Manrope", sans-serif; font-weight: 600; font-size: 44px; color: #aeb6bc; }}
</style>
<div id="sting-root" data-composition-id="sting" data-width="1920" data-height="1080" data-layout-allow-overlap>
  <div id="sting-bg"></div>
  <div class="lockup" id="lockup">
    <svg id="mark" viewBox="0 0 200 200" role="img" aria-label="Alibi">
      <g fill="none" stroke="#e9ecee">
        <circle id="g-outline" cx="100" cy="100" r="74" stroke-width="6" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" transform="rotate(-90 100 100)"/>
        <ellipse id="g-meridian" opacity="0" cx="100" cy="100" rx="34" ry="74" stroke-width="3.5" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>
        <line id="g-equator" opacity="0" x1="26" y1="100" x2="174" y2="100" stroke-width="3.5" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>
      </g>
      <polyline id="thread" opacity="0" points="56,128 84,88 114,114 146,62" fill="none" stroke="#c8102e" stroke-width="7"
                stroke-linecap="round" stroke-linejoin="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>
      <g class="pin" id="p1"><circle cx="56" cy="128" r="11" fill="#e9ecee"/><circle cx="56" cy="128" r="4" fill="#0e1012"/></g>
      <g class="pin" id="p2"><circle cx="84" cy="88" r="11" fill="#e9ecee"/><circle cx="84" cy="88" r="4" fill="#0e1012"/></g>
      <g class="pin" id="p3"><circle cx="114" cy="114" r="11" fill="#e9ecee"/><circle cx="114" cy="114" r="4" fill="#0e1012"/></g>
      <g class="pin" id="p4"><circle cx="146" cy="62" r="11" fill="#e9ecee"/><circle cx="146" cy="62" r="4" fill="#0e1012"/></g>
      <g class="pin" id="p5"><circle cx="134" cy="148" r="11" fill="#e9ecee"/><circle cx="134" cy="148" r="4" fill="#0e1012"/></g>
    </svg>
    <div class="text">
      <div id="word">ALIBI</div>
      <div id="tag">Ask anywhere.</div>
    </div>
  </div>
  <div id="end">
    <div id="end-url">{url}</div>
    <div id="end-gh">{GITHUB}</div>
  </div>
</div>
<script>
  const tl = gsap.timeline({{ paused: true }});
  tl.to("#sting-bg", {{ opacity: 1, duration: 0.4, ease: "power2.inOut" }}, 0);
  tl.to("#g-outline", {{ strokeDashoffset: 0, duration: 0.5, ease: "power2.inOut" }}, 0.15);
  tl.set(["#g-meridian", "#g-equator"], {{ opacity: 1 }}, 0.35);
  tl.to("#g-meridian", {{ strokeDashoffset: 0, duration: 0.4, ease: "power2.inOut" }}, 0.35);
  tl.to("#g-equator", {{ strokeDashoffset: 0, duration: 0.35, ease: "power2.inOut" }}, 0.4);
  tl.set("#g-outline", {{ strokeDasharray: "none" }}, 0.66);
  ["#p1", "#p2", "#p3", "#p4"].forEach((id, i) => {{
    tl.fromTo(id, {{ opacity: 0, y: -26, scale: 1.5, transformOrigin: "50% 50%" }},
                  {{ opacity: 1, y: 0, scale: 1, duration: 0.2, ease: "back.out(2.2)" }}, 0.7 + i * 0.09);
  }});
  tl.set("#thread", {{ opacity: 1 }}, 1.1);
  tl.to("#thread", {{ strokeDashoffset: 0, duration: 0.4, ease: "power3.inOut" }}, 1.1);
  tl.fromTo("#p5", {{ opacity: 0, y: -26, scale: 1.5, transformOrigin: "50% 50%" }},
                   {{ opacity: 1, y: 0, scale: 1, duration: 0.22, ease: "back.out(2.2)" }}, 1.55);
  tl.fromTo("#p5", {{ rotation: 0 }}, {{ rotation: 8, duration: 0.08, yoyo: true, repeat: 3, ease: "sine.inOut", svgOrigin: "134 148" }}, 1.75);
  tl.fromTo("#mark", {{ x: 385 }}, {{ x: 0, duration: 0.45, ease: "power3.inOut" }}, 1.8);
  tl.fromTo("#word", {{ clipPath: "inset(0 100% 0 0)" }}, {{ clipPath: "inset(0 0% 0 0)", duration: 0.4, ease: "power3.out" }}, 1.95);
  tl.fromTo("#tag", {{ opacity: 0, y: 12 }}, {{ opacity: 1, y: 0, duration: 0.3, ease: "power2.out" }}, 2.2);
  // End card: the lockup rises, the links arrive and hold to the last frame.
  tl.fromTo("#lockup", {{ yPercent: -50 }}, {{ yPercent: -78, duration: 0.4, ease: "power3.inOut" }}, 2.0);
  tl.fromTo("#end", {{ opacity: 0, y: 16 }}, {{ opacity: 1, y: 0, duration: 0.3, ease: "power2.out" }}, 2.1);
  window.__timelines["sting"] = tl;
</script>
</template>
"""


# ---------------------------------------------------------------- index.html


def index(music: str | None) -> str:
    rows = []
    for cid, start, d, track in TIMELINE:
        z = ' style="z-index:50"' if cid == "sting" else ""
        rows.append(f'  <div id="{cid}"{z} data-composition-id="{cid}" data-composition-src="compositions/{cid}.html" '
                    f'data-start="{start}" data-duration="{d}" data-track-index="{track}" data-track-kind="graphics" '
                    f'data-width="1920" data-height="1080"></div>')
    if music:
        rows.append(f'  <!-- Music slot: {music} is assets/music/track.mp3 cut to {TOTAL} s by render.sh -->')
        rows.append(f'  <audio id="music" src="{music}" data-start="0" data-duration="{TOTAL}" data-track-index="2" data-volume="0.9"></audio>')
    else:
        rows.append("  <!-- Music slot empty: drop assets/music/track.mp3 and run ./render.sh -->")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1920, height=1080" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
<style>
{FONTS}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #0e1012; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{TOTAL}" data-width="1920" data-height="1080">
{chr(10).join(rows)}
</div>
<script>
  const tl = gsap.timeline({{ paused: true }});
  window.__timelines["main"] = tl;
  tl.seek(0);
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--music", default=None, help="project-relative path of the cut music file, or omit")
    ap.add_argument("--live-url", default="[LIVE_URL]", help="URL shown on the end card")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    scenes = {"mead": mead, "saw": saw, "jargon": jargon, "turn": turn, "ask": ask, "stack": stack,
              "answer": answer, "close": close, "sting": lambda: sting(a.live_url)}
    for name, fn in scenes.items():
        (OUT / f"{name}.html").write_text(fn())
    (ROOT / "index.html").write_text(index(a.music))


if __name__ == "__main__":
    main()
