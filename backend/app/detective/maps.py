"""Per-pixel map overlays written by the detective (`trend_map`) and the route that serves them.

- Files live in `MAPS_DIR` (`data/detective/maps/`), named `<uuid4 hex>.png`: 32 hex
  characters, so a name cannot be guessed and nothing else on disk can be reached.
- Each file is written atomically (a temporary name, then `os.replace`).
- Files older than `MAX_AGE_DAYS` are removed when the API starts (`cleanup_old`).
- `GET /detective/maps/{name}.png` serves only names matching `^[0-9a-f]{32}\\.png$`.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_MAPS_DIR = Path(__file__).resolve().parents[2] / "data" / "detective" / "maps"
MAPS_DIR: Path = DEFAULT_MAPS_DIR  # patched in tests
MAX_AGE_DAYS = 7
URL_PREFIX = "/detective/maps/"
NAME_RE = re.compile(r"^[0-9a-f]{32}\.png$")

router = APIRouter()


def maps_dir() -> Path:
    return MAPS_DIR


def new_name() -> str:
    return f"{uuid.uuid4().hex}.png"


def url_for(name: str) -> str:
    return f"{URL_PREFIX}{name}"


def write_png(rgba: np.ndarray, size: tuple[int, int], name: str | None = None) -> str:
    """Write the RGBA grid (resized to `size`, nearest: no smoothing) under `name` (default: a new
    one); returns the name."""
    folder = maps_dir()
    folder.mkdir(parents=True, exist_ok=True)
    name = new_name() if name is None else name
    if not NAME_RE.fullmatch(name):
        raise ValueError("bad map name")
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".png")
    try:
        with os.fdopen(fd, "wb") as fh:
            Image.fromarray(rgba, "RGBA").resize(size, Image.Resampling.NEAREST).save(fh, format="PNG", optimize=True)
        os.replace(tmp, folder / name)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return name


def cleanup_old(max_age_days: float = MAX_AGE_DAYS, now: float | None = None) -> int:
    """Remove map files (and stray temporary files) older than `max_age_days`; returns how many."""
    folder = maps_dir()
    if not folder.is_dir():
        return 0
    limit = (time.time() if now is None else now) - max_age_days * 86400
    removed = 0
    for path in folder.iterdir():
        if not (NAME_RE.fullmatch(path.name) or path.name.startswith(".tmp-")):
            continue
        try:
            if path.is_file() and path.stat().st_mtime < limit:
                path.unlink()
                removed += 1
        except OSError as exc:
            logger.warning("detective maps: could not remove %s: %s", path.name, exc)
    return removed


@router.get("/detective/maps/{name}")
def get_map(name: str) -> FileResponse:
    if not NAME_RE.fullmatch(name):
        raise HTTPException(status_code=404, detail="no such map")
    path = maps_dir() / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no such map")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
