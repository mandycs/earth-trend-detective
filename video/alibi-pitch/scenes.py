"""Generate the Alibi-brand scenes of the pitch film (turn, ask, stack, answer, promise, close).

Run: python3 scenes.py   (rewrites those compositions/*.html)
Copy and chip wording come from the app's own screens; the only figures (6.5 cm per decade, 77.5%)
are from the recorded Lake Mead run of 15 Nov 2026 (`/detective?replay=mead`); 6.5 matches
sites/lake_mead/site.json (sen_slope_per_decade -6.47).
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "compositions"

FONTS = """  @font-face { font-family: "Archivo"; src: url(assets/fonts/archivo.woff2) format("woff2"); font-weight: 100 900; font-stretch: 62% 125%; }
  @font-face { font-family: "Manrope"; src: url(assets/fonts/manrope.woff2) format("woff2"); font-weight: 200 800; }"""

BASE = """  #ID-root .h { position: absolute; left: 96px; font-family: "Archivo", sans-serif; font-stretch: 75%; font-weight: 800;
        text-transform: uppercase; color: #e9ecee; line-height: 0.92; }
  #ID-root .lab { position: absolute; left: 100px; font-family: "Manrope", sans-serif; font-weight: 700; font-size: 30px;
         letter-spacing: 0.12em; text-transform: uppercase; color: #aeb6bc; }
  #ID-root .src { position: absolute; left: 100px; bottom: 48px; font-family: "Manrope", sans-serif; font-weight: 500;
         font-size: 28px; color: #9aa2a8; }"""

MARK = """<svg id="{p}-mark" viewBox="0 0 200 200" aria-hidden="true">
      <g fill="none" stroke="#e9ecee"><circle cx="100" cy="100" r="74" stroke-width="6"/><ellipse cx="100" cy="100" rx="34" ry="74" stroke-width="3.5"/><line x1="26" y1="100" x2="174" y2="100" stroke-width="3.5"/></g>
      <polyline points="56,128 84,88 114,114 146,62" fill="none" stroke="#c8102e" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
      <g fill="#e9ecee"><circle cx="56" cy="128" r="11"/><circle cx="84" cy="88" r="11"/><circle cx="114" cy="114" r="11"/><circle cx="146" cy="62" r="11"/><circle cx="134" cy="148" r="11"/></g>
      <g fill="#0e1012"><circle cx="56" cy="128" r="4"/><circle cx="84" cy="88" r="4"/><circle cx="114" cy="114" r="4"/><circle cx="146" cy="62" r="4"/><circle cx="134" cy="148" r="4"/></g>
    </svg>"""


def blur_in(sel: str, t: float, d: float = 0.25) -> str:
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


