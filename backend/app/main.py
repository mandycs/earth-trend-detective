"""Earth Trend Detective API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.catalog import load_catalog

app = FastAPI(title="Earth Trend Detective API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/variables")
def variables() -> list[dict]:
    return [
        {"id": v.id, "label": v.label, "role": v.role, "units": v.units, "dataset": v.dataset}
        for v in load_catalog()
    ]
