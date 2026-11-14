"""Statistics engine: deseasonalize -> Mann-Kendall (Hamed-Rao) + Sen -> FDR -> verdict -> residual."""

from app.stats.residual import ResidualResult, compute_residuals
from app.stats.sweep import VariableResult, run_sweep

__all__ = ["ResidualResult", "VariableResult", "compute_residuals", "run_sweep"]
