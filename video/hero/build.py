"""Generate the film's scene files from the image folders.

Run: python3 build.py   (rewrites index.html and compositions/*.html)
Timings and copy follow SPEC.md; every figure is from sites/<id>/site.json.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).parent
FADE = 4 / 30  # 4-frame cross-dissolve between years
BAR = 138  # 2.39:1 letterbox bar height at 1080
# Grade persisted once by `hyperframes media-treatment` (grade.json), reused on every image.
GRADE = (ROOT / "grade.attr").read_text().strip()

SCENES = [
    {
        "id": "mead",
        "start": 0.0,
        "dur": 9.0,
        "folder": "mead",
        "step": 0.6,
        "title": "Lake Mead",
        "title_at": 0.5,
        "fact": "Total water stored&nbsp;&nbsp;−6.5 cm per decade",
        "fact_at": 4.5,
        "source": "Water drawn at the yearly USBR level on 2018 USGS lidar · USDA NAIP",
        "origin": "42% 50%",
        "objpos": "41.7% 27%",
        "zoom": (1.22, 1.36),
    },
    {
        "id": "aletsch",
        "start": 9.0,
        "dur": 8.5,
        "folder": "aletsch",
        "step": 0.4,
        "title": "Aletsch Glacier",
        "title_at": 0.4,
        "fact": "Air temperature&nbsp;&nbsp;+1.0 °C per decade",
        "fact_at": 4.0,
        "source": "swisstopo SWISSIMAGE, newest photo flown each year",
        "origin": "50% 40%",
    },
    {
        "id": "donana",
        "start": 17.5,
        "dur": 7.0,
        "folder": "donana",
        "step": 0.75,
        "title": "Doñana Wetlands",
        "title_at": 0.4,
        "fact": "Topsoil moisture&nbsp;&nbsp;falling, for real",
        "fact_at": 3.5,
        "source": "IGN Spain PNOA, one photo per flight",
        "origin": "50% 50%",
    },
]
CLAIM = {"id": "claim", "start": 24.5, "dur": 5.5}
TOTAL = 30.0

STYLE = """
  #root { position: absolute; inset: 0; overflow: hidden; background: #0B0907; }
  .cam { position: absolute; inset: 0; transform-origin: ORIGIN; }
  .shot { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; object-fit: cover; }
  .bar { position: absolute; left: 0; width: 1920px; height: 138px; background: #000; z-index: 20; }
  .bar.top { top: 0; } .bar.bot { bottom: 0; }
  .txt { opacity: var(--text-opacity, 1); }
  .scrim { position: absolute; inset: 0; z-index: 8; pointer-events: none;
           background: radial-gradient(120% 70% at 0% 100%, rgba(11,9,7,0.82) 0%, rgba(11,9,7,0.5) 38%, rgba(11,9,7,0) 70%),
                       radial-gradient(60% 55% at 0% 0%, rgba(11,9,7,0.7) 0%, rgba(11,9,7,0) 70%); }
  .year { position: absolute; left: 96px; top: 168px; z-index: 10; font-family: "League Gothic", sans-serif;
          font-size: 300px; line-height: 0.82; color: #EDE3D1; letter-spacing: 0.01em; }
  .title { position: absolute; left: 96px; bottom: 236px; z-index: 10; font-family: "League Gothic", sans-serif;
           font-size: 150px; line-height: 0.9; color: #EDE3D1; text-transform: uppercase; letter-spacing: 0.01em; }
  .fact { position: absolute; left: 100px; bottom: 182px; z-index: 10; font-family: "Oswald", sans-serif;
          font-weight: 500; font-size: 34px; color: #EDE3D1; text-transform: uppercase; letter-spacing: 0.12em; }
  .source { position: absolute; left: 100px; bottom: 52px; z-index: 30; font-family: "Oswald", sans-serif;
            font-weight: 400; font-size: 22px; color: rgba(237,227,209,0.62); text-transform: uppercase;
            letter-spacing: 0.14em; }
"""


def years(folder: str) -> list[str]:
    return sorted(p.stem for p in (ROOT / "assets" / folder).glob("*.jpg"))


def scene_html(s: dict) -> str:
    sid = s["id"]
    ys = years(s["folder"])
    step = s["step"]
    imgs, labels, tweens = [], [], []
    for i, y in enumerate(ys):
        t0 = round(i * step, 3)
        last = i == len(ys) - 1
        d = round(s["dur"] - t0, 3) if last else round(step + FADE, 3)
        imgs.append(
            f'<img {GRADE} id="{sid}-{y}" class="clip shot" src="assets/{s["folder"]}/{y}.jpg" alt="" '
            f'data-start="{t0}" data-duration="{d}" data-track-index="{i % 2}" style="z-index:{i + 1}" />'
        )
        yd = round(s["dur"] - t0, 3) if last else round(step, 3)
        labels.append(
            f'<div id="{sid}-y{y}" class="clip year txt" data-start="{t0}" data-duration="{yd}" '
            f'data-track-index="3">{y}</div>'
        )
        if i > 0:
            tweens.append(
                f'tl.fromTo("#{sid}-{y}", {{opacity: 0}}, {{opacity: 1, duration: {FADE:.3f}, ease: "none"}}, {t0});'
            )
    end = s["dur"]
    z0, z1 = s.get("zoom", (1.0, 1.14))
    tweens += [
        f'tl.fromTo("#{sid}-cam", {{scale: {z0}, xPercent: 0}}, {{scale: {z1}, xPercent: -1.5, duration: {end}, ease: "power1.inOut"}}, 0);',
        f'tl.fromTo("#{sid}-title", {{opacity: 0, filter: "blur(10px)"}}, {{opacity: 1, filter: "blur(0px)", duration: 0.2, ease: "power4.out"}}, {s["title_at"]});',
        f'tl.fromTo("#{sid}-fact", {{opacity: 0, filter: "blur(10px)"}}, {{opacity: 1, filter: "blur(0px)", duration: 0.2, ease: "power4.out"}}, {s["fact_at"]});',
        f'tl.to(["#{sid}-title", "#{sid}-fact"], {{opacity: 0, filter: "blur(8px)", duration: 0.17, ease: "power3.in"}}, {end - 0.3});',
    ]
    style = STYLE.replace("ORIGIN", s["origin"]) + (
        f'  .shot {{ object-position: {s["objpos"]}; }}' if s.get("objpos") else "")
    return f"""<template>
<style>{style}</style>
<div id="root" data-composition-id="{sid}" data-width="1920" data-height="1080" data-layout-allow-overlap>
  <div id="{sid}-cam" class="cam">
    {chr(10).join('    ' + x for x in imgs).strip()}
  </div>
  <div class="scrim txt" data-layout-ignore></div>
  {chr(10).join('  ' + x for x in labels).strip()}
  <div id="{sid}-txt" class="txt">
    <h2 id="{sid}-title" class="title">{s["title"]}</h2>
    <p id="{sid}-fact" class="fact">{s["fact"]}</p>
  </div>
  <div class="bar top"></div>
  <div class="bar bot"></div>
  <p class="source txt" data-layout-ignore>{s["source"]}</p>
</div>
<script>
  const tl = gsap.timeline({{ paused: true }});
  {chr(10).join('  ' + x for x in tweens).strip()}
  window.__timelines["{sid}"] = tl;
</script>
</template>
"""


def claim_html() -> str:
    return f"""<template>
<style>{STYLE.replace("ORIGIN", "62% 45%")}
  .dim {{ position: absolute; inset: 0; background: #0B0907; z-index: 5; }}
  .q {{ position: absolute; left: 96px; top: 300px; z-index: 10; font-family: "League Gothic", sans-serif;
        font-size: 190px; line-height: 0.9; color: #EDE3D1; text-transform: uppercase; }}
  .a {{ position: absolute; left: 100px; top: 500px; z-index: 10; font-family: "Oswald", sans-serif; font-weight: 500;
        font-size: 54px; color: #EDE3D1; text-transform: uppercase; letter-spacing: 0.06em; }}
  .a b {{ color: #C8792E; font-weight: 600; }}
  .c {{ position: absolute; left: 100px; top: 580px; z-index: 10; font-family: "Oswald", sans-serif; font-weight: 400;
        font-size: 34px; color: rgba(237,227,209,0.78); text-transform: uppercase; letter-spacing: 0.14em; }}
  .mark {{ position: absolute; left: 96px; bottom: 200px; z-index: 10; font-family: "League Gothic", sans-serif;
           font-size: 96px; color: #EDE3D1; text-transform: uppercase; letter-spacing: 0.04em; }}
</style>
<div id="root" data-composition-id="claim" data-width="1920" data-height="1080" data-layout-allow-overlap>
  <div id="claim-cam" class="cam">
    <img {GRADE} id="claim-bg" class="clip shot" src="assets/mead/2014.jpg" alt="" data-start="0" data-duration="{CLAIM['dur']}" data-track-index="0" />
  </div>
  <div id="claim-dim" class="dim"></div>
  <div class="txt">
    <h2 id="claim-q" class="q">Is it the climate?</h2>
    <p id="claim-a" class="a">At Lake Mead, <b>54–84%</b> is not.</p>
    <p id="claim-c" class="c">A clue, not proof.</p>
    <p id="claim-mark" class="mark">Earth Trend Detective</p>
  </div>
  <div class="bar top"></div>
  <div class="bar bot"></div>
  <p class="source txt" data-layout-ignore>Share of the water loss not explained by rain, heat and sunlight, across climate models</p>
</div>
<script>
  const tl = gsap.timeline({{ paused: true }});
  tl.fromTo("#claim-cam", {{scale: 1.14, xPercent: -1.5}}, {{scale: 1.2, xPercent: -2, duration: {CLAIM['dur']}, ease: "none"}}, 0);
  tl.fromTo("#claim-dim", {{opacity: 0}}, {{opacity: 0.55, duration: 0.5, ease: "power2.inOut"}}, 0);
  tl.fromTo("#claim-q", {{opacity: 0, filter: "blur(10px)"}}, {{opacity: 1, filter: "blur(0px)", duration: 0.2, ease: "power4.out"}}, 0.3);
  tl.fromTo("#claim-a", {{opacity: 0, filter: "blur(10px)"}}, {{opacity: 1, filter: "blur(0px)", duration: 0.2, ease: "power4.out"}}, 1.9);
  tl.fromTo("#claim-c", {{opacity: 0, filter: "blur(10px)"}}, {{opacity: 1, filter: "blur(0px)", duration: 0.2, ease: "power4.out"}}, 2.9);
  tl.fromTo("#claim-mark", {{opacity: 0, filter: "blur(10px)"}}, {{opacity: 1, filter: "blur(0px)", duration: 0.25, ease: "power4.out"}}, 3.3);
  window.__timelines["claim"] = tl;
</script>
</template>
"""


def index_html() -> str:
    hosts = []
    for i, s in enumerate(SCENES + [CLAIM]):
        hosts.append(
            f'<div id="{s["id"]}" data-composition-id="{s["id"]}" data-composition-src="compositions/{s["id"]}.html" '
            f'data-start="{s["start"]}" data-duration="{s["dur"]}" data-track-index="1" data-track-kind="graphics" '
            f'data-width="1920" data-height="1080"></div>'
        )
    variables = json.dumps(
        [{"id": "text-opacity", "type": "number", "label": "Text opacity (0 for the website loop)",
          "default": 1, "min": 0, "max": 1, "step": 1}]
    )
    return f"""<!doctype html>
<html lang="en" data-composition-variables='{variables}'>
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1920, height=1080" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #0B0907; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{TOTAL}" data-width="1920" data-height="1080">
  {chr(10).join('  ' + h for h in hosts).strip()}
  <!-- MUSIC -->
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
    (ROOT / "compositions").mkdir(exist_ok=True)
    for s in SCENES:
        (ROOT / "compositions" / f"{s['id']}.html").write_text(scene_html(s))
    (ROOT / "compositions" / "claim.html").write_text(claim_html())
    index = ROOT / "index.html"
    old = index.read_text() if index.exists() else ""
    music = old[old.index("<!-- MUSIC -->"):old.index("<!-- /MUSIC -->") + 15] if "<!-- /MUSIC -->" in old else "<!-- MUSIC -->"
    index.write_text(index_html().replace("<!-- MUSIC -->", music))


if __name__ == "__main__":
    main()
