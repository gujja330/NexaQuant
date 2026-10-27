"""RE-ENTRY COOLDOWN · counterfactual replay. Decides nothing.

THE MEASURED DEFECT
-------------------
Across 143 closed India trades, 25 tickers lost more than once and
**55 of 116 losses (47%) were re-entries into a name that had already
stopped the system out**. OFSS x3, ATUL x3, MARUTI x3, COALINDIA x3,
OIL x3. The system has no memory of having just been wrong about a name.

This module measures what a cooldown would have removed: after a ticker
exits on a stop, block re-entry into it for N trading days.

WHY THIS IS A COUNTERFACTUAL AND NOT A RESULT
---------------------------------------------
It is evaluated on the same 143 trades that motivated it. That is the
single easiest way in finance to produce a beautiful lie, so:

  - the P&L delta is reported with its DATE-UNIT count, because 143
    trades across 36 entry dates is not 143 independent observations
  - suppressed trades are removed, NOT replaced with an assumed
    alternative. Capital freed by a blocked entry would in reality have
    gone somewhere; pretending to know where would be fabrication, so
    the number reported is "what would not have happened", which is a
    strictly smaller claim than "what we would have earned"
  - no threshold is tuned to a target. N is swept over a fixed grid
    declared up front

Nothing here promotes anything. Production selection is untouched.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.r3.reentry_cooldown.v1"

# Declared up front so no one can claim the grid was fitted afterwards.
COOLDOWN_GRID = (5, 10, 20, 30)

# Exit reasons that mean "this name just went against us". A cooldown is
# about not repeating a mistake, so a routine rotation or a horizon
# expiry does not arm it.
STOP_REASONS = ("stop-loss triggered", "stop loss", "stop-loss")


def _f(v) -> Optional[float]:
    try:
        return float(str(v).replace("%", "").strip())
    except Exception:
        return None


def _d(v) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def _tkey(t) -> str:
    return str(t).upper().strip().replace(".NS", "").replace(".BO", "")


def load_closed(root: Path, market: str) -> list:
    """Every REALIZED EXIT with the fields the replay needs."""
    p = (Path(root) / "reports" / "context"
         / ("canonical_lifecycle_%s.json" % market))
    if not p.exists():
        return []
    lc = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for e in (lc.get("exits") or []):
        if e.get("record_type") != "REALIZED EXIT":
            continue
        ep, xp = _f(e.get("entry_price")), _f(e.get("exit_price"))
        ed, xd = _d(e.get("entry_date")), _d(e.get("exit_date"))
        if not (ep and xp and ep > 0 and ed and xd):
            continue
        out.append({
            "market": market,
            "ticker": _tkey(e.get("ticker")),
            "entry_date": ed,
            "exit_date": xd,
            # recomputed from prices · never the reported field
            "pnl_pct": 100.0 * (xp - ep) / ep,
            "exit_reason": str(e.get("exit_reason") or ""),
            "position_id": e.get("position_id"),
            "sector": e.get("sector"),
        })
    out.sort(key=lambda r: (r["entry_date"], r["ticker"]))
    return out


def _is_stop(reason: str) -> bool:
    r = (reason or "").lower()
    return any(s in r for s in STOP_REASONS)


def replay(trades: list, cooldown_days: int) -> dict:
    """Which entries would a cooldown of N calendar days have blocked?

    Walks the book in entry-date order, so the decision at each entry
    uses only exits that had already happened — no lookahead.
    """
    last_stop: dict = {}          # ticker -> exit_date of its last stop
    kept, blocked = [], []

    for t in trades:
        prev = last_stop.get(t["ticker"])
        if prev is not None and (t["entry_date"] - prev).days <= cooldown_days:
            blocked.append({**t, "blocked_by_exit_on": prev.isoformat(),
                            "gap_days": (t["entry_date"] - prev).days})
        else:
            kept.append(t)
        # the exit arms the cooldown regardless of whether the entry was
        # taken, because in production the stop still fired
        if _is_stop(t["exit_reason"]):
            if prev is None or t["exit_date"] > prev:
                last_stop[t["ticker"]] = t["exit_date"]

    def _agg(rows):
        if not rows:
            return {"n": 0, "sum_pp": 0.0, "mean_pct": None, "win_rate": None}
        p = [r["pnl_pct"] for r in rows]
        w = sum(1 for x in p if x > 0)
        return {"n": len(rows), "sum_pp": round(sum(p), 2),
                "mean_pct": round(sum(p) / len(p), 4),
                "win_rate": round(100.0 * w / len(p), 1)}

    all_a, kept_a, blk_a = _agg(trades), _agg(kept), _agg(blocked)
    return {
        "cooldown_days": cooldown_days,
        "all": all_a, "kept": kept_a, "blocked": blk_a,
        "pnl_delta_pp": round(kept_a["sum_pp"] - all_a["sum_pp"], 2),
        "entry_date_units_kept": len({r["entry_date"] for r in kept}),
        "blocked_detail": sorted(blocked,
                                 key=lambda r: r["pnl_pct"])[:25],
    }


def effective_dates(trades: list) -> dict:
    return {
        "n_trades": len(trades),
        "n_entry_dates": len({t["entry_date"] for t in trades}),
        "n_exit_dates": len({t["exit_date"] for t in trades}),
        "n_tickers": len({t["ticker"] for t in trades}),
    }


def run(root: Path, market: str) -> dict:
    trades = load_closed(root, market)
    if not trades:
        return {"schema_version": SCHEMA_VERSION, "market": market,
                "error": "no closed trades"}
    sweeps = [replay(trades, n) for n in COOLDOWN_GRID]
    base = effective_dates(trades)
    return {
        "schema_version": SCHEMA_VERSION,
        "market": market,
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds"),
        "production_authority": False,
        "baseline": base,
        "grid": list(COOLDOWN_GRID),
        "sweeps": sweeps,
        "governance": {
            "changes_production": False,
            "evidence_tier": "COUNTERFACTUAL",
            "in_sample": True,
            "caveat": (
                "Evaluated on the same %d trades across %d entry dates that "
                "motivated it. Removing a trade is not the same as earning "
                "what replaced it - the delta reported is 'what would not "
                "have happened', which is a strictly smaller claim. Not "
                "evidence of forward improvement until it survives dates it "
                "was not designed against."
                % (base["n_trades"], base["n_entry_dates"])),
        },
    }


def write(root: Path, market: str, payload: dict) -> Path:
    p = (Path(root) / "reports" / "research" / "r3"
         / ("reentry_cooldown_%s.json" % market))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return p
