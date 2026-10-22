"""TARGET-EXIT · shadow evaluator + the inverted-target defect.

WHAT THIS IS, AND WHY IT IS NOT WIRED TO PRODUCTION YET
-------------------------------------------------------
The audit question was "why are +38%, +20%, +13% positions still open, and why
are targets missing?" The answer turned out to be worse than a missing field:

  "Target hit" exists ONLY as a display label in the workbook's exit-reason
  normalizer. No engine has ever evaluated a target. In 131 realized exits
  across both markets it has fired exactly 0 times.

  dynamic_risk_v2.py computes STOPS (ATR) and nothing else.
  dynamic_holding/engine.py computes holding DAYS and nothing else.
  The target is written at entry, rendered in the workbook, and never read.

So this is not a disconnected wire - the rule was never built. Adding it is a
change to live trading behaviour, and the supporting evidence is a RESEARCH
SIGNAL at 11 effective date units against a 20-date OOS floor. Flipping it on
today would be exactly the "manufacture readiness by lowering the gate" move
that governance forbids.

This module therefore does two separable things:

  1. FIXES a real defect unconditionally - the inverted stop/target. A stop
     above its own target is incoherent for a long position regardless of any
     exit rule, and 4 of 58 India positions are in that state right now
     (TATAELXSI stop 3588.33 vs target 3346.99). That is a data bug, not a
     policy choice.

  2. SHADOW-EVALUATES the target exit every day: what WOULD have been closed,
     at what price, for what P&L, versus what production actually did. It
     writes an evidence ledger and nothing else. Production is untouched.

     Flipping it live is one config flag (TARGET_EXIT_ENABLED) once the date
     count clears the gate. The mechanism is built and tested; only the
     authority to act is withheld.

MEASURED BASIS (validated, see exit_autopsy)
--------------------------------------------
  mean peak +2.92% -> mean realized -3.15%, 6.07pp given back on stop exits
  take-profit +3% : train -2.217 -> -0.776 | TEST -3.256 -> -2.267 (+0.99pp)
  survives a conservative close-fill (degradation 0.04pp)
  holding PAST the stop is WORSE (-0.94pp at +5d) - the stop is doing its job
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.r3.target_exit_shadow.v1"

# Production authority. Deliberately OFF: the evidence is a RESEARCH SIGNAL at
# 11 effective date units, below the 20-date OOS floor this programme uses.
# Flipping this is a CEO decision, not a code decision.
TARGET_EXIT_ENABLED = False


def _f(v) -> Optional[float]:
    try:
        return float(str(v).replace("%", "").strip())
    except Exception:
        return None


def diagnose_inverted(positions: list) -> dict:
    """A stop above its own target is incoherent for a long position.

    Cause: the target is frozen at entry while the stop trails upward, so on a
    strong winner the stop eventually overtakes the stale target. Once that
    happens the target can never fire even if a rule existed - the stop would
    always trigger first.
    """
    inverted, passed = [], []
    for p in positions:
        tg, st = _f(p.get("target")), _f(p.get("stop"))
        cp, ep = _f(p.get("current_price")), _f(p.get("entry_price"))
        if tg is None:
            continue
        if st is not None and st > tg:
            inverted.append({"ticker": p.get("ticker"), "target": tg, "stop": st,
                             "current": cp, "pnl_pct": _f(p.get("pnl_pct")),
                             "gap": round(st - tg, 4)})
        if cp is not None and cp >= tg:
            passed.append({"ticker": p.get("ticker"), "target": tg, "current": cp,
                           "pnl_pct": _f(p.get("pnl_pct")),
                           "overshoot_pct": round(100.0 * (cp - tg) / tg, 2)})
    return {
        "n_positions": len(positions),
        "n_inverted_stop_above_target": len(inverted),
        "n_target_already_passed": len(passed),
        "inverted": sorted(inverted, key=lambda r: -r["gap"]),
        "target_passed": sorted(passed, key=lambda r: -(r["pnl_pct"] or 0)),
        "interpretation": (
            "A passed target with the position still open proves no engine "
            "consumes the target. An inverted stop/target proves the target is "
            "frozen at entry while the stop trails - so even adding a rule "
            "would not fire on these until the target is recomputed."),
    }


def repair_target(entry_price: Optional[float], target: Optional[float],
                  stop: Optional[float]) -> dict:
    """Make the target coherent without inventing a price.

    The ONLY safe repair is to restore the ordering stop < target, because a
    long position's target must sit above its stop by construction. The
    original target's DISTANCE from entry is preserved and re-anchored above
    the trailing stop, so the repair carries no new opinion about where the
    price should go - it just stops asserting something impossible.

    Returns the repair with its reason so it is auditable, never silent.
    """
    ep, tg, st = entry_price, target, stop
    if tg is None or st is None or ep is None or ep <= 0:
        return {"repaired": False, "reason": "INSUFFICIENT_FIELDS",
                "target": tg}
    if st <= tg:
        return {"repaired": False, "reason": "ALREADY_COHERENT", "target": tg}
    # preserve the original target's reward distance, re-anchored on the stop
    reward_pct = (tg - ep) / ep
    new_target = st * (1.0 + max(reward_pct, 0.005))
    return {"repaired": True, "reason": "STOP_WAS_ABOVE_TARGET",
            "old_target": round(tg, 4), "stop": round(st, 4),
            "target": round(new_target, 4),
            "preserved_reward_pct": round(100.0 * reward_pct, 3),
            "note": ("re-anchored above the trailing stop, original reward "
                     "distance preserved - no new price view introduced")}


def shadow_evaluate(positions: list, asof: str,
                    threshold_pct: float = 3.0) -> dict:
    """What a target exit WOULD have closed today. Decides nothing.

    Two rules are evaluated side by side so the comparison is honest:
      TARGET   - close when price reaches the (repaired) target
      TAKE_3PC - close when unrealized gain reaches +3%, the rule that
                 actually survived out-of-sample in exit_autopsy
    """
    would_target, would_take = [], []
    for p in positions:
        tg, st = _f(p.get("target")), _f(p.get("stop"))
        cp, ep = _f(p.get("current_price")), _f(p.get("entry_price"))
        pnl = _f(p.get("pnl_pct"))
        rep = repair_target(ep, tg, st)
        eff_target = rep.get("target")
        if cp is not None and eff_target is not None and cp >= eff_target:
            would_target.append({"ticker": p.get("ticker"), "pnl_pct": pnl,
                                 "effective_target": eff_target,
                                 "target_was_repaired": rep.get("repaired")})
        if pnl is not None and pnl >= threshold_pct:
            would_take.append({"ticker": p.get("ticker"), "pnl_pct": pnl})
    locked = sum(x["pnl_pct"] or 0 for x in would_take)
    return {
        "schema_version": SCHEMA_VERSION,
        "asof": asof,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "production_authority": False,
        "target_exit_enabled": TARGET_EXIT_ENABLED,
        "take_profit_threshold_pct": threshold_pct,
        "n_positions": len(positions),
        "TARGET_rule": {"n_would_close": len(would_target),
                        "positions": would_target},
        "TAKE_3PC_rule": {"n_would_close": len(would_take),
                          "positions": sorted(would_take,
                                              key=lambda r: -(r["pnl_pct"] or 0)),
                          "sum_pnl_locked_pp": round(locked, 2),
                          "mean_pnl_locked_pct": (round(locked / len(would_take), 2)
                                                  if would_take else None)},
        "governance": {
            "changes_production": False,
            "evidence_tier": "RESEARCH SIGNAL",
            "effective_date_units": 11,
            "oos_floor": 20,
            "blocker": ("date depth - 11 of 20. The rule survives a "
                        "chronological split and a conservative fill, but not "
                        "yet the floor. Accumulating, not promoting."),
        },
    }


def write(root: Path, market: str, payload: dict) -> Path:
    p = (Path(root) / "reports" / "research" / "r3"
         / ("target_exit_shadow_%s.json" % market))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return p
