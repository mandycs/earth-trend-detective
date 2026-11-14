"""False discovery rate across one sweep.

Testing many variables at once means some will look "significant" by luck.
Benjamini-Hochberg turns each p-value into a q-value: the expected share of
false alarms among everything at least that significant.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
from statsmodels.stats.multitest import multipletests


def benjamini_hochberg(p_values: Mapping[str, float]) -> dict[str, float]:
    """q-value per key; NaN p-values are left out of the correction and stay NaN."""
    testable = {k: p for k, p in p_values.items() if p is not None and not math.isnan(p)}
    q_values = {k: float("nan") for k in p_values}
    if not testable:
        return q_values
    keys = list(testable)
    _, corrected, _, _ = multipletests(np.array([testable[k] for k in keys]), method="fdr_bh")
    return {**q_values, **{k: float(q) for k, q in zip(keys, corrected, strict=True)}}
