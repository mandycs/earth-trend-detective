"""Registry of human "suspects" for the lineup (stats/lineup.py).

A suspect is an annual series of a possible human cause of a change that
climate does not explain (urban area, night lights, irrigated area, river
water use, ...). This module only fixes the SHAPE of a registry entry; the data
extractors that produce each suspect's annual series come later.

expected_sign is the sign of the relationship we would see if this suspect were
the cause, measured as corr(suspect year-to-year change, residual year-to-year
change). Declared BEFORE looking at the data, so the lineup cannot pick the
sign that happens to fit:
  +1  more of the suspect -> residual goes up   (e.g. a dam filling a lake)
  -1  more of the suspect -> residual goes down (e.g. more irrigation -> less water)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Suspect:
    id: str
    label: str
    """Plain-English name used in evidence sentences, e.g. "irrigated area"."""
    source: str
    """Who publishes the data, e.g. "USBR Consumptive Uses and Losses"."""
    url: str
    expected_sign: int
    """+1 or -1, see module docstring."""
    applies_to: tuple[str, ...]
    """Tags matched against impact variable ids or site tags, e.g. ("grace_tws", "arid")."""
    unit: str
    is_nasa: bool
    validation_only: bool = False
    """True for ground-truth series used to check the method, not to accuse."""

    def __post_init__(self) -> None:
        if self.expected_sign not in (-1, 1):
            raise ValueError(f"{self.id}: expected_sign must be +1 or -1, got {self.expected_sign}")
        if not self.id:
            raise ValueError("suspect id must not be empty")


SUSPECTS: tuple[Suspect, ...] = (
    # Filled in once the extractors exist. Example of the intended shape:
    # Suspect(
    #     id="irrigated_area",
    #     label="irrigated area",
    #     source="<dataset name>",
    #     url="<landing page>",
    #     expected_sign=-1,  # more irrigation -> less stored water
    #     applies_to=("grace_tws", "soil_moisture"),
    #     unit="km²",
    #     is_nasa=False,
    # ),
)


def registry_by_id(suspects: Iterable[Suspect] = SUSPECTS) -> dict[str, Suspect]:
    """id -> Suspect; duplicate ids are a configuration error."""
    out: dict[str, Suspect] = {}
    for suspect in suspects:
        if suspect.id in out:
            raise ValueError(f"duplicate suspect id {suspect.id}")
        out[suspect.id] = suspect
    return out
