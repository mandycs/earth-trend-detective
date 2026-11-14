import math

import httpx
import numpy as np
import pandas as pd
import pytest
import respx

from app.catalog import Variable, load_catalog
from app.extractors import gldas

CSV = """Dataset: GLDAS_NOAH025_M.A200301.021.nc4
/lon, -114.75, -114.5, -114.25
/lat, 35.95, 36.2, 36.45
/Qs_acc[0][0], 1e-06, 2e-06, 3e-06
/Qs_acc[0][1], 4e-06, 0.01, 6e-06
/Qs_acc[0][2], 7e-06, 8e-06, 9e-06
/SoilMoi0_10cm_inst[0][0], 10, 11, 12
/SoilMoi0_10cm_inst[0][1], 13, -9999, 15
/SoilMoi0_10cm_inst[0][2], 16, 17, 18
"""


def make_var(var_id: str, band: str, scale: float = 1.0) -> Variable:
    return Variable(
        id=var_id, label=var_id, role="impact", source="gldas", dataset="GLDAS_NOAH025_M.2.1",
        band=band, units="u", scale=scale, offset=0.0, temporal="monthly",
        tags=(), applies_to=("any",), drivers=(),
    )


def cmr_payload(months: list[str]) -> dict:
    return {
        "feed": {
            "entry": [
                {
                    "title": f"GLDAS_NOAH025_M.2.1:GLDAS_NOAH025_M.A{m.replace('-', '')}.021.nc4",
                    "time_start": f"{m}-01T00:00:00.000Z",
                }
                for m in months
            ]
        }
    }


def test_grid_index_nearest_cell_and_bounds():
    assert gldas.grid_index(36.2, -114.5) == (384, 262)
    assert gldas.grid_index(-59.875, -179.875) == (0, 0)
    with pytest.raises(ValueError):
        gldas.grid_index(-70.0, 0.0)


def test_window_is_clipped_at_grid_edges():
    rows, cols = gldas.window(0, 1439)
    assert (rows.start, rows.stop) == (0, 2)
    assert (cols.start, cols.stop) == (1438, 1440)


def test_subset_url_percent_encodes_brackets():
    ce = gldas.constraint_expression(["Qs_acc", "SoilMoi0_10cm_inst"], slice(383, 386), slice(261, 264))
    assert ce.startswith("/Qs_acc[0][383:385][261:263];/SoilMoi0_10cm_inst[0][383:385]")
    url = gldas.subset_url("GLDAS_NOAH025_M.2.1:GLDAS_NOAH025_M.A200301.021.nc4", ce)
    assert "[" not in url and "]" not in url and ";" not in url.split("?")[1]
    assert "GLDAS_NOAH025_M.2.1%3AGLDAS" in url
    assert url.split("?")[0].endswith(".nc4.dap.csv")


def test_parse_dap_csv_builds_grids_and_masks_fill():
    parsed = gldas.parse_dap_csv(CSV)
    assert parsed["SoilMoi0_10cm_inst"].shape == (3, 3)
    assert math.isnan(parsed["SoilMoi0_10cm_inst"][1, 1])
    assert parsed["Qs_acc"][1, 1] == pytest.approx(0.01)
    np.testing.assert_allclose(parsed["lat"], [[35.95, 36.2, 36.45]])


def test_cell_value_falls_back_to_window_mean_when_centre_masked():
    parsed = gldas.parse_dap_csv(CSV)
    assert gldas.cell_value(parsed["Qs_acc"], (1, 1)) == pytest.approx(0.01)
    assert gldas.cell_value(parsed["SoilMoi0_10cm_inst"], (1, 1)) == pytest.approx(14.0)
    assert math.isnan(gldas.cell_value(np.full((3, 3), np.nan), (1, 1)))


@respx.mock
def test_list_granules_paginates_and_dedupes():
    route = respx.get(gldas.CMR_GRANULES_URL).mock(
        side_effect=[
            httpx.Response(200, json=cmr_payload(["2003-01", "2003-02"])),
            httpx.Response(200, json=cmr_payload(["2003-02"])),
        ]
    )
    with httpx.Client() as client:
        granules = gldas.list_granules(2003, 2003, client, page_size=2)
    assert route.call_count == 2
    assert [g.month for g in granules] == [pd.Timestamp("2003-01-01"), pd.Timestamp("2003-02-01")]


@respx.mock
def test_fetch_monthly_scales_reindexes_and_caches(tmp_path):
    respx.get(gldas.CMR_GRANULES_URL).mock(
        return_value=httpx.Response(200, json=cmr_payload(["2003-01", "2003-03"]))
    )
    dap = respx.get(url__startswith=gldas.OPENDAP_BASE).mock(return_value=httpx.Response(200, text=CSV))
    variables = [make_var("soil_moisture", "SoilMoi0_10cm_inst"), make_var("runoff", "Qs_acc", 8.0)]

    with httpx.Client() as client:
        first = gldas.fetch_monthly(36.2, -114.5, variables, 2003, 2003, tmp_path, client, max_workers=2)
        second = gldas.fetch_monthly(36.2, -114.5, variables, 2003, 2003, tmp_path, client, max_workers=2)

    assert dap.call_count == 2  # one per granule; second run served from cache
    assert len(list((tmp_path / "cell_384_262").glob("*.csv"))) == 2
    runoff = first["runoff"]
    assert isinstance(runoff.index, pd.DatetimeIndex) and len(runoff) == 12
    assert runoff.index.freqstr == "MS"
    assert runoff.loc["2003-01-01"] == pytest.approx(0.08)
    assert math.isnan(runoff.loc["2003-02-01"])  # granule missing in CMR -> NaN
    assert first["soil_moisture"].loc["2003-03-01"] == pytest.approx(14.0)
    pd.testing.assert_series_equal(first["runoff"], second["runoff"])


@respx.mock
def test_server_errors_are_retried_then_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(gldas.time, "sleep", lambda _s: None)
    route = respx.get(url__startswith=gldas.OPENDAP_BASE).mock(return_value=httpx.Response(503))
    granule = gldas.Granule(month=pd.Timestamp("2003-01-01"), ur="G:x.nc4")
    with httpx.Client() as client, pytest.raises(RuntimeError):
        gldas._fetch_granule(granule, "/Qs_acc[0][0:0][0:0]", tmp_path / "x.csv", client)
    assert route.call_count == gldas.RETRIES
    assert not (tmp_path / "x.csv").exists()


def test_catalog_gldas_entries_use_monthly_product():
    variables = {v.id: v for v in gldas.gldas_variables(load_catalog())}
    assert set(variables) == {"soil_moisture", "runoff"}
    assert all(v.dataset == "GLDAS_NOAH025_M.2.1" and v.temporal == "monthly" for v in variables.values())
    assert variables["runoff"].scale == 8.0


def test_load_site_points_swaps_lon_lat():
    points = dict((s, (lat, lon)) for s, lat, lon in gldas.load_site_points())
    assert points["lake_mead"] == (36.2, -114.5)
