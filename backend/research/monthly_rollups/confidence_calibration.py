"""Monthly rollup · Confidence Calibration.

For every closed position in the given month, bucket by predicted confidence
(from rank_history.jsonl) and compute the actual hit rate. Perfect calibration
= bucket midpoint == actual hit rate.

Sample:
    Bucket 40-50%: predicted midpoint 45% · actual hit rate 42% · calibration Δ = -3pp · n=17
    Bucket 60-70%: predicted midpoint 65% · actual hit rate 58% · calibration Δ = -7pp · n=8
    Bucket 80-90%: INSUFFICIENT DATA (n<5)

If bucket calibration diverges from midpoint by >10pp over 30+ samples · emit
CALIBRATION_DRIFT alert.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable


MIN_SAMPLES_PER_BUCKET = 5     # below this → insufficient_data flag on bucket
DRIFT_ALERT_THRESHOLD_PP = 10.0   # bucket vs midpoint > this = alert
BUCKETS = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50),
              (50, 60), (60, 70), (70, 80), (80, 90), (90, 100)]

# What counts as a "hit" · position closed positive OR still open with positive P&L
HIT_MIN_RET_PCT = 0.0


@dataclass
class Bucket:
    lo: int
    hi: int
    midpoint: float
    n_samples: int
    n_hits: int
    hit_rate_pct: float | None
    calibration_delta_pp: float | None    # actual - midpoint · negative = over-confident
    insufficient_data: bool


def _load_positions_history(root: Path, market: str, month: str) -> list[dict]:
    """Load closed positions from position_store history + open positions
    still active. `month` = YYYY-MM. Returns rows with:
        ticker, runner, entry_date, exit_date, entry_price, exit_price, ret_pct
    """
    reports = root / ("usa/reports" if market == "usa" else "reports")
    positions_file = reports / "position_store" / market / "positions.json"
    history_file = reports / "position_store" / market / "history.jsonl"
    rows: list[dict] = []
    if positions_file.exists():
        try:
            d = json.loads(positions_file.read_text(encoding="utf-8"))
            for t, p in (d.get("positions") or {}).items():
                fs = p.get("first_seen_date") or ""
                if not fs.startswith(month):
                    continue
                entry = p.get("first_seen_price") or 0
                exit_ = p.get("last_seen_price") or entry
                if not entry:
                    continue
                rows.append({
                    "ticker": t.replace(".NS", "").replace(".BO", ""),
                    "runner": "runner2",
                    "entry_date": fs, "exit_date": p.get("last_seen_date"),
                    "entry_price": entry, "exit_price": exit_,
                    "ret_pct": ((exit_ - entry) / entry) * 100.0,
                    "still_open": True,
                })
        except Exception:
            pass
    if history_file.exists():
        try:
            for line in history_file.read_text(encoding="utf-8").splitlines():
                if not line.strip(): continue
                try:  ev = json.loads(line)
                except json.JSONDecodeError: continue
                if not str(ev.get("asof") or "").startswith(month): continue
                entry = ev.get("first_seen_price") or 0
                exit_ = ev.get("last_seen_price") or entry
                if not entry: continue
                rows.append({
                    "ticker": (ev.get("ticker") or "").replace(".NS", "").replace(".BO", ""),
                    "runner": ev.get("runner", "runner2"),
                    "entry_date": ev.get("first_seen_date"),
                    "exit_date": ev.get("asof"),
                    "entry_price": entry, "exit_price": exit_,
                    "ret_pct": ((exit_ - entry) / entry) * 100.0,
                    "still_open": False,
                })
        except Exception:
            pass
    return rows


def _load_rank_history_by_month(root: Path, market: str, runner: str, month: str) -> dict:
    """Return {ticker: [{asof, confidence, rank}, ...]} for this month only."""
    p = root / "reports" / "research" / "rank_history.jsonl"
    if not p.exists(): return {}
    by_ticker: dict[str, list[dict]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try:  d = json.loads(line)
        except json.JSONDecodeError: continue
        if d.get("market") != market or d.get("runner") != runner: continue
        if not str(d.get("asof") or "").startswith(month): continue
        t = d.get("ticker") or ""
        by_ticker.setdefault(t, []).append(d)
    return by_ticker


def compute(root: Path, market: str, month: str,
                 runner: str = "runner2") -> dict:
    """Compute calibration report for (market, month, runner)."""
    positions = _load_positions_history(root, market, month)
    rh = _load_rank_history_by_month(root, market, runner, month)

    # Map each position to its entry-date confidence
    labeled: list[tuple[float, bool]] = []
    for pos in positions:
        t = pos["ticker"]
        # Find rank_history entry closest to entry_date
        ph = rh.get(t) or rh.get(t + ".NS") or rh.get(t + ".BO") or []
        if not ph: continue
        entry_dt = pos.get("entry_date") or ""
        candidates = [p for p in ph if (p.get("asof") or "") <= entry_dt]
        if not candidates: candidates = ph
        candidates.sort(key=lambda p: p.get("asof") or "")
        entry_snap = candidates[-1]
        conf = entry_snap.get("confidence")
        if conf is None: continue
        # Normalise · confidence stored as [0..1] · convert to pct
        conf_pct = conf * 100.0 if conf <= 1.0 else conf
        is_hit = pos["ret_pct"] > HIT_MIN_RET_PCT
        labeled.append((conf_pct, is_hit))

    buckets: list[Bucket] = []
    for lo, hi in BUCKETS:
        in_bucket = [(c, h) for (c, h) in labeled if lo <= c < hi]
        n = len(in_bucket)
        n_hits = sum(1 for _, h in in_bucket if h)
        insufficient = n < MIN_SAMPLES_PER_BUCKET
        hit_rate = round(n_hits / n * 100.0, 1) if n > 0 else None
        mid = (lo + hi) / 2.0
        cal_delta = round(hit_rate - mid, 1) if hit_rate is not None else None
        buckets.append(Bucket(
            lo=lo, hi=hi, midpoint=mid, n_samples=n, n_hits=n_hits,
            hit_rate_pct=hit_rate, calibration_delta_pp=cal_delta,
            insufficient_data=insufficient,
        ))

    total_n = sum(b.n_samples for b in buckets)
    total_hits = sum(b.n_hits for b in buckets)
    overall_hit_rate = round(total_hits / total_n * 100.0, 1) if total_n > 0 else None

    # Drift alerts (bucket-level)
    drift_alerts = []
    for b in buckets:
        if not b.insufficient_data and b.n_samples >= 30 \
           and b.calibration_delta_pp is not None \
           and abs(b.calibration_delta_pp) > DRIFT_ALERT_THRESHOLD_PP:
            direction = "OVER-CONFIDENT" if b.calibration_delta_pp < 0 else "UNDER-CONFIDENT"
            drift_alerts.append({
                "bucket": f"{b.lo}-{b.hi}%", "direction": direction,
                "delta_pp": b.calibration_delta_pp, "n": b.n_samples,
                "midpoint": b.midpoint, "actual": b.hit_rate_pct,
            })

    return {
        "engine":              "aegis.research.confidence_calibration.v1",
        "generated_utc":       datetime.now(timezone.utc).isoformat(),
        "market":              market,
        "month":               month,
        "runner":              runner,
        "total_samples":       total_n,
        "total_hits":          total_hits,
        "overall_hit_rate_pct": overall_hit_rate,
        "insufficient_data":   total_n < MIN_SAMPLES_PER_BUCKET,
        "min_samples_per_bucket": MIN_SAMPLES_PER_BUCKET,
        "buckets":             [asdict(b) for b in buckets],
        "drift_alerts":        drift_alerts,
    }


def render_md(rep: dict) -> str:
    """Render report as a Markdown table for operator inspection."""
    lines = [f"# Confidence Calibration · {rep['market'].upper()} · {rep['month']}",
                "",
                f"Runner: **{rep['runner']}** · Total samples: **{rep['total_samples']}** · "
                f"Overall hit rate: **{rep['overall_hit_rate_pct']}%**",
                ""]
    if rep["insufficient_data"]:
        lines.append(f"> ⚠️ INSUFFICIENT DATA · total samples {rep['total_samples']} "
                          f"< min {rep['min_samples_per_bucket']} · report is directional only.\n")
    lines += ["| Bucket | Midpoint | n | Hits | Actual % | Δ vs Mid | Note |",
                 "|---|---|---|---|---|---|---|"]
    for b in rep["buckets"]:
        note = "insufficient" if b["insufficient_data"] else ""
        cal = f"{b['calibration_delta_pp']:+.1f}pp" if b["calibration_delta_pp"] is not None else "—"
        actual = f"{b['hit_rate_pct']}%" if b["hit_rate_pct"] is not None else "—"
        lines.append(f"| {b['lo']}-{b['hi']}% | {b['midpoint']:.0f}% | "
                          f"{b['n_samples']} | {b['n_hits']} | {actual} | {cal} | {note} |")
    if rep["drift_alerts"]:
        lines += ["", "## Drift alerts (n≥30 samples · |Δ|>10pp)", ""]
        for a in rep["drift_alerts"]:
            lines.append(f"- **{a['bucket']}** · {a['direction']} · "
                              f"actual {a['actual']}% vs midpoint {a['midpoint']}% "
                              f"(Δ {a['delta_pp']:+.1f}pp · n={a['n']})")
    return "\n".join(lines) + "\n"
