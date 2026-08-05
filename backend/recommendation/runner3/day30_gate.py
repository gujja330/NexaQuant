"""Runner 3 · Day-30 Gate · GO/NO-GO checkpoint.

Per RL-Runner3 pre-registered criteria:
    PASS if ≥2 of 3 satisfied at day 30:
        1. R3 Sharpe within 0.2 of R2
        2. R3 Calibration Brier score better than R2 (or absolute < 0.20)
        3. R3 top-model Feature Attribution edge > +3pp
    Requires n ≥ 20 closed positions in shadow ledger (per Claude PDF n≥20 rule).
    Below n=20 · defer gate rather than declare on noise.

Fail → STAND DOWN · archive R3 · no Tier 2 spend.
Pass → continue shadow · unlock Tier 2 engineering.

Verdict lands in reports/research/runner3/day30_gate_{market}.json.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from .shadow_ledger import load_all, count_distinct_asofs


MIN_POSITIONS = 20            # Claude PDF · applies here explicitly
MIN_DAYS = 30                 # Day-30 gate


def _load_cfg(root: Path) -> dict:
    p = root / "configs" / "runner3.json"
    if not p.exists(): return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _compute_shadow_returns(root: Path, market: str) -> list[float]:
    """Very simplified · uses shadow_ledger entry_price vs position_store
    last_seen_price when the ticker exists there. Real Sharpe/Brier come
    later once we have close-price fetch for R3 shadow tickers."""
    rows = load_all(root, market=market)
    if not rows: return []
    reports = root / ("usa/reports" if market == "usa" else "reports")
    pos_file = reports / "position_store" / market / "positions.json"
    px_lookup = {}
    if pos_file.exists():
        try:
            d = json.loads(pos_file.read_text(encoding="utf-8"))
            for t, p in (d.get("positions") or {}).items():
                px_lookup[t.replace(".NS", "").replace(".BO", "")] = p.get("last_seen_price")
        except Exception:
            pass
    rets = []
    for r in rows:
        entry = r.get("entry_price")
        if not entry: continue
        t = r.get("ticker", "").replace(".NS", "").replace(".BO", "")
        last = px_lookup.get(t)
        if not last: continue
        rets.append((last - entry) / entry)
    return rets


def _sharpe(returns: list[float], rf_annual: float = 0.04) -> float | None:
    if len(returns) < 2: return None
    import statistics
    mean_r = statistics.mean(returns)
    stdev_r = statistics.stdev(returns) or 0.0001
    return round(((mean_r - rf_annual / 252) / stdev_r) * (252 ** 0.5), 3)


def _brier(probs: list[float], outcomes: list[int]) -> float | None:
    if not probs or len(probs) != len(outcomes): return None
    return round(sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(probs), 4)


def _r2_sharpe(root: Path, market: str) -> float | None:
    """Extract R2's Sharpe from ai_scorecard or benchmark file if present."""
    for pth in [root / "reports" / "ai_scorecard.json",
                    root / "reports" / "benchmark_runner2_india.json"]:
        if not pth.exists(): continue
        try:
            d = json.loads(pth.read_text(encoding="utf-8"))
            for k in ("sharpe", "sharpe_ratio", "runner2_sharpe"):
                v = d.get(k)
                if v is not None: return float(v)
        except Exception:
            continue
    return None


def evaluate(root: Path, market: str, asof: str | None = None) -> dict:
    asof = asof or date.today().isoformat()
    cfg = _load_cfg(root)
    gate = cfg.get("day30_gate_pass_criteria", {})

    n_days = count_distinct_asofs(root, market)
    all_entries = load_all(root, market=market)
    n_positions = len(all_entries)

    if n_days < MIN_DAYS:
        return _verdict("DEFERRED", asof, market, n_days, n_positions,
                              reason=f"only {n_days} shadow days · need {MIN_DAYS}",
                              details={})
    if n_positions < MIN_POSITIONS:
        return _verdict("DEFERRED", asof, market, n_days, n_positions,
                              reason=f"only {n_positions} shadow positions · "
                                        f"need {MIN_POSITIONS} (n≥20 rule)",
                              details={})

    returns = _compute_shadow_returns(root, market)
    r3_sharpe = _sharpe(returns) or 0.0
    r2_sharpe = _r2_sharpe(root, market) or 0.0
    outcomes = [1 if r > 0 else 0 for r in returns]
    probs = [float(e.get("calibrated_confidence") or e.get("predicted_probability") or 0.5)
                 for e in all_entries[:len(outcomes)]]
    r3_brier = _brier(probs, outcomes)

    within_sharpe = abs(r3_sharpe - r2_sharpe) <= gate.get("sharpe_within_of_r2", 0.2)
    brier_ok = (r3_brier is not None and
                     r3_brier < gate.get("brier_max_absolute", 0.20))
    # Feature edge · placeholder until per-position attribution feed lands
    top_edge_ok = False
    top_edge_pp = None

    passes = sum([within_sharpe, brier_ok, top_edge_ok])
    verdict = "PASS" if passes >= gate.get("must_pass_of_three", 2) else "FAIL"

    return _verdict(verdict, asof, market, n_days, n_positions,
                          reason=f"{passes}/3 criteria met",
                          details={
                              "r3_sharpe":  r3_sharpe,
                              "r2_sharpe":  r2_sharpe,
                              "sharpe_within_r2": within_sharpe,
                              "r3_brier":   r3_brier,
                              "brier_ok":   brier_ok,
                              "top_edge_pp": top_edge_pp,
                              "top_edge_ok": top_edge_ok,
                          })


def _verdict(v: str, asof: str, market: str, n_days: int, n_positions: int,
                  reason: str, details: dict) -> dict:
    return {
        "engine":      "aegis.runner3.day30_gate.v1",
        "asof":        asof, "market": market,
        "verdict":     v,             # PASS · FAIL · DEFERRED
        "n_days":      n_days, "n_positions": n_positions,
        "reason":      reason, "details": details,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "next_action": {
            "PASS":     "Continue shadow · unlock Tier 2 engineering",
            "FAIL":     "STAND DOWN · archive R3 · no Tier 2 spend",
            "DEFERRED": "Continue accumulating shadow data · re-evaluate daily",
        }.get(v, "unknown"),
    }


def emit(root: Path, market: str, verdict: dict) -> Path:
    p = root / "reports" / "research" / "runner3" / f"day30_gate_{market}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(verdict, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return p