def turn() -> str:
    body = f"""  <p id="t-pre" class="lab" style="top:290px;font-size:56px">So we built</p>
  <div id="t-lock">{MARK.format(p="t")}<div id="t-word">ALIBI</div></div>"""
    tw = [
        blur_in("#t-pre", 0.1, 0.2),
        'tl.fromTo("#t-mark", {opacity: 0, scale: 0.6, rotation: -20}, {opacity: 1, scale: 1, rotation: 0, duration: 0.5, ease: "back.out(1.6)"}, 0.35);',
        'tl.fromTo("#t-word", {clipPath: "inset(0 100% 0 0)"}, {clipPath: "inset(0 0% 0 0)", duration: 0.5, ease: "power3.out"}, 0.6);',
    ]
    style = """  #t-lock { position: absolute; left: 96px; top: 390px; display: flex; align-items: center; gap: 48px; }
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
        tw_chips.append(f'tl.fromTo("#a-c{i}", {{opacity: 0, y: 24}}, {{opacity: 1, y: 0, duration: 0.3, ease: "power3.out"}}, {round(3.6 + i * 0.35, 2)});')
    keys = "".join(f'<i id="a-k{i}">{ch if ch != " " else "&nbsp;"}</i>' for i, ch in enumerate(QUESTION))
    typing = [f'tl.set("#a-k{i}", {{opacity: 1}}, {round(0.5 + i * 0.045, 3)});' for i in range(len(QUESTION))]
    body = f"""  <p id="a-l1" class="lab" style="top:150px">Ask in your own words</p>
  <div id="a-box"><div id="a-q">{keys}<em id="a-caret"></em></div></div>
  <div id="a-place">Lake Mead, USA</div>
  <p id="a-l2" class="lab" style="top:490px">Alibi picks the satellite records</p>
  """ + "\n  ".join(chips)
    tw = [
        'tl.fromTo("#a-l1", {opacity: 0}, {opacity: 1, duration: 0.2}, 0.05);',
        'tl.fromTo("#a-box", {opacity: 0, y: 20}, {opacity: 1, y: 0, duration: 0.3, ease: "power3.out"}, 0.1);',
        *typing,
        'tl.fromTo("#a-caret", {opacity: 1}, {opacity: 0, duration: 0.01, repeat: 9, yoyo: true, repeatDelay: 0.25}, 0.3);',
        'tl.fromTo("#a-place", {opacity: 0, x: -20}, {opacity: 1, x: 0, duration: 0.3, ease: "power3.out"}, 2.7);',
        'tl.fromTo("#a-l2", {opacity: 0}, {opacity: 1, duration: 0.25}, 3.3);',
        *tw_chips,
    ]
    style = """  #a-box { position: absolute; left: 96px; top: 210px; width: 1728px; height: 170px; border: 3px solid #e9ecee; background: #171a1d;
           display: flex; align-items: center; padding: 0 44px; }
  #a-q { font-family: "Manrope", sans-serif; font-weight: 600; font-size: 84px; color: #e9ecee; white-space: nowrap; display: flex; align-items: center; }
  #a-q i { font-style: normal; opacity: 0; }
  #a-caret { display: inline-block; width: 6px; height: 90px; background: #e9ecee; margin-left: 6px; }
  #a-place { position: absolute; left: 96px; top: 400px; font-family: "Manrope", sans-serif; font-weight: 700; font-size: 34px;
             color: #0e1012; background: #e9ecee; padding: 6px 18px; }
  .chip { position: absolute; width: 848px; height: 172px; border: 2px solid #4a5157; background: #15181b; padding: 26px 34px;
          display: flex; flex-direction: column; justify-content: center; gap: 10px; }
  .chip b { font-family: "Manrope", sans-serif; font-weight: 800; font-size: 54px; color: #e9ecee; line-height: 1; }
  .chip span { font-family: "Manrope", sans-serif; font-weight: 500; font-size: 34px; color: #aeb6bc; line-height: 1.1; }"""
    return comp("ask", body, tw, style)


def stack() -> str:
    body = """  <img id="s-img" src="assets/ui/stack.png" alt="">
  <h2 id="s-h1" class="h">Then it lays every record over the same ground.</h2>
  <p class="src">Real screen: Alibi's evidence stack for Lake Mead · MODIS land cover, ground temperature, vegetation</p>"""
    tw = [
        'tl.fromTo("#s-img", {opacity: 0, scale: 0.92, y: 40}, {opacity: 1, scale: 1, y: 0, duration: 0.6, ease: "power3.out"}, 0);',
        'tl.to("#s-img", {scale: 1.07, duration: 4.4, ease: "none"}, 0.6);',
        blur_in("#s-h1", 0.5),
    ]
    style = """  #s-img { position: absolute; left: 40px; top: 90px; width: 1012px; height: 874px; object-fit: contain; transform-origin: 50% 55%; }
  #stack-root .h { left: 1120px; top: 300px; font-size: 120px; width: 720px; }"""
    return comp("stack", body, tw, style)


def answer() -> str:
    body = """  <img id="n-bg" src="assets/ui/map.jpg" alt="">
  <div id="n-dim"></div>
  <p id="n-l" class="lab" style="top:150px">And answers in plain words · Lake Mead, 2003–2024</p>
  <p id="n-1" class="ln">Total water stored fell about 6.5&nbsp;cm per decade. <u>A real drop.</u></p>
  <p id="n-2" class="ln">77.5% of the fall is not explained by the climate we measured.</p>
  <p id="n-3" class="ln">A clue, not proof.</p>
  <p class="src">From a recorded run of Alibi, 15 Nov 2026 · GRACE &amp; GRACE-FO, NASA POWER · every figure checked against the data</p>"""
    tw = [
        'tl.fromTo("#n-bg", {scale: 1.04}, {scale: 1.1, duration: 7, ease: "none"}, 0);',
        'tl.fromTo("#n-l", {opacity: 0}, {opacity: 1, duration: 0.25}, 0.1);',
        blur_in("#n-1", 0.35), blur_in("#n-2", 2.3), blur_in("#n-3", 4.2),
    ]
    style = """  #n-bg { position: absolute; inset: 0; width: 1920px; height: 1080px; object-fit: cover; transform-origin: 70% 50%; }
  #n-dim { position: absolute; inset: 0; background: rgba(14,16,18,0.86); }
  .ln { position: absolute; left: 96px; width: 1700px; font-family: "Manrope", sans-serif; font-weight: 700; color: #e9ecee; line-height: 1.08; }
  #n-1 { top: 220px; font-size: 92px; }
  #n-1 u { text-decoration: none; border-bottom: 6px solid #e9ecee; }
  #n-2 { top: 560px; font-size: 64px; color: #d3d8db; width: 1500px; }
  #n-3 { top: 780px; font-family: "Archivo", sans-serif; font-stretch: 75%; font-weight: 800; font-size: 130px; text-transform: uppercase; }"""
    return comp("answer", body, tw, style)


def promise() -> str:
    body = """  <img id="p-bg" src="assets/sat/mead-hls.jpg" alt="">
  <div id="p-dim"></div>
  <p id="p-1" class="ln">Ask in your own words.</p>
  <p id="p-2" class="ln">It picks the satellites and tests what changed.</p>
  <p id="p-3" class="ln">It tells you what’s real — and what’s only a clue.</p>"""
    tw = [
        'tl.fromTo("#p-bg", {scale: 1.15, xPercent: 2}, {scale: 1.25, xPercent: -2, duration: 7.5, ease: "none"}, 0);',
        blur_in("#p-1", 0.15), blur_in("#p-2", 1.9), blur_in("#p-3", 3.8),
    ]
    style = """  #p-bg { position: absolute; inset: 0; width: 1920px; height: 1080px; object-fit: cover; }
  #p-dim { position: absolute; inset: 0; background: rgba(14,16,18,0.8); }
  .ln { position: absolute; left: 96px; width: 1730px; font-family: "Archivo", sans-serif; font-stretch: 75%; font-weight: 800;
        text-transform: uppercase; color: #e9ecee; line-height: 0.95; font-size: 124px; }
  #p-1 { top: 140px; } #p-2 { top: 330px; } #p-3 { top: 640px; }"""
    return comp("promise", body, tw, style)


def close() -> str:
    body = """  <h2 id="c-1" class="h">NASA-level tools.</h2>
  <h2 id="c-2" class="h">Everyday words.</h2>"""
    tw = [blur_in("#c-1", 0.1), blur_in("#c-2", 0.9)]
    style = """  #c-1, #c-2 { font-size: 200px; white-space: nowrap; }
  #c-1 { top: 280px; }
  #c-2 { top: 530px; }"""
    return comp("close", body, tw, style)


# Real terms from the pipeline and its docs (grep backend/ and docs/): (text, x, y, size, opacity).
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
    ("95% confidence band", 420, 1000, 38, 0.4),
]
GAPS = [0.55, 0.45, 0.36, 0.3, 0.24, 0.2, 0.17, 0.15, 0.13, 0.11, 0.1, 0.09, 0.09, 0.08, 0.08,
        0.07, 0.07, 0.06, 0.06, 0.06, 0.05, 0.05, 0.05, 0.05, 0.05]
JARGON_START = 2.7


def jargon() -> str:
    t, els, tw = JARGON_START, [], []
    for i, (s, x, y, size, op) in enumerate(TERMS):
        els.append(f'<div id="j{i}" class="term" style="left:{x}px;top:{y}px;font-size:{size}px">{s}</div>')
        tw.append(f'tl.fromTo("#j{i}", {{opacity: 0, scale: 1.12}}, {{opacity: {op}, scale: 1, duration: 0.12, ease: "power3.out"}}, {round(t, 3)});')
        t += GAPS[i] if i < len(GAPS) else 0.05
    end = round(t + 0.45, 2)
    body = ('  <h2 id="j-h1" class="h">But reading it takes tools few people speak.</h2>\n  <div id="j-pile">\n    '
            + "\n    ".join(els) + '\n  </div>\n  <h2 id="j-h2" class="h">Nobody told<br>the story.</h2>')
    tweens = [
        blur_in("#j-h1", 0.1),
        'tl.to("#j-h1", {opacity: 0, duration: 0.15, ease: "power2.in"}, %.2f);' % (JARGON_START - 0.15),
        *tw,
        'tl.fromTo("#j-pile", {scale: 1}, {scale: 1.06, duration: %.2f, ease: "power1.in"}, %.2f);' % (end - JARGON_START, JARGON_START),
        'tl.set("#j-pile", {opacity: 0}, %.2f);' % end,
        blur_in("#j-h2", round(end + 0.2, 2)),
    ]
    style = """  .term { position: absolute; white-space: nowrap; font-family: "Manrope", sans-serif; font-weight: 700;
           color: #e9ecee; letter-spacing: -0.01em; line-height: 1; transform-origin: 0% 50%; }
  #j-pile { position: absolute; inset: 0; }
  #j-h1 { top: 330px; font-size: 150px; width: 1500px; }
  #j-h2 { top: 300px; font-size: 230px; width: 1700px; }"""
    return comp("jargon", body, tweens, style)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, fn in [("jargon", jargon), ("turn", turn),("ask", ask), ("stack", stack), ("answer", answer),
                     ("promise", promise), ("close", close)]:
        (OUT / f"{name}.html").write_text(fn())


if __name__ == "__main__":
    main()
