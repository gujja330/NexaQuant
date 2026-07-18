"""Decision Center · daily snapshot store.

For each day, capture the minimum state needed to detect what changed
vs the following day. Snapshots live under
`data/market_intelligence/derived/decisions/YYYY-MM-DD.json` — derived
data, not committed to git.

The snapshot is intentionally lean: per-ticker action + intelligence
score + confidence + current portfolio weight + key price levels."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
SNAP_DIR = _ROOT / "data" / "market_intelligence" / "derived" / "decisions"
SNAP_DIR.mkdir(parents=True, exist_ok=True)


# Action tier ordering: higher = more bullish
ACTION_TIER = {
    "Strong-Buy":  5,
    "Buy":         4,
    "Accumulate":  3,
    "Hold":        2,
    "Watchlist":   1,
    "Reduce":     -1,
    "Sell":       -2,
    "Avoid":      -3,
}


def _read(name: str):
    p = _ROOT / "reports" / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def capture_today(day: str | None = None) -> dict:
    """Build today's snapshot from live reports/*.json."""
    day = day or date.today().isoformat()

    recs = _read("recommendations.json") or {}
    ii = _read("investment_intelligence.json") or {}
    risk = _read("risk_capital_v2_latest.json") or {}
    val = _read("validation_v2_latest.json") or {}
    port = _read("portfolio.json") or {}

    # Index intelligence + sizing by ticker
    ii_by_ticker = {str(r.get("ticker")): r for r in (ii.get("reports") or [])}
    size_by_ticker = {str(s.get("ticker")): s for s in (risk.get("sizing") or [])}

    entries = []
    for r in (recs.get("recommendations") or []):
        t = str(r.get("ticker"))
        ii_r = ii_by_ticker.get(t)
        size_r = size_by_ticker.get(t)
        entries.append({
            "ticker":            t,
            "sector":            r.get("sector"),
            "industry":          r.get("industry"),
            "action":            r.get("recommendation"),
            "action_tier":       ACTION_TIER.get(r.get("recommendation"), 0),
            "raw_score":         r.get("composite_decision_score"),
            "confidence":        r.get("confidence"),
            "conviction_pct":    r.get("conviction_pct"),
            "entry_price":       r.get("entry_price"),
            "target_1":          r.get("target_1"),
            "stop_loss":         r.get("stop_loss"),
            "expected_hold":     r.get("expected_holding_days"),
            "currently_held":    bool(r.get("currently_held")),
            "current_weight":    r.get("current_weight"),
            "unrealised_pnl_pct":r.get("unrealised_pnl_pct"),
            "intelligence_score":(ii_r or {}).get("intelligence_score"),
            "fusion_action":     (ii_r or {}).get("fusion_decision"),
            "target_weight":     (size_r or {}).get("target_weight"),
            "sizing_verdict":    (size_r or {}).get("verdict"),
        })

    # Portfolio-level (single reference construction: balanced+hrp)
    portfolios = port.get("portfolios") or []
    ref = next((p for p in portfolios if p.get("portfolio_type") == "balanced"
                                            and p.get("allocator") == "hrp"),
                  portfolios[0] if portfolios else None)

    return {
        "date":                day,
        "n_recs":              len(entries),
        "entries":             entries,
        "portfolio_ref":       {
            "portfolio_type":   ref.get("portfolio_type") if ref else None,
            "allocator":        ref.get("allocator") if ref else None,
            "cash_allocation_pct": ref.get("cash_allocation_pct") if ref else None,
            "n_positions":      ref.get("n_positions") if ref else 0,
            "top_positions":    [{"ticker": p.get("ticker"),
                                    "weight": p.get("weight")}
                                    for p in ((ref or {}).get("positions") or [])[:20]],
        } if ref else {},
        "validation_summary":  {
            "n_open":          val.get("n_open_positions"),
            "n_closed":        val.get("n_closed_trades"),
            "drift_flag":      (val.get("metric_drift") or {}).get("flag"),
        },
    }


def persist(snapshot: dict) -> Path:
    day = snapshot["date"]
    p = SNAP_DIR / f"{day}.json"
    with p.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, default=str)
    return p


def load_snapshot(day: str) -> dict | None:
    p = SNAP_DIR / f"{day}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_latest_previous(before: str) -> dict | None:
    """Return the most recent snapshot with date < `before`, or None."""
    if not SNAP_DIR.exists():
        return None
    candidates = sorted(p.stem for p in SNAP_DIR.glob("*.json"))
    candidates = [c for c in candidates if c < before]
    if not candidates:
        return None
    return load_snapshot(candidates[-1])
