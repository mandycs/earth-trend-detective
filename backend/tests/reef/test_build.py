"""`python -m app.reef.build`: the whole reef case from injected fakes. Offline, no network."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from PIL import Image

from app.reef import build
from app.reef.points import SITE_ID
from tests.reef.test_dhw import _scout_yearly

START, END = 2003, 2024
LATS = np.array([-20.0, -19.5, -19.0, -18.5, -18.0])  # ascending, as ERDDAP answers
LONS = np.array([146.0, 146.5, 147.0, 147.5, 148.0, 148.5])


class Fakes:
    """The six network callables, each counting its calls."""

    def __init__(self):
        self.calls: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def base(self, bbox, date, out_path):
        self._count("base")
        w, s, e, n = bbox
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (450, round(450 * (n - s) / (e - w))), (20, 60, 120)).save(out_path, "JPEG")
        return out_path

    def mur_year(self, dataset, variable, bbox, start, end, stride):
        self._count("mur_year")
        times = pd.date_range(f"{start}-01-01", periods=12, freq="MS") + pd.Timedelta(days=15)
        months = times.month.to_numpy()
        base = 26.0 + 2.0 * np.cos(2 * np.pi * (months - 2) / 12) + 0.03 * (start - START)
        cube = np.broadcast_to(base[:, None, None], (12, len(LATS), len(LONS))).copy()
        cube[:, 0, 0] = np.nan  # land
        return xr.DataArray(
            cube,
            dims=("time", "latitude", "longitude"),
            coords={"time": times, "latitude": LATS, "longitude": LONS},
            name=variable,
            attrs={"missing_years": []},
        )

    def chlorophyll_point(self, dataset, variable, lat, lon, start, end):
        self._count("chlorophyll_point")
        idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
        rng = np.random.default_rng(3)
        series = pd.Series(np.exp(rng.normal(-0.5, 0.3, len(idx))), index=idx, name=variable)
        series.attrs["missing_years"] = []
        return series, (lat + 0.02, lon - 0.02)

    def dhw_point_year(self, point, years):
        self._count("dhw_point_year")
        per = _scout_yearly()[point.id]
        return {y: per[y] for y in years}

    def gebco(self, bbox):
        self._count("gebco")
        rows, cols = 40, 45
        return np.linspace(-60.0, 300.0, rows * cols).reshape(rows, cols)

    def dhw_day(self, dataset, variable, bbox, day, stride):
        self._count("dhw_day")
        values = np.full((len(LATS), len(LONS)), 6.0)
        values[0, 0] = np.nan
        return xr.DataArray(values, dims=("latitude", "longitude"), coords={"latitude": LATS, "longitude": LONS})

    def fetchers(self) -> build.ReefFetchers:
        return build.ReefFetchers(
            base=self.base,
            mur_year=self.mur_year,
            chlorophyll_point=self.chlorophyll_point,
            dhw_point_year=self.dhw_point_year,
            gebco=self.gebco,
            dhw_day=self.dhw_day,
        )


def _raising() -> build.ReefFetchers:
    def boom(*_args, **_kwargs):
        raise AssertionError("network fetcher called in an offline build")

    return build.ReefFetchers(*(boom,) * 6)


def _build(tmp_path, fetchers, offline=False):
    return build.build_reef(
        sites_dir=tmp_path / "sites", cache_dir=tmp_path / "cache", offline=offline, fetchers=fetchers
    )


def test_build_writes_the_contract(tmp_path):
    fakes = Fakes()
    written = _build(tmp_path, fakes.fetchers())
    site_dir = tmp_path / "sites" / SITE_ID
    names = [
        "base.jpg", "heightmap.png", "heightmap.json", "heightmap_rgb.png", "hillshade.png",
        "trend_sst.png", "trend_sst.json", "layers/dhw/meta.json", "site.json", "layers.json",
        *(f"year_sst_{y}.png" for y in range(START, END + 1)),
    ]  # fmt: skip
    for name in names:
        assert (site_dir / name).is_file(), name
    assert site_dir / "site.json" in written and site_dir / "layers.json" in written
    doc = json.loads((site_dir / "site.json").read_text(encoding="utf-8"))
    assert doc["assets"]["trend"] == {"sst": "trend_sst.png"}
    assert doc["assets"]["yearly"]["sst"] == "year_sst_{YYYY}.png"
    assert [v["id"] for v in doc["variables"]] == ["sst", "dhw", "chlorophyll"]
    assert fakes.calls["mur_year"] == END - START + 1
    assert fakes.calls["dhw_point_year"] == 5
    assert fakes.calls["chlorophyll_point"] == 1 and fakes.calls["gebco"] == 1 and fakes.calls["base"] == 1
    assert (tmp_path / "cache" / "chl_burdekin.csv").is_file()


def test_base_is_kept_unless_refreshed(tmp_path):
    fakes = Fakes()
    _build(tmp_path, fakes.fetchers())
    _build(tmp_path, fakes.fetchers())
    assert fakes.calls["base"] == 1
    build.build_reef(
        sites_dir=tmp_path / "sites", cache_dir=tmp_path / "cache", refresh_base=True, fetchers=fakes.fetchers()
    )
    assert fakes.calls["base"] == 2


def test_offline_second_run_makes_no_network_call(tmp_path):
    _build(tmp_path, Fakes().fetchers())
    path = tmp_path / "sites" / SITE_ID / "site.json"
    first = json.loads(path.read_text(encoding="utf-8"))
    _build(tmp_path, _raising(), offline=True)
    second = json.loads(path.read_text(encoding="utf-8"))
    first.pop("generated_at")
    second.pop("generated_at")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_offline_second_run_is_byte_identical(tmp_path):
    _build(tmp_path, Fakes().fetchers())
    path = tmp_path / "sites" / SITE_ID / "site.json"
    before = path.read_bytes()
    _build(tmp_path, _raising(), offline=True)
    assert path.read_bytes() == before  # same day: generated_at is the same date too


def test_offline_missing_cache_fails_loudly(tmp_path):
    with pytest.raises(FileNotFoundError, match="2003"):
        _build(tmp_path, _raising(), offline=True)
    assert not (tmp_path / "sites" / SITE_ID / "site.json").exists()


def test_offline_refresh_base_is_refused(tmp_path):
    with pytest.raises(ValueError, match="offline"):
        build.build_reef(sites_dir=tmp_path / "s", cache_dir=tmp_path / "c", offline=True, refresh_base=True)


def test_steps_are_logged(tmp_path, caplog):
    caplog.set_level("INFO", logger="app.reef.build")
    _build(tmp_path, Fakes().fetchers())
    steps = [r.getMessage() for r in caplog.records if r.getMessage().startswith("step ")]
    assert [s.split()[1] for s in steps] == [f"{i}/9" for i in range(1, 10)]
    assert all(s.rstrip().endswith(" s") for s in steps)
    assert any("cell" in r.getMessage() and "burdekin" in r.getMessage() for r in caplog.records)


def test_cli_parses_flags(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(build, "build_reef", lambda **kw: seen.update(kw) or [])
    assert build.main(["--offline", "--refresh-base", "--cache-dir", str(tmp_path)]) == 0
    assert seen == {"offline": True, "refresh_base": True, "cache_dir": tmp_path}
