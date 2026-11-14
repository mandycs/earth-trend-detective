"""Audit the story-mode data: every field we render, and every file the JSON promises.

Read-only. Prints problems grouped by severity so the console output is the report.
Run: python scripts/audit_sites.py   (from the repo root, stdlib only)
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITES = ROOT / "sites"
VERDICTS = {"real", "likely", "unknown"}
DIRECTIONS = {"up", "down", "flat"}

errors: list[str] = []
warnings: list[str] = []


def err(site: str, message: str) -> None:
    errors.append(f"[{site}] {message}")


def warn(site: str, message: str) -> None:
    warnings.append(f"[{site}] {message}")


def check_asset(site: str, folder: pathlib.Path, name: str, label: str) -> None:
    if not name:
        err(site, f"{label}: empty filename")
        return
    if not (folder / name).exists():
        err(site, f"{label}: missing file {folder.name}/{name}")


def audit(slug: str) -> None:
    folder = SITES / slug
    manifest = folder / "site.json"
    if not manifest.exists():
        err(slug, "no site.json")
        return
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        err(slug, f"site.json is not valid JSON: {exc}")
        return

    for key in ("id", "name", "bbox", "years", "vertical_exaggeration", "assets", "variables", "steps"):
        if key not in data:
            err(slug, f"missing top-level key '{key}'")

    if data.get("id") != slug:
        err(slug, f"id '{data.get('id')}' does not match the folder name")

    bbox = data.get("bbox") or []
    if len(bbox) != 4:
        err(slug, f"bbox has {len(bbox)} values, expected 4")
    else:
        west, south, east, north = bbox
        if not (west < east and south < north):
            err(slug, f"bbox is inverted: {bbox}")
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            err(slug, f"bbox longitude out of range: {bbox}")

    years = data.get("years") or []
    if len(years) != 2 or years[0] >= years[1]:
        err(slug, f"years should be [first, last] ascending, got {years}")

    exaggeration = data.get("vertical_exaggeration")
    if not isinstance(exaggeration, (int, float)) or not (0 < exaggeration <= 60):
        err(slug, f"vertical_exaggeration looks wrong: {exaggeration!r}")

    assets = data.get("assets") or {}
    for key in ("heightmap", "base"):
        check_asset(slug, folder, assets.get(key, ""), key)

    for key in ("heightmap_rgb", "hillshade", "base_hq"):
        if key in assets:
            check_asset(slug, folder, assets.get(key, ""), key)

    trend = assets.get("trend") or {}
    yearly = assets.get("yearly") or {}
    for var_id, name in trend.items():
        check_asset(slug, folder, name, f"trend[{var_id}]")
    for var_id, pattern in yearly.items():
        if "{YYYY}" not in pattern:
            err(slug, f"yearly[{var_id}] has no {{YYYY}} placeholder: {pattern}")
            continue
        missing = [
            year
            for year in range(years[0], years[1] + 1)
            if not (folder / pattern.replace("{YYYY}", str(year))).exists()
        ]
        if missing:
            warn(slug, f"yearly[{var_id}] missing {len(missing)} frames: {missing[:5]}")

    variables = data.get("variables") or []
    seen: set[str] = set()
    for entry in variables:
        var_id = entry.get("id", "?")
        if var_id in seen:
            err(slug, f"duplicate variable id '{var_id}'")
        seen.add(var_id)
        for key in ("id", "label", "unit", "verdict", "direction"):
            if key not in entry:
                err(slug, f"variable '{var_id}' missing '{key}'")
        if entry.get("verdict") not in VERDICTS:
            err(slug, f"variable '{var_id}' has verdict {entry.get('verdict')!r}")
        if entry.get("direction") not in DIRECTIONS:
            err(slug, f"variable '{var_id}' has direction {entry.get('direction')!r}")
        slope = entry.get("sen_slope_per_decade")
        if slope is not None and not isinstance(slope, (int, float)):
            err(slug, f"variable '{var_id}' slope is not numeric: {slope!r}")
        p = entry.get("p_value")
        if p is not None and not (0 <= p <= 1):
            err(slug, f"variable '{var_id}' p_value out of range: {p}")
        q = entry.get("q_value")
        if q is not None and p is not None and q + 1e-9 < p:
            warn(slug, f"variable '{var_id}' q_value {q} < p_value {p}")
        rng = entry.get("residual_pct_range")
        if rng is not None:
            if len(rng) != 2:
                err(slug, f"variable '{var_id}' residual_pct_range is not a pair: {rng}")
            elif not (0 <= rng[0] <= 100 and 0 <= rng[1] <= 100):
                err(slug, f"variable '{var_id}' residual range out of 0-100: {rng}")
            elif rng[0] > rng[1]:
                warn(slug, f"variable '{var_id}' residual range is reversed: {rng}")
        pct = entry.get("residual_pct_non_climate")
        if pct is not None and not (0 <= pct <= 100):
            err(slug, f"variable '{var_id}' residual_pct_non_climate out of range: {pct}")
        if entry.get("verdict") == "real" and p is not None and p > 0.05:
            warn(slug, f"variable '{var_id}' is 'real' but p={p}")
        if entry.get("verdict") == "unknown" and p is not None and p < 0.05:
            warn(slug, f"variable '{var_id}' is 'unknown' but p={p}")
        series = entry.get("series")
        if series is not None:
            if not isinstance(series, list) or len(series) < 2:
                warn(slug, f"variable '{var_id}' has a series with < 2 points")
            else:
                y0 = series[0].get("year")
                y1 = series[-1].get("year")
                if y0 != years[0] or y1 != years[1]:
                    warn(slug, f"variable '{var_id}' series spans {y0}-{y1}, case says {years[0]}-{years[1]}")
                values = [p.get("value") for p in series if isinstance(p.get("value"), (int, float))]
                if len(values) != len(series):
                    err(slug, f"variable '{var_id}' series has non-numeric values")

    for var_id in trend:
        if var_id not in seen:
            err(slug, f"trend raster '{var_id}' has no matching variable")
    for var_id in yearly:
        if var_id not in seen:
            err(slug, f"yearly frames '{var_id}' have no matching variable")

    steps = data.get("steps") or []
    if len(steps) != 3:
        err(slug, f"expected 3 steps, got {len(steps)}")
    for index, step in enumerate(steps):
        if isinstance(step, str):
            if not step.strip():
                err(slug, f"step {index} is an empty string")
        elif not step.get("title"):
            err(slug, f"step {index} has no title")

    for source in data.get("sources") or []:
        url = source.get("url", "")
        if not url.startswith("http"):
            err(slug, f"source '{source.get('title')}' has a bad url: {url!r}")

    # layers.json, if present
    layers_file = folder / "layers.json"
    if layers_file.exists():
        try:
            layers = json.loads(layers_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            err(slug, f"layers.json is not valid JSON: {exc}")
            return
        ids: set[str] = set()
        for layer in layers.get("layers", []):
            layer_id = layer.get("id", "?")
            if layer_id in ids:
                err(slug, f"duplicate layer id '{layer_id}'")
            ids.add(layer_id)
            if layer.get("file"):
                check_asset(slug, folder, layer["file"], f"layer {layer_id}")
            src = layer.get("source") or {}
            if src.get("url") and not str(src["url"]).startswith("http"):
                err(slug, f"layer {layer_id} source url is not http: {src['url']!r}")
        for layer_id in layers.get("fallback", []) or []:
            if layer_id not in ids:
                err(slug, f"fallback layer '{layer_id}' is not defined")


def main() -> None:
    slugs = sorted(p.name for p in SITES.iterdir() if p.is_dir())
    for slug in slugs:
        audit(slug)
    print(f"audited {len(slugs)} sites: {', '.join(slugs)}\n")
    if errors:
        print(f"ERRORS ({len(errors)})")
        for line in errors:
            print("  " + line)
        print()
    if warnings:
        print(f"WARNINGS ({len(warnings)})")
        for line in warnings:
            print("  " + line)
        print()
    if not errors and not warnings:
        print("clean: no errors, no warnings")


if __name__ == "__main__":
    main()
