"""Approximate data-cell size of each coarse source, in km (one value covers the whole cell).

Shared by the map footprint (`tools/mapping.show_footprint`) and the report (`report.data_cells`).
"""

from __future__ import annotations

CELL_KM = {"grace": 300.0, "power": 50.0, "gldas": 25.0}
