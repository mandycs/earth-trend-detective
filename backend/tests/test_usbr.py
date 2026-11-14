from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.validation.usbr import FEET_TO_M, fetch_mead_elevation, parse_elevation_table

FIXTURE = Path(__file__).parent / "fixtures" / "usbr_mead_snippet.html"


def test_parse_converts_feet_to_metres_and_indexes_months():
    s = parse_elevation_table(FIXTURE.read_text())
    assert s.loc["2003-01-01"] == pytest.approx(1153.33 * FEET_TO_M)
    assert s.loc["2004-12-01"] == pytest.approx(1130.01 * FEET_TO_M)
    assert s.index.is_monotonic_increasing


def test_empty_cells_become_nan():
    s = parse_elevation_table(FIXTURE.read_text())
    assert s.loc["2026-02-01"] == pytest.approx(1060.00 * FEET_TO_M)
    assert np.isnan(s.loc["2026-03-01"])


def test_parse_rejects_page_without_table():
    with pytest.raises(ValueError):
        parse_elevation_table("<html>maintenance</html>")


def test_fetch_uses_cache_and_trims(tmp_path):
    cache = tmp_path / "mead.html"
    cache.write_text(FIXTURE.read_text())
    s = fetch_mead_elevation(2003, 2004, cache_path=cache)
    assert len(s) == 24
    assert s.index[0] == pd.Timestamp("2003-01-01")
    assert s.notna().all()
