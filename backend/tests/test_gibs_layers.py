"""GIBS colour -> value decoding (no network)."""

import numpy as np

from app.assets.gibs_layers import colorize, decode, encode_values, parse_colormap, season_mean

XML = """
<ColorMap>
  <ColorMapEntry rgb="0,26,105" transparent="true" sourceValue="[-3000,-2000)" value="[-0.3,-0.2)" nodata="true" ref="0"/>
  <ColorMapEntry rgb="10,20,30" transparent="false" sourceValue="[100,200)" value="[0.01,0.02)" ref="1"/>
  <ColorMapEntry rgb="40,50,60" transparent="false" sourceValue="[200,300)" value="[0.02,0.03)" ref="2"/>
</ColorMap>
"""


def test_parse_colormap_skips_nodata_and_uses_midpoints():
    table = parse_colormap(XML)
    assert set(table) == {(10, 20, 30), (40, 50, 60)}
    assert abs(table[(10, 20, 30)] - 0.015) < 1e-12


def test_decode_unknown_and_transparent_are_nan():
    rgba = np.array([[[10, 20, 30, 255], [40, 50, 60, 0], [1, 2, 3, 255]]], dtype=np.uint8)
    vals = decode(rgba, parse_colormap(XML))
    assert abs(vals[0, 0] - 0.015) < 1e-12
    assert np.isnan(vals[0, 1]) and np.isnan(vals[0, 2])


def test_season_mean_ignores_gaps():
    a = np.array([[1.0, np.nan]])
    b = np.array([[3.0, 4.0]])
    assert season_mean([a, b]).tolist() == [[2.0, 4.0]]


def test_value_encoding_round_trips_and_keeps_zero_for_nodata():
    vals = np.array([[0.5, np.nan, -0.2]])
    code = encode_values(vals, -1.0, 0.0001)
    assert code[0, 1] == 0
    back = -1.0 + 0.0001 * code[0, [0, 2]].astype(float)
    assert np.allclose(back, [0.5, -0.2])


def test_colorize_is_transparent_where_no_data():
    rgba = colorize(np.array([[0.0, np.nan]]), 0.0, 1.0, "YlGn")
    assert rgba[0, 0, 3] > 0 and rgba[0, 1, 3] == 0
