"""Analysis tools of the detective: test the suspects.

- `climate_residual`: how much of a change the climate we measured does not explain.
- `correlate`: do two series move together from year to year (and with a lag)?
- `compare`: does one variable trend differently in two places or two periods?
- `years_needed_for`: how many more years until a trend would be clear (no test).

Every counted test goes into the session ledger, so the Benjamini-Hochberg correction
covers everything the agent tried. Verdicts and q values are read from
`ledger.corrected()` at return time (also for cached results), and every result that
logged tests lists their `test_ids` so later code can refresh them again.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pandas as pd
from scipy import stats

from app import gather
from app.detective.ledger import Ledger, TestRecord
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import data
from app.investigate.landcover import box_around
from app.site_report import residual_withheld_reason
from app.stats.annual import annual_trend, annual_years_needed
from app.stats.deseason import monthly_anomalies
from app.stats.lineup import MIN_PAIRS, _pairs, annualize, year_changes
from app.stats.residual import CANDIDATE_MODELS, residual_for
from app.stats.trend import trend_test as mk_trend_test
from app.stats.years import years_needed

logger = logging.getLogger(__name__)

WORDING = "not explained by the climate we measured — a clue, not proof"
CORRELATION_NOTE = "Moving together is a clue, not proof that one drives the other."
PCT_NOTE = "The total change is not clear enough to split, so no share is given."
ANNUAL_RESIDUAL_REASON = "one value per year; the climate split needs monthly values (use trend_test)"
MAX_LAG = 5

_num = data._num
_not_available = data._not_available


def refresh_verdicts(session: Session, value: Any, corrected: Mapping | None = None) -> Any:
    """Copy of `value` with q_session / verdict / direction re-read from the ledger now."""
    corrected = session.ledger.corrected() if corrected is None else corrected
    if isinstance(value, list):
        return [refresh_verdicts(session, v, corrected) for v in value]
    if not isinstance(value, Mapping):
        return value
    out = {k: refresh_verdicts(session, v, corrected) for k, v in value.items()}
    tid = out.get("test_id")
    if isinstance(tid, str) and tid in corrected:
        q, verdict, direction = corrected[tid]
        out |= {"q_session": _num(q), "verdict": str(verdict), "direction": str(direction)}
    return out


def _cached_or_run(session: Session, tool: str, args: Mapping, compute) -> dict:
    return refresh_verdicts(session, data._through_ledger(session, tool, args, compute))


def _log(session: Session, record: TestRecord) -> str:
    """Add `record` under the next test id and return that id."""
    test_id = f"t{session.ledger.n_tests + 1}"
    session.ledger.add_test(replace(record, id=test_id))
    return test_id


# --------------------------------------------------------------------------- climate_residual


def climate_residual(session: Session, var_id: str) -> dict:
    """One residual per target per thread: the key is the target alone."""
    return _cached_or_run(session, "climate_residual", {"var_id": var_id}, lambda: _residual(session, var_id))


def _fetched(session: Session, var_id: str) -> tuple[pd.Series | None, bool]:
    """(series or None, whether the failure was a passing one that a retry may fix)."""
    got = data.get_series(session, var_id=var_id)
    if got.get("status") != "ok":
        return None, bool(got.get("transient"))
    return session.series[got["series_id"]], False


def _extra_driver_ids(session: Session, var_id: str) -> list[str]:
    """Opt-in drivers of this place that a candidate model of `var_id` would use."""
    offered = {
        d for spec in CANDIDATE_MODELS[1:] if spec.impacts is None or var_id in spec.impacts for d in spec.extra_drivers
    }
    site_extra = gather.site_extra_drivers(session.place.as_site(), session.catalog)
    return [v.id for v in site_extra if v.id in offered]


def _residual(session: Session, var_id: str) -> dict:
    var = data._variable(session, var_id)
    if var is None:
        return _not_available(f"unknown variable {var_id!r}; call list_variables", var_id=var_id, wording=WORDING)
    if var.temporal == "annual":
        return _not_available(ANNUAL_RESIDUAL_REASON, var_id=var_id, wording=WORDING)
    if var.role != "impact" or not var.drivers:
        return _not_available(
            f"{var.label} is a climate driver, not an impact; there is nothing to split", var_id=var_id, wording=WORDING
        )
    drivers = list(var.drivers)
    withheld = residual_withheld_reason(var.source, session.place.tags)
    if withheld is not None:
        # No figure and no test: a split we would not show must not count as evidence.
        return {"var_id": var_id, "label": var.label, "drivers": drivers, "withheld": withheld, "wording": WORDING}

    impact, transient = _fetched(session, var_id)
    if impact is None:
        return _not_available(f"no data for {var.label} here", transient, var_id=var_id, wording=WORDING)
    fetched = {d: _fetched(session, d) for d in drivers}
    missing = [d for d, (series, _) in fetched.items() if series is None]
    if missing:
        return _not_available(
            f"climate driver(s) {', '.join(missing)} not available here, so the split would count "
            "their effect as not explained",
            any(t for _, t in fetched.values()),
            var_id=var_id,
            wording=WORDING,
        )
    driver_series = {d: series for d, (series, _) in fetched.items()}
    try:
        for d in _extra_driver_ids(session, var_id):
            series, _ = _fetched(session, d)
            if series is not None:
                driver_series[d] = series
        driver_anoms = {d: monthly_anomalies(s) for d, s in driver_series.items()}
        res = residual_for(var, impact, driver_anoms)
    except Exception as exc:  # noqa: BLE001 - never a stack trace to the model
        logger.warning("climate_residual %s failed: %s: %s", var_id, type(exc).__name__, exc)
        return _not_available("the climate split could not run here", True, var_id=var_id, wording=WORDING)
    p = res.residual_p_value
    slope = res.residual_slope_per_decade
    test_id = _log(
        session,
        TestRecord(
            id="",
            var_id=var_id,
            label=f"{var.label}: part not explained by climate",
            kind="residual",
            p_value=float("nan") if p is None else p,
            slope=slope,
            too_short=slope is None,
            result=None,
        ),
    )
    out = {
        "var_id": var_id,
        "label": var.label,
        "test_id": test_id,
        "test_ids": [test_id],
        "pct_not_explained": None if res.pct_non_climate is None else round(res.pct_non_climate, 1),
        "pct_range": None if res.pct_range is None else [round(x, 1) for x in res.pct_range],
        "drivers": list(res.drivers_used),
        "model": res.model_label,
        "r2": _num(res.r2, 3),
        "n_months": res.n_months,
        "unit": f"{var.units} per decade",
        "total_slope_per_decade": _num(res.total_slope_per_decade),
        "climate_slope_per_decade": _num(res.climate_slope_per_decade),
        "residual_slope_per_decade": _num(slope),
        "p_value": _num(p),
        "n_tests_so_far": session.ledger.n_finite(),
        "caveat": res.caveat,
        "wording": WORDING,
    }
    if out["pct_not_explained"] is None:
        out["pct_note"] = PCT_NOTE
    return out


# --------------------------------------------------------------------------- correlate


def correlate(session: Session, series_a: str, series_b: str, max_lag: int = 2) -> dict:
    max_lag = max(0, min(int(max_lag), MAX_LAG))
    args = {"series_a": series_a, "series_b": series_b, "max_lag": max_lag}
    return _cached_or_run(session, "correlate", args, lambda: _correlate(session, series_a, series_b, max_lag))


def _label(session: Session, series_id: str, series: pd.Series) -> tuple[str, str]:
    var_id = str(series.name or series_id.split(":")[0])
    var = data._variable(session, var_id)
    return var_id, var.label if var else var_id


def _pearson(a: pd.Series, b: pd.Series, lag: int) -> tuple[float, float, int]:
    """Pearson r, p of a(t) against b(t - lag); NaN when too few pairs."""
    pairs = _pairs(a, b, lag)  # same lag convention as the lineup: y = a(t), x = b(t - lag)
    n = len(pairs)
    if n < MIN_PAIRS or pairs["x"].nunique() < 2 or pairs["y"].nunique() < 2:
        return math.nan, math.nan, n
    r, p = stats.pearsonr(pairs["y"], pairs["x"])
    return float(r), float(p), n


def _correlate(session: Session, series_a: str, series_b: str, max_lag: int) -> dict:
    sa, sb = session.series.get(series_a), session.series.get(series_b)
    for sid, s in ((series_a, sa), (series_b, sb)):
        if s is None:
            return _not_available(f"unknown series_id {sid!r}; call get_series first")
    var_a, label_a = _label(session, series_a, sa)
    var_b, label_b = _label(session, series_b, sb)
    da, db = year_changes(annualize(sa)), year_changes(annualize(sb))
    lags = []
    for lag in range(max_lag + 1):
        r, p, n = _pearson(da, db, lag)
        too_short = not math.isfinite(r)
        test_id = _log(
            session,
            TestRecord(
                id="",
                var_id=f"{var_a}~{var_b}",
                label=f"{label_a} vs {label_b}" + (f" ({lag} yr earlier)" if lag else ""),
                kind="correlate",
                p_value=p,
                slope=None if too_short else r,
                too_short=too_short,
                result=None,
            ),
        )
        lags.append({"lag": lag, "test_id": test_id, "r": _num(r, 3), "p": _num(p), "n_years": n, "too_short": too_short})
    return {
        "series_a": series_a,
        "series_b": series_b,
        "method": "Pearson r of year-on-year changes; lag k pairs a in year t with b in year t-k",
        "lags": lags,
        "test_ids": [row["test_id"] for row in lags],
        "n_tests_so_far": session.ledger.n_finite(),
        "note": CORRELATION_NOTE,
    }


# --------------------------------------------------------------------------- compare


class _Capture(Ledger):
    """Scratch ledger that keeps the last test record so it can be re-logged as `compare`."""

    last: TestRecord | None = None

    def add_test(self, record: TestRecord) -> None:
        super().add_test(record)
        self.last = record


def _side(raw: Any) -> dict | None:
    side = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw or {})
    out = {k: side.get(k) for k in ("lat", "lon", "start", "end")}
    has_point = out["lat"] is not None and out["lon"] is not None
    has_period = out["start"] is not None or out["end"] is not None
    if (out["lat"] is None) != (out["lon"] is None) or not (has_point or has_period):
        return None
    if has_point and not (-90 <= float(out["lat"]) <= 90 and -180 <= float(out["lon"]) <= 180):
        return None
    return out


def compare(session: Session, var_id: str, a: Any, b: Any) -> dict:
    side_a, side_b = _side(a), _side(b)
    if side_a is None or side_b is None:
        return _not_available("each side needs a place {lat, lon} or a period {start, end}")
    args = {"var_id": var_id, "a": side_a, "b": side_b}
    return _cached_or_run(session, "compare", args, lambda: _compare(session, var_id, side_a, side_b))


def _side_trend(session: Session, var_id: str, side: dict) -> dict:
    """The trend of one side through the same get_series / trend_test path, on a scratch ledger."""
    start = session.start if side["start"] is None else int(side["start"])
    end = session.end if side["end"] is None else int(side["end"])
    here = side["lat"] is None or (float(side["lat"]) == session.place.lat and float(side["lon"]) == session.place.lon)
    if here:
        place = session.place
        fetched = data.get_series(session, var_id=var_id, start=start, end=end)
    else:
        lat, lon = float(side["lat"]), float(side["lon"])
        place = Place(lat=lat, lon=lon, bbox=box_around(lat, lon), tags=session.place.tags)
    scratch = Session(ledger=_Capture(), place=place, catalog=session.catalog, start=start, end=end)
    if here:
        if fetched.get("status") != "ok":
            return fetched
        scratch.series[fetched["series_id"]] = session.series[fetched["series_id"]]
    else:
        fetched = data.get_series(scratch, var_id=var_id, start=start, end=end)
        if fetched.get("status") != "ok":
            return fetched
    trend = data.trend_test(scratch, series_id=fetched["series_id"])
    if "test_id" not in trend:
        return trend
    return {
        **{k: v for k, v in trend.items() if k not in {"evidence_id", "test_id", "n_tests_so_far"}},
        "place": {"lat": place.lat, "lon": place.lon},
        "_record": scratch.ledger.last,
    }


def _where(side: dict) -> str:
    return f"{side['place']['lat']:.2f}, {side['place']['lon']:.2f}, {side['years'][0]}-{side['years'][1]}"


def _compare(session: Session, var_id: str, side_a: dict, side_b: dict) -> dict:
    sides = [_side_trend(session, var_id, s) for s in (side_a, side_b)]
    for s in sides:
        if "_record" not in s:
            # Re-mark a passing source failure so the outer ledger does not cache it either.
            reason = s.get("reason", "this side could not be tested")
            return _not_available(reason, bool(s.get("transient")), var_id=var_id)
    out_sides = []
    for s in sides:
        record = s["_record"]
        rest = {k: v for k, v in s.items() if k != "_record"}
        test_id = _log(session, replace(record, kind="compare", label=f"{record.label} at {_where(rest)}"))
        out_sides.append({"test_id": test_id, **rest})
    a, b = out_sides
    sa, sb = a["slope_per_decade"], b["slope_per_decade"]
    return {
        "var_id": var_id,
        "a": a,
        "b": b,
        "difference_per_decade": None if sa is None or sb is None else _num(sa - sb),
        "unit": a["unit"],
        "test_ids": [a["test_id"], b["test_id"]],
        "n_tests_so_far": session.ledger.n_finite(),
    }


# --------------------------------------------------------------------------- years_needed_for


def years_needed_for(session: Session, series_id: str) -> dict:
    series = session.series.get(series_id)
    if series is None:
        return _not_available(f"unknown series_id {series_id!r}; call get_series first")
    return data._through_ledger(
        session, "years_needed_for", {"series_id": series_id}, lambda: _years(session, series, series_id)
    )


def _years(session: Session, series: pd.Series, series_id: str) -> dict:
    if data.is_annual(session, series, series_id):  # one value per year: the annual formula
        return {
            "series_id": series_id,
            "basis": "annual",
            "years": [int(series.index.year.min()), int(series.index.year.max())],
            "years_needed": annual_years_needed(series, annual_trend(series)),
        }
    anomalies = monthly_anomalies(series)
    res = mk_trend_test(anomalies)  # only feeds the formula; not a counted test, nothing is logged
    slope = None if res.too_short else res.sen_slope_per_decade
    return {
        "series_id": series_id,
        "years": [int(series.index.year.min()), int(series.index.year.max())],
        "years_needed": years_needed(anomalies, slope),
    }
