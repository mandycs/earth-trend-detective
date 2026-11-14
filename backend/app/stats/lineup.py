"""Suspect lineup: which human cause best matches the part of a change climate does not explain?

Input: the residual of one impact variable (residual.py, monthly or annual) and
annual series of candidate suspects (app/suspects.py). Every suspect goes
through the SAME protocol; nothing is tuned per suspect:

1. Annualize the residual: calendar-year mean, a year counts only with at least
   MIN_VALID_MONTHS valid months.
2. Compare YEAR-TO-YEAR CHANGES, never levels. Two series that both just trend
   (anything growing while water declines) correlate strongly in levels by
   construction; their changes do not, unless one actually tracks the other.
   Spearman rank correlation of residual change in year t vs suspect change in
   year t - lag, lag = 0..MAX_LAG. The lag with the largest |r| is reported,
   but EVERY lag counts as a test.
3. Benjamini-Hochberg across all suspects x lags of the site (fdr.py).
4. Out-of-sample check at the chosen lag: fit residual_change ~ suspect_change
   on years up to SPLIT_YEAR, predict the later years. Skill = share of error
   removed vs the "average change" baseline (the training mean change). The
   baseline is the mean, not zero, so a suspect gets no credit just for the
   residual having a trend.
5. Placebos: the same protocol on N_PLACEBOS fake lineups where each suspect's
   changes are phase-randomized (same spectrum and mean, so same smoothness
   and trend, but no real timing). The share of fake lineups that accuse
   someone is the false-alarm rate; above MAX_PLACEBO_ALARM the lineup is
   "inconclusive".

Verdicts: "prime suspect" = q < Q_THRESHOLD AND out-of-sample skill > 0 AND the
declared direction. "can't rule out" = right direction with q < Q_THRESHOLD or
raw p < LEAD_P but not all three, or not enough data to test. "cleared" = the
rest. Matching in time is a lead, not proof of cause.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd
from scipy import stats

from app.stats.fdr import benjamini_hochberg
from app.suspects import Suspect

logger = logging.getLogger(__name__)

MIN_VALID_MONTHS = 8
"""A calendar year of a monthly residual counts only with at least 8 valid months."""
MAX_LAG = 2
"""Suspect may lead the residual by 0, 1 or 2 years (e.g. irrigation expands, aquifer drops later)."""
MIN_PAIRS = 10
"""At least 10 pairs of year-to-year changes at a lag to test it at all."""
SPLIT_YEAR = 2015
"""Out-of-sample split: fit on changes up to this year, test on the later ones."""
MIN_TRAIN_PAIRS = 5
MIN_TEST_PAIRS = 3
"""Below these, the out-of-sample check is not done (skill unknown, cannot be prime)."""
Q_THRESHOLD = 0.05
"""q-value (after testing all suspects x lags) needed to be a prime suspect."""
LEAD_P = 0.05
"""Raw p below this, with the right direction, keeps a suspect at "can't rule out"."""
N_PLACEBOS = 200
PLACEBO_SEED = 0
MAX_PLACEBO_ALARM = 0.10
"""If more than 10% of fake lineups accuse someone, the real accusation is not trusted."""

CAVEAT = "Matching in time is a lead, not proof of cause."
PRIME, OPEN, CLEARED = "prime suspect", "can't rule out", "cleared"
SUSPECT_FOUND, NO_SUSPECT, INCONCLUSIVE = "suspect found", "no suspect", "inconclusive"


def _clean(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@dataclass(frozen=True)
class SuspectResult:
    id: str
    label: str
    n_years: int
    """Pairs of year-to-year changes at the chosen lag (0 if not testable)."""
    lag_years: int | None
    r: float | None
    p: float | None
    q: float | None
    oos_skill: float | None
    expected_sign_ok: bool | None
    verdict: str
    evidence: str
    skipped_reason: str | None

    def to_dict(self) -> dict:
        return {k: _clean(v) for k, v in asdict(self).items()}


@dataclass(frozen=True)
class LineupResult:
    suspects: tuple[SuspectResult, ...]
    n_suspects: int
    n_tests: int
    n_placebos: int
    placebo_false_alarm_rate: float | None
    status: str
    caveat: str

    def to_dict(self) -> dict:
        head = {k: _clean(v) for k, v in asdict(self).items() if k != "suspects"}
        return head | {"suspects": [s.to_dict() for s in self.suspects]}


def _years(index: pd.Index) -> np.ndarray:
    if isinstance(index, (pd.DatetimeIndex, pd.PeriodIndex)):
        return np.asarray(index.year, dtype=int)
    return np.asarray(index, dtype=int)


def annualize(series: pd.Series) -> pd.Series:
    """Calendar-year mean on an int year index.

    Monthly input (more than one row in some year): a year needs >= MIN_VALID_MONTHS
    valid months. Annual input (one row per year) passes through without NaN rows.
    """
    s = pd.Series(series.to_numpy(dtype=float), index=_years(series.index))
    if s.empty:
        return s
    rows_per_year = s.groupby(level=0).size()
    valid = s.dropna()
    if rows_per_year.max() <= 1:
        return valid.sort_index()
    grouped = valid.groupby(level=0)
    counts, means = grouped.size(), grouped.mean()
    return means[counts >= MIN_VALID_MONTHS].sort_index()


def year_changes(annual: pd.Series) -> pd.Series:
    """Change from year t-1 to t, indexed by t; only consecutive valid years."""
    if annual.empty:
        return annual.copy()
    years = annual.index.astype(int)
    full = annual.reindex(range(int(years.min()), int(years.max()) + 1))
    return full.diff().dropna()


def _pairs(res_d: pd.Series, sus_d: pd.Series, lag: int) -> pd.DataFrame:
    shifted = pd.Series(sus_d.to_numpy(), index=sus_d.index + lag)
    return pd.concat([res_d.rename("y"), shifted.rename("x")], axis=1).dropna()


def _correlate(pairs: pd.DataFrame) -> tuple[float, float] | None:
    if len(pairs) < MIN_PAIRS or pairs["x"].nunique() < 2 or pairs["y"].nunique() < 2:
        return None
    r, p = stats.spearmanr(pairs["x"], pairs["y"])
    return (float(r), float(p)) if math.isfinite(r) and math.isfinite(p) else None


def oos_skill(pairs: pd.DataFrame, split_year: int) -> float | None:
    """1 - MSE(model) / MSE(training mean change) on years after split_year."""
    train, test = pairs[pairs.index <= split_year], pairs[pairs.index > split_year]
    if len(train) < MIN_TRAIN_PAIRS or len(test) < MIN_TEST_PAIRS:
        return None
    x_mean, y_mean = float(train["x"].mean()), float(train["y"].mean())
    var_x = float(((train["x"] - x_mean) ** 2).sum())
    if var_x == 0.0:
        return None
    slope = float(((train["x"] - x_mean) * (train["y"] - y_mean)).sum()) / var_x
    predicted = y_mean + slope * (test["x"] - x_mean)
    mse_model = float(((test["y"] - predicted) ** 2).mean())
    mse_base = float(((test["y"] - y_mean) ** 2).mean())
    return None if mse_base == 0.0 else 1.0 - mse_model / mse_base


def _verdict(q: float, p: float, skill: float | None, sign_ok: bool) -> str:
    if q < Q_THRESHOLD and skill is not None and skill > 0 and sign_ok:
        return PRIME
    if sign_ok and (q < Q_THRESHOLD or p < LEAD_P):
        return OPEN
    return CLEARED


def _evaluate(
    res_d: pd.Series, sus_ds: Mapping[str, pd.Series], specs: Mapping[str, Suspect], split_year: int
) -> tuple[list[SuspectResult], int]:
    """Steps 2-4 for every suspect; evidence sentences are left empty."""
    tests: dict[str, dict[int, tuple[float, float, pd.DataFrame]]] = {}
    for sid, sus_d in sus_ds.items():
        per_lag = {}
        for lag in range(MAX_LAG + 1):
            pairs = _pairs(res_d, sus_d, lag)
            corr = _correlate(pairs)
            if corr is not None:
                per_lag[lag] = (*corr, pairs)
        tests[sid] = per_lag
    p_values = {f"{sid}|{lag}": v[1] for sid, per in tests.items() for lag, v in per.items()}
    q_values = benjamini_hochberg(p_values)

    results = []
    for sid, per_lag in tests.items():
        spec = specs[sid]
        if not per_lag:
            n_max = max(len(_pairs(res_d, sus_ds[sid], lag)) for lag in range(MAX_LAG + 1))
            reason = (
                f"Only {n_max} years of year-to-year change overlap with the residual "
                f"(need {MIN_PAIRS}), so {spec.label} could not be tested."
            )
            results.append(SuspectResult(sid, spec.label, n_max, None, None, None, None, None, None, OPEN, "", reason))
            continue
        lag = max(per_lag, key=lambda k: (abs(per_lag[k][0]), -k))
        r, p, pairs = per_lag[lag]
        q = q_values[f"{sid}|{lag}"]
        skill = oos_skill(pairs, split_year)
        sign_ok = bool(np.sign(r) == spec.expected_sign)
        verdict = _verdict(q, p, skill, sign_ok)
        results.append(SuspectResult(sid, spec.label, len(pairs), lag, r, p, q, skill, sign_ok, verdict, "", None))
    return results, len(p_values)


def _fmt_p(value: float) -> str:
    return "<0.001" if value < 0.001 else f"{value:.2g}"


def evidence(result: SuspectResult, split_year: int) -> str:
    """Plain-English sentence built only from the numbers in `result`."""
    if result.skipped_reason is not None:
        return result.skipped_reason
    timing = "in the same year" if result.lag_years == 0 else f"with a {result.lag_years}-year delay"
    first = (
        f"Year-to-year changes in {result.label} and in the unexplained part line up {timing}: "
        f"r = {result.r:.2f}, q = {_fmt_p(result.q)}, over {result.n_years} years."
    )
    if result.oos_skill is None:
        second = f"Too few years after {split_year} to check it on years it was not fitted on."
    elif result.oos_skill > 0:
        second = (
            f"Fitted on years up to {split_year}, it predicted the later years with "
            f"{result.oos_skill:.0%} less error than the average change alone."
        )
    else:
        second = (
            f"Fitted on years up to {split_year}, it predicted the later years no better than "
            f"the average change alone (skill {result.oos_skill:.2f})."
        )
    third = (
        "The direction matches what this cause would do."
        if result.expected_sign_ok
        else "The direction is the opposite of what this cause would do."
    )
    return f"{first} {second} {third}"


def _phase_randomize(changes: pd.Series, rng: np.random.Generator) -> pd.Series:
    """Same Fourier amplitudes and mean, random phases. Gaps are closed up first
    (the valid changes are treated as contiguous), then the original years are kept."""
    values = changes.to_numpy(dtype=float)
    n = len(values)
    if n < 3:
        return changes.copy()
    spectrum = np.fft.rfft(values)
    phases = rng.uniform(0.0, 2.0 * np.pi, len(spectrum))
    phases[0] = 0.0
    if n % 2 == 0:
        phases[-1] = 0.0
    surrogate = np.fft.irfft(spectrum * np.exp(1j * phases), n)
    return pd.Series(surrogate, index=changes.index)


def _placebo_rate(
    res_d: pd.Series, sus_ds: Mapping[str, pd.Series], specs: Mapping[str, Suspect],
    split_year: int, n_placebos: int, seed: int,
) -> float:
    rng = np.random.default_rng(seed)
    alarms = 0
    for _ in range(n_placebos):
        fake = {sid: _phase_randomize(d, rng) for sid, d in sus_ds.items()}
        results, _ = _evaluate(res_d, fake, specs, split_year)
        alarms += any(r.verdict == PRIME for r in results)
    return alarms / n_placebos


def run_lineup(
    residual: pd.Series,
    suspects: Mapping[str, pd.Series],
    specs: Mapping[str, Suspect],
    *,
    split_year: int = SPLIT_YEAR,
    n_placebos: int = N_PLACEBOS,
    seed: int = PLACEBO_SEED,
) -> LineupResult:
    """Run the protocol (module docstring) for one impact variable's residual.

    residual: monthly (DatetimeIndex) or annual (int years / DatetimeIndex) values.
    suspects: {suspect_id: annual series}; gaps and different spans are fine.
    specs: {suspect_id: Suspect}; every suspect id must be present (KeyError otherwise).
    Inputs are not modified.
    """
    missing = [sid for sid in suspects if sid not in specs]
    if missing:
        raise KeyError(f"no Suspect spec for {missing}")
    res_d = year_changes(annualize(residual))
    sus_ds = {sid: year_changes(annualize(s)) for sid, s in suspects.items()}

    raw, n_tests = _evaluate(res_d, sus_ds, specs, split_year)
    results = tuple(replace(r, evidence=evidence(r, split_year)) for r in raw)

    if n_tests == 0:
        rate, status = None, INCONCLUSIVE
    else:
        rate = _placebo_rate(res_d, sus_ds, specs, split_year, n_placebos, seed) if n_placebos > 0 else None
        if rate is not None and rate > MAX_PLACEBO_ALARM:
            status = INCONCLUSIVE
        elif any(r.verdict == PRIME for r in results):
            status = SUSPECT_FOUND
        else:
            status = NO_SUSPECT
    logger.info(
        "lineup: %d suspects, %d tests, placebo rate %s, status %s, verdicts %s",
        len(results), n_tests, rate, status, {r.id: r.verdict for r in results},
    )
    return LineupResult(results, len(results), n_tests, n_placebos, rate, status, CAVEAT)
