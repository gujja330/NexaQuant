"""
MON001 monitoring engine — drift detection + evidence-state machine.

Consumes:
- The forward observation ledger (append-only JSONL)
- The baseline expected envelope (sealed JSON derived from LAB009 State C)
- The current production fingerprint (via `fingerprint.compute_fingerprint`)
- Market data via `india.feature_engine.load_panels` (READ-ONLY)

Produces per-run diagnostics:
- fingerprint status (CONFIG_DRIFT? OK?)
- forward observation coverage (days since boundary, cycles completed, samples per metric)
- per-metric envelope comparison (min/median/max envelope vs forward point + delta)
- active drift alerts D1-D10
- global MON001 state
- HALT_REVIEW_REQUIRED evaluation (persistent divergence)

Does NOT touch: HOLD, CONFIG, current_regime, HRP, sector_cap, name_cap, or any strategy
input. Does NOT increment cumulative_strategy_search.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# --- pure state constants ------------------------------------------------------------

STATES = ("INSUFFICIENT_EVIDENCE", "PASS", "WATCH", "DIVERGED",
          "HALT_REVIEW_REQUIRED", "DATA_INTEGRITY_FAILURE")

DRIFT_DIMENSIONS = (
    "D1_CONFIG_DRIFT", "D2_PERFORMANCE_DRIFT", "D3_RISK_DRIFT", "D4_TURNOVER_DRIFT",
    "D5_COST_DRIFT", "D6_REGIME_BEHAVIOUR_DRIFT", "D7_CONCENTRATION_DRIFT",
    "D8_DATA_DRIFT", "D9_EXECUTION_DRIFT", "D10_DATA_INTEGRITY_FAILURE",
)


@dataclass
class MetricEvidence:
    metric: str
    forward_value: float | None
    envelope_min: float | None
    envelope_median: float | None
    envelope_max: float | None
    sample_size: int
    minimum_required: int
    status: str                         # PASS / WATCH / DIVERGED / INSUFFICIENT_EVIDENCE
    reason: str

    def as_dict(self) -> dict:
        return {
            "metric": self.metric,
            "forward_value": self.forward_value,
            "envelope_min": self.envelope_min,
            "envelope_median": self.envelope_median,
            "envelope_max": self.envelope_max,
            "sample_size": self.sample_size,
            "minimum_required": self.minimum_required,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class DriftAlert:
    dimension: str
    level: str                          # WATCH / DIVERGED / HALT
    reason: str
    first_seen: str | None = None
    consecutive_reports: int = 1
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "level": self.level,
            "reason": self.reason,
            "first_seen": self.first_seen,
            "consecutive_reports": self.consecutive_reports,
            "details": self.details,
        }


@dataclass
class MonitorReport:
    run_date_utc: str
    forward_boundary_asof: str
    forward_days_accumulated: int
    forward_recs_ingested: int
    completed_cycles: int
    fingerprint_status: str
    fingerprint_hash_current: str
    fingerprint_hash_sealed: str
    ledger_integrity: dict
    baseline_envelope_hash: str
    broker_status: dict
    metric_evidence: list[MetricEvidence]
    drift_alerts: list[DriftAlert]
    global_state: str
    halt_review_required: bool
    reason: str

    def as_dict(self) -> dict:
        return {
            "run_date_utc": self.run_date_utc,
            "forward_boundary_asof": self.forward_boundary_asof,
            "forward_days_accumulated": self.forward_days_accumulated,
            "forward_recs_ingested": self.forward_recs_ingested,
            "completed_cycles": self.completed_cycles,
            "fingerprint_status": self.fingerprint_status,
            "fingerprint_hash_current": self.fingerprint_hash_current,
            "fingerprint_hash_sealed": self.fingerprint_hash_sealed,
            "ledger_integrity": self.ledger_integrity,
            "baseline_envelope_hash": self.baseline_envelope_hash,
            "broker_status": self.broker_status,
            "metric_evidence": [e.as_dict() for e in self.metric_evidence],
            "drift_alerts": [a.as_dict() for a in self.drift_alerts],
            "global_state": self.global_state,
            "halt_review_required": self.halt_review_required,
            "reason": self.reason,
        }


# --- forward observation coverage --------------------------------------------------------


def _trading_days_between(start_date: date, end_date: date, closes_index: pd.Index) -> int:
    """Count trading days in (start_date, end_date] using the market close index."""
    idx = pd.to_datetime(closes_index).normalize()
    mask = (idx > pd.Timestamp(start_date)) & (idx <= pd.Timestamp(end_date))
    return int(mask.sum())


def forward_coverage(ledger_rows: list[dict], run_date: date,
                      closes_index: pd.Index) -> dict:
    """Return coverage stats: recs ingested, unique cycles, completed cycles, days since
    first observation, days since forward boundary."""
    if not ledger_rows:
        return {
            "recs_ingested": 0, "unique_cycles": 0, "completed_cycles": 0,
            "forward_days_from_first_obs": 0,
        }
    asofs = pd.to_datetime([r["asof"] for r in ledger_rows]).normalize()
    first = asofs.min().date()
    cycles = {r["portfolio_cycle"] for r in ledger_rows}
    completed = {c for c in cycles
                 if all(_cycle_asof_days(c) + 63 <= (run_date - date(2000, 1, 1)).days
                        for _ in [0])}
    completed_count = sum(1 for c in cycles if _is_cycle_completed(c, run_date))
    return {
        "recs_ingested": len(ledger_rows),
        "unique_cycles": len(cycles),
        "completed_cycles": completed_count,
        "forward_days_from_first_obs": _trading_days_between(first, run_date, closes_index),
    }


def _cycle_asof_days(cycle: str) -> int:
    """Extract the asof from a portfolio_cycle string like '2026-06-25_63'."""
    try:
        asof_str, _hold = cycle.rsplit("_", 1)
        d = datetime.strptime(asof_str, "%Y-%m-%d").date()
        return (d - date(2000, 1, 1)).days
    except Exception:
        return -1


def _is_cycle_completed(cycle: str, run_date: date) -> bool:
    """Cycle is 'completed' if HOLD trading days have elapsed. Approximation using 90
    calendar days as a conservative buffer for 63 trading days."""
    try:
        asof_str, hold = cycle.rsplit("_", 1)
        asof = datetime.strptime(asof_str, "%Y-%m-%d").date()
        hold_td = int(hold)
        # 63 trading days ≈ 90 calendar days (rough)
        approx_calendar = int(hold_td * 1.45)
        return (run_date - asof).days >= approx_calendar
    except Exception:
        return False


# --- per-metric evidence -----------------------------------------------------------------


def _forward_daily_returns(ledger_rows: list[dict], closes: pd.DataFrame,
                            benchmark: pd.Series | None,
                            run_date: date) -> tuple[pd.Series, pd.Series | None, int]:
    """Reconstruct a paper equity curve from the forward-ledger snapshots.

    For each portfolio cycle, we treat the observed snapshots as an equal-weighted (by
    intended_weight) portfolio held over HOLD days. We stitch cycles chronologically. This
    is a coarse approximation — for MON001 seal time it is enough to detect gross drift.
    Broker-fill-based curves come later (D9).
    """
    if not ledger_rows:
        return pd.Series(dtype=float), None, 0

    df = pd.DataFrame(ledger_rows)
    df["asof"] = pd.to_datetime(df["asof"]).dt.normalize()
    df = df.sort_values("asof")
    cycles = sorted(df["portfolio_cycle"].unique())

    equity_segments: list[pd.Series] = []
    running_val = 1.0
    for cyc in cycles:
        rows = df[df["portfolio_cycle"] == cyc]
        cyc_start = rows["asof"].min().normalize()
        try:
            hold_td = int(cyc.rsplit("_", 1)[1])
        except Exception:
            hold_td = 63
        # end of cycle: hold_td trading days after cyc_start, capped by run_date
        idx = closes.index[closes.index >= cyc_start]
        if len(idx) < 2:
            continue
        segment_end_pos = min(hold_td, len(idx) - 1,
                              (idx <= pd.Timestamp(run_date)).sum() - 1)
        if segment_end_pos <= 0:
            continue
        seg_index = idx[: segment_end_pos + 1]
        symbols = [s for s in rows["symbol"].tolist() if s in closes.columns]
        if not symbols:
            continue
        weights = np.array(
            [float(rows.loc[rows["symbol"] == s, "intended_weight"].iloc[0])
             for s in symbols])
        wsum = weights.sum()
        if wsum <= 0:
            continue
        weights = weights / wsum
        exp_mult = float(rows["exposure_multiplier"].iloc[0])
        stock_px = closes.loc[seg_index, symbols].ffill()
        stock_rets = stock_px.pct_change().fillna(0.0)
        port_rets = stock_rets.dot(weights) * exp_mult
        seg_eq = (1 + port_rets).cumprod() * running_val
        equity_segments.append(seg_eq)
        running_val = float(seg_eq.iloc[-1])

    if not equity_segments:
        return pd.Series(dtype=float), None, 0

    equity = pd.concat(equity_segments).sort_index()
    equity = equity[~equity.index.duplicated(keep="last")]
    daily = equity.pct_change().dropna()

    bench_daily = None
    if benchmark is not None:
        b = benchmark.reindex(equity.index).ffill()
        bench_daily = b.pct_change().dropna()

    return daily, bench_daily, int(daily.shape[0])


def _sharpe(daily: pd.Series, trading_days_per_year: int = 252) -> float:
    if daily.empty or daily.std() == 0:
        return float("nan")
    return float(daily.mean() / daily.std() * math.sqrt(trading_days_per_year))


def _max_dd(daily: pd.Series) -> float:
    if daily.empty:
        return float("nan")
    eq = (1 + daily).cumprod()
    dd = eq / eq.cummax() - 1
    return float(dd.min())


def _ulcer(daily: pd.Series) -> float:
    if daily.empty:
        return float("nan")
    eq = (1 + daily).cumprod()
    dd = (eq / eq.cummax() - 1) * 100
    return float(math.sqrt((dd ** 2).mean()))


def evaluate_metric_evidence(daily: pd.Series, envelope: dict,
                              min_evidence_cfg: dict) -> list[MetricEvidence]:
    """Compare forward equity metrics against the LAB009 envelope."""
    out: list[MetricEvidence] = []
    n = int(daily.shape[0])

    metrics = envelope.get("metrics", {})

    def _lookup_envelope(metric_key: str) -> tuple[float, float, float] | None:
        m = metrics.get(metric_key, {})
        # Use cash=0.0 envelope by default; MON001 report also computes cash=0.06 side-by-side.
        row = m.get("0.0") or m.get(0.0)
        if not row:
            return None
        return row["min"], row["median"], row["max"]

    # Sharpe
    min_days = int(min_evidence_cfg.get("daily_metrics_days", 30))
    env = _lookup_envelope("sharpe_full")
    if n < min_days:
        out.append(MetricEvidence("sharpe_forward", None, env[0] if env else None,
                                   env[1] if env else None, env[2] if env else None,
                                   n, min_days, "INSUFFICIENT_EVIDENCE",
                                   f"only {n} forward days, need {min_days}"))
    elif env is None:
        out.append(MetricEvidence("sharpe_forward", _sharpe(daily), None, None, None,
                                   n, min_days, "INSUFFICIENT_EVIDENCE",
                                   "no envelope available"))
    else:
        fwd = _sharpe(daily)
        env_min, env_med, env_max = env
        sd_sharpe = 1.0 / math.sqrt(max(1, n) / 252)  # rough Sharpe SD proxy
        status = "PASS"
        reason = "sharpe within envelope"
        if fwd < env_min - sd_sharpe:
            status, reason = "DIVERGED", (
                f"forward Sharpe {fwd:.3f} < envelope_min {env_min:.3f} - 1.0σ ({sd_sharpe:.3f})")
        elif fwd < env_med - sd_sharpe:
            status, reason = "WATCH", (
                f"forward Sharpe {fwd:.3f} < envelope_median {env_med:.3f} - 1.0σ ({sd_sharpe:.3f})")
        out.append(MetricEvidence("sharpe_forward", fwd, env_min, env_med, env_max,
                                   n, min_days, status, reason))

    # MaxDD — requires more days
    min_days_dd = int(min_evidence_cfg.get("maxdd_days", 126))
    env = _lookup_envelope("max_dd_full")
    if n < min_days_dd:
        out.append(MetricEvidence("max_dd_forward", None,
                                   env[0] if env else None,
                                   env[1] if env else None,
                                   env[2] if env else None,
                                   n, min_days_dd, "INSUFFICIENT_EVIDENCE",
                                   f"only {n} forward days, need {min_days_dd} for MaxDD"))
    else:
        fwd = _max_dd(daily)
        if env is None:
            out.append(MetricEvidence("max_dd_forward", fwd, None, None, None,
                                       n, min_days_dd, "INSUFFICIENT_EVIDENCE",
                                       "no envelope available"))
        else:
            env_min, env_med, env_max = env  # env_min is the WORST (most negative)
            watch_thresh = env_min * 1.10
            div_thresh = env_min * 1.20
            status = "PASS"
            reason = "MaxDD within envelope"
            if fwd < div_thresh:
                status, reason = "DIVERGED", (
                    f"forward MaxDD {fwd:.4f} < envelope_worst {env_min:.4f} × 1.20 "
                    f"= {div_thresh:.4f}")
            elif fwd < watch_thresh:
                status, reason = "WATCH", (
                    f"forward MaxDD {fwd:.4f} < envelope_worst {env_min:.4f} × 1.10 "
                    f"= {watch_thresh:.4f}")
            out.append(MetricEvidence("max_dd_forward", fwd, env_min, env_med, env_max,
                                       n, min_days_dd, status, reason))

    # Ulcer — informational, but respects the sortino_days min so state machine reflects
    # true sample sufficiency. Marked INSUFFICIENT_EVIDENCE below the threshold; above it,
    # reported without a hard envelope gate.
    ulcer_min = int(min_evidence_cfg.get("sortino_days", 126))
    if n < ulcer_min:
        out.append(MetricEvidence("ulcer_forward", None, None, None, None,
                                   n, ulcer_min, "INSUFFICIENT_EVIDENCE",
                                   f"only {n} forward days, need {ulcer_min}"))
    else:
        out.append(MetricEvidence("ulcer_forward", _ulcer(daily), None, None, None,
                                   n, ulcer_min, "PASS",
                                   "informational, no sealed threshold"))

    return out


# --- concentration + data quality --------------------------------------------------------


def evaluate_concentration(ledger_rows: list[dict], name_cap: float, sector_cap: int,
                            tolerance: float, over_by: int) -> DriftAlert | None:
    """D7: name_cap or sector_cap violation."""
    if not ledger_rows:
        return None
    df = pd.DataFrame(ledger_rows)
    name_max = float(df["intended_weight"].max()) if not df.empty else 0.0
    if name_max > name_cap * (1 + tolerance):
        return DriftAlert(
            "D7_CONCENTRATION_DRIFT", "DIVERGED",
            f"intended_weight {name_max:.4f} > name_cap {name_cap} × (1 + {tolerance})",
            details={"max_weight": name_max, "name_cap": name_cap},
        )
    # sector_cap per cycle
    for cyc, grp in df.groupby("portfolio_cycle"):
        sec_counts = grp.groupby("sector").size()
        if (sec_counts > sector_cap + over_by).any():
            over = sec_counts[sec_counts > sector_cap + over_by].to_dict()
            return DriftAlert(
                "D7_CONCENTRATION_DRIFT", "DIVERGED",
                f"cycle {cyc}: sector cap {sector_cap} exceeded by more than {over_by}: {over}",
                details={"cycle": cyc, "over_by_sector": over},
            )
    return None


def evaluate_data_drift(ledger_rows: list[dict], watch_missing_pct: float,
                        diverged_missing_pct: float, watch_stale_pct: float,
                        diverged_stale_pct: float) -> DriftAlert | None:
    """D8: missing prices + stale recommendations."""
    if not ledger_rows:
        return None
    df = pd.DataFrame(ledger_rows)
    n = len(df)
    missing = float((df["data_quality"] != "OK").mean()) if n > 0 else 0.0
    stale = float((df["data_quality"] == "STALE").mean()) if n > 0 else 0.0
    if missing >= diverged_missing_pct:
        return DriftAlert(
            "D8_DATA_DRIFT", "DIVERGED",
            f"{missing:.2%} of forward rows have non-OK data quality "
            f"(>= {diverged_missing_pct:.0%} threshold)",
            details={"missing_pct": missing, "stale_pct": stale},
        )
    if missing >= watch_missing_pct or stale >= watch_stale_pct:
        return DriftAlert(
            "D8_DATA_DRIFT", "WATCH",
            f"missing_pct={missing:.2%} stale_pct={stale:.2%}",
            details={"missing_pct": missing, "stale_pct": stale},
        )
    return None


# --- global state assembly ---------------------------------------------------------------


def assemble_global_state(fingerprint_status: str, ledger_integrity: dict,
                          metric_evidence: list[MetricEvidence],
                          alerts: list[DriftAlert]) -> tuple[str, bool, str]:
    """Return (global_state, halt_review_required, reason)."""
    if fingerprint_status == "DRIFT":
        return ("HALT_REVIEW_REQUIRED", True,
                "CONFIG_DRIFT: production baseline changed since MON001 seal")
    if not ledger_integrity.get("ok", True):
        return ("DATA_INTEGRITY_FAILURE", True,
                f"ledger integrity failure: {ledger_integrity.get('reason', 'unknown')}")

    any_diverged = any(a.level == "DIVERGED" for a in alerts) or any(
        e.status == "DIVERGED" for e in metric_evidence)
    any_watch = any(a.level == "WATCH" for a in alerts) or any(
        e.status == "WATCH" for e in metric_evidence)
    non_insufficient = [e for e in metric_evidence if e.status != "INSUFFICIENT_EVIDENCE"]

    if any_diverged:
        return ("DIVERGED", False,
                "one or more DIVERGED alerts active; HALT_REVIEW_REQUIRED only after "
                "4 consecutive weekly reports of persistent divergence")
    if any_watch:
        return ("WATCH", False, "one or more WATCH alerts active; no DIVERGED alerts")
    if not non_insufficient:
        return ("INSUFFICIENT_EVIDENCE", False,
                "no metric has sufficient forward observations to evaluate")
    return ("PASS", False, "all evaluable metrics within envelope; no drift alerts")
