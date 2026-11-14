"""Traffic light shown to the user. Values match `sites/*/site.json`."""

from __future__ import annotations

import math
from enum import StrEnum

REAL_Q = 0.05
"""`real`: after correcting for testing many variables at once (FDR q-value),
there is less than a 5% expected chance that this is a false alarm."""

LIKELY_P = 0.10
"""`likely`: on its own the trend would happen by chance less than 1 time in 10
(raw p-value), but it does not survive the many-variables correction. A hint,
not a finding."""


class Verdict(StrEnum):
    REAL = "real"
    LIKELY = "likely"
    UNKNOWN = "unknown"  # "Can't tell yet": too noisy, too short, or no trend


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


def classify(q_value: float, p_value: float, slope: float) -> tuple[Verdict, Direction]:
    """Verdict from q/p; direction from the Sen slope sign (flat when unknown)."""
    if q_value is not None and not math.isnan(q_value) and q_value < REAL_Q:
        verdict = Verdict.REAL
    elif p_value is not None and not math.isnan(p_value) and p_value < LIKELY_P:
        verdict = Verdict.LIKELY
    else:
        return Verdict.UNKNOWN, Direction.FLAT
    if slope > 0:
        return verdict, Direction.UP
    if slope < 0:
        return verdict, Direction.DOWN
    return verdict, Direction.FLAT
