"""Statistics engine: deseasonalize -> Mann-Kendall (Hamed-Rao) + Sen -> FDR -> verdict."""

from app.stats.sweep import VariableResult, run_sweep

__all__ = ["VariableResult", "run_sweep"]
