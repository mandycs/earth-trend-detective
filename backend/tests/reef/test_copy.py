"""The reef story prose holds no figures and none of the forbidden words."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.reef.export import REEF_CAVEATS

COPY = Path(__file__).resolve().parents[3] / "sites" / "great_barrier_reef" / "copy.json"
FORBIDDEN = re.compile(r"\b(proof|proves?|proven|cause[sd]?|bleached)\b", re.I)


def test_reef_copy_has_no_figures_or_forbidden_words():
    text = COPY.read_text(encoding="utf-8")
    copy = json.loads(text)
    prose = [s["body"] for s in copy["steps"]] + [copy["narrative"], *copy["caveats"]]
    assert len(copy["steps"]) == 3
    for line in prose:
        assert not re.search(r"\d", line), line
    assert not FORBIDDEN.search(text)
    for caveat in REEF_CAVEATS:
        assert not FORBIDDEN.search(caveat), caveat
