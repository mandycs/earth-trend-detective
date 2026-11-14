"""Variable catalog: which NASA variables the sweep analyzes and how to read them."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalog" / "variables.yaml"

ROLES = frozenset({"driver", "impact"})
SOURCES = frozenset({"power", "appeears", "datarods", "grace"})


@dataclass(frozen=True)
class Variable:
    id: str
    label: str
    role: str
    source: str
    dataset: str
    band: str
    units: str
    scale: float
    offset: float
    temporal: str
    tags: tuple[str, ...]
    applies_to: tuple[str, ...]
    drivers: tuple[str, ...]


def _parse_variable(raw: dict) -> Variable:
    if raw["role"] not in ROLES:
        raise ValueError(f"variable {raw['id']!r}: invalid role {raw['role']!r}")
    if raw["source"] not in SOURCES:
        raise ValueError(f"variable {raw['id']!r}: invalid source {raw['source']!r}")
    return Variable(
        id=str(raw["id"]),
        label=str(raw["label"]),
        role=raw["role"],
        source=raw["source"],
        dataset=str(raw["dataset"]),
        band=str(raw["band"]),
        units=str(raw["units"]),
        scale=float(raw["scale"]),
        offset=float(raw["offset"]),
        temporal=str(raw["temporal"]),
        tags=tuple(raw.get("tags") or ()),
        applies_to=tuple(raw.get("applies_to") or ()),
        drivers=tuple(raw.get("drivers") or ()),
    )


def load_catalog(path: Path = CATALOG_PATH) -> tuple[Variable, ...]:
    """Load and validate the variable catalog."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    variables = tuple(_parse_variable(raw) for raw in data["variables"])
    ids = [v.id for v in variables]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate variable ids in catalog")
    driver_ids = {v.id for v in variables if v.role == "driver"}
    for v in variables:
        unknown = set(v.drivers) - driver_ids
        if unknown:
            raise ValueError(f"variable {v.id!r}: unknown drivers {sorted(unknown)}")
    return variables


def variables_for_site(catalog: Sequence[Variable], site_tags: Iterable[str]) -> tuple[Variable, ...]:
    """Variables whose `applies_to` matches the site tags ("any" matches every site)."""
    tags = set(site_tags)
    return tuple(v for v in catalog if "any" in v.applies_to or tags & set(v.applies_to))
