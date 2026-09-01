"""Dynamic-exit bridge · CEO 2026-09-01.

Wires together already-existing components that were coded but never
connected to the daily production path:

    backend/risk/dynamic_risk_v2                (produces per-position stops)
              +
    backend/portfolio/lifecycle_state_machine   (evaluate_position · stop/target/horizon)
              →
    backend/research/opportunity_registry.close (canonical Registry close)

For every Registry ACTIVE R2 position: pull today's dynamic stop from
`reports/context/dynamic_risk_{market}.json` (writer: dynamic_risk_v2)
· pull T1/T2 from the recommendations JSON's entry_zone · pull horizon
from recommendation's suggested_holding_period_days · call the coded
evaluate_position · if it returns a lifecycle decision (EXIT_STOP /
EXIT_TARGET / EXIT_HORIZON), call oreg.close() with the decision's
exact event and reason.

Modes:
    --enforce      · actually calls oreg.close() when engine says exit
    --audit-only   · only reports what the engine WOULD have decided
                     (default · non-destructive · used for today's build)

Does NOT modify:
    · backend/portfolio/*  (uses evaluate_position READ-ONLY)
    · backend/risk/*       (consumes dynamic_risk_v2 output READ-ONLY)
    · backend/recommendation/*
    · Registry decision logic
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def _load_dynamic_stops(root: Path, market: str) -> dict[str, dict]:
    """Return {opportunity_id: {new_stop, stop_type, reason, current_price}}."""
    p = root / "reports" / "context" / f"dynamic_risk_{market.lower()}.json"
    out: dict[str, dict] = {}
    if not p.exists(): return out
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return out
    for u in (data.get("updates") or []):
        pid = u.get("opportunity_id")
        if pid:
            out[pid] = u
    return out


def _load_rec_lookup(root: Path, market: str) -> dict[str, dict]:
    """Return {ticker: {stop_loss, target_1, target_2, horizon_days, current_price}}."""
    if market.lower() == "usa":
        p = root / "usa" / "reports" / "recommendations.json"
    else:
        p = root / "reports" / "recommendations.json"
    out: dict[str, dict] = {}
    if not p.exists(): return out
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return out
    for r in (data.get("recommendations") or []):
        tk = str(r.get("ticker", "")).split(".", 1)[0].upper()
        if not tk: continue
        ez = r.get("entry_zone") or {}
        out[tk] = {
            "stop_loss":    ez.get("stop_loss"),
            "target_1":     ez.get("target_1"),
            "target_2":     ez.get("target_2"),
            "current_price": ez.get("current_price"),
            "horizon_days": r.get("suggested_holding_period_days") or 60,
        }
    return out


def _close_on_or_before(root: Path, ticker: str, market: str, target_date: str):
    import pandas as pd
    dir_ = "usa/data/raw/us" if market.lower() == "usa" else "data/raw/india"
    ext = "" if market.lower() == "usa" else ".NS"
    for p in (root / dir_ / f"{ticker.upper()}{ext}_D1.parquet",
                root / dir_ / f"{ticker.upper()}_D1.parquet"):
        if not p.exists(): continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns: continue
            idx = pd.to_datetime(df.index).strftime("%Y-%m-%d")
            df = df.copy(); df.index = idx
            sub = df.loc[df.index <= target_date]
            if sub.empty: continue
            return float(sub.iloc[-1]["close"])
        except Exception:
            continue
    return None


def _first_stop_cross_date(root: Path, ticker: str, market: str,
                              entry_date: str, asof: str, stop_price: float):
    """Find the first trading day (>= entry_date) where close <= stop_price."""
    import pandas as pd
    dir_ = "usa/data/raw/us" if market.lower() == "usa" else "data/raw/india"
    ext = "" if market.lower() == "usa" else ".NS"
    for p in (root / dir_ / f"{ticker.upper()}{ext}_D1.parquet",
                root / dir_ / f"{ticker.upper()}_D1.parquet"):
        if not p.exists(): continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns: continue
            idx = pd.to_datetime(df.index).strftime("%Y-%m-%d")
            df = df.copy(); df.index = idx
            sub = df.loc[(df.index >= entry_date) & (df.index <= asof)]
            for d, c in sub["close"].items():
                if float(c) <= stop_price:
                    return d
            return None
        except Exception:
            continue
    return None


def apply_market(root: Path, market: str, asof: str, enforce: bool) -> dict:
    from backend.research import opportunity_registry as oreg
    from backend.delivery.canonical.retirement import retired_runners
    retired = retired_runners(root)

    dynamic_stops = _load_dynamic_stops(root, market)
    rec_lookup = _load_rec_lookup(root, market)

    reg = oreg.load_all(root)
    decisions = []
    enforced = 0
    audit_only = 0

    for _reg_key, opps in reg.items():
        for opp in opps:
            if opp.market.lower() != market.lower(): continue
            if opp.runner in retired: continue      # skip retired runners
            if opp.status != "ACTIVE": continue
            pid = opp.opportunity_id      # canonical PID · not the reg dict key
            tk = str(opp.ticker or "").split(".", 1)[0].upper()

            # Determine stop_price · prefer dynamic_risk_v2 · fall back to rec
            stop_price = None
            stop_source = "none"
            if pid in dynamic_stops:
                stop_price = dynamic_stops[pid].get("new_stop")
                stop_source = f"dynamic_risk_v2:{dynamic_stops[pid].get('stop_type')}"
            if stop_price is None and tk in rec_lookup:
                stop_price = rec_lookup[tk].get("stop_loss")
                stop_source = "rec.entry_zone.stop_loss"
            # Absolute fallback: 6% of first-day close
            if stop_price is None:
                fc = _close_on_or_before(root, tk, market, opp.created_date or asof)
                if fc:
                    stop_price = round(fc * 0.94, 4)
                    stop_source = "fallback:entry×0.94"

            t1_price = rec_lookup.get(tk, {}).get("target_1")
            t2_price = rec_lookup.get(tk, {}).get("target_2")
            horizon_days = rec_lookup.get(tk, {}).get("horizon_days") or 60
            current_price = _close_on_or_before(root, tk, market, asof)

            if current_price is None:
                decisions.append({
                    "opportunity_id": pid, "ticker": tk, "runner": opp.runner,
                    "action": "SKIP", "reason": "no current price",
                })
                continue

            # Directly evaluate stop / target / horizon (mirrors
            # backend/portfolio/lifecycle_state_machine.evaluate_position
            # · we don't call it because it also expects portfolio_ledger
            # state we don't maintain · but the LOGIC is the same and comes
            # from the same source of truth)
            entry_dt = opp.created_date
            try:
                days_held = (date.fromisoformat(asof) - date.fromisoformat(entry_dt)).days
            except Exception:
                days_held = 0

            event = None
            reason = None
            trigger_price = None
            trigger_date = None
            if stop_price is not None and current_price <= stop_price:
                event = "EXIT_STOP"
                reason = (f"stop-loss triggered at {current_price:.2f} · "
                            f"stop={stop_price:.2f} · source={stop_source}")
                trigger_price = current_price
                trigger_date = _first_stop_cross_date(root, tk, market,
                                                        entry_dt, asof, stop_price)
            elif t2_price is not None and current_price >= t2_price:
                event = "EXIT_TARGET"
                reason = f"T2 hit at {current_price:.2f} · T2={t2_price:.2f}"
                trigger_price = current_price
                trigger_date = asof
            elif t1_price is not None and current_price >= t1_price:
                event = "EXIT_TARGET"
                reason = f"T1 hit at {current_price:.2f} · T1={t1_price:.2f}"
                trigger_price = current_price
                trigger_date = asof
            elif horizon_days > 0 and days_held >= horizon_days:
                event = "EXIT_HORIZON"
                reason = f"held {days_held}d ≥ horizon {horizon_days}d"
                trigger_price = current_price
                trigger_date = asof

            # CEO 2026-09-01 final closure invariant: enforcement is ONLY
            # authorized when the stop comes from the AUTHORITATIVE dynamic
            # engine (dynamic_risk_v2). If we fell back to rec.entry_zone
            # static or the 6% fallback, we do NOT fire a close · that would
            # be substituting a hardcoded stop where the dynamic engine
            # had no data. Instead we emit an audit-only decision + record
            # the reason so the operator can see the coverage gap.
            _authoritative = stop_source.startswith("dynamic_risk_v2:")
            _would_enforce = enforce and _authoritative

            if event is None:
                # No trigger · still ACTIVE · record the HOLD verdict so the
                # workbook can display the dynamic stop level for every
                # position (transparency · not just for exits).
                decisions.append({
                    "opportunity_id": pid,
                    "ticker": tk,
                    "runner": opp.runner,
                    "entry_date": entry_dt,
                    "current_price": current_price,
                    "stop_price": stop_price,
                    "stop_source": stop_source,
                    "authoritative_dynamic": _authoritative,
                    "t1_price": t1_price,
                    "t2_price": t2_price,
                    "horizon_days": horizon_days,
                    "days_held": days_held,
                    "event": "HOLD",
                    "reason": "no exit trigger reached · position remains ACTIVE",
                    "trigger_date": None,
                    "asof": asof,
                    "action": "AUDIT_ONLY",
                })
                continue

            decisions.append({
                "opportunity_id": pid,
                "ticker": tk,
                "runner": opp.runner,
                "entry_date": entry_dt,
                "entry_price_approx": _close_on_or_before(root, tk, market, entry_dt),
                "current_price": current_price,
                "stop_price": stop_price,
                "stop_source": stop_source,
                "authoritative_dynamic": _authoritative,
                "t1_price": t1_price,
                "t2_price": t2_price,
                "horizon_days": horizon_days,
                "days_held": days_held,
                "event": event,
                "reason": reason,
                "trigger_date": trigger_date,
                "asof": asof,
                "action": (
                    "ENFORCED" if _would_enforce
                    else ("AUDIT_ONLY_NON_AUTHORITATIVE" if enforce
                            else "AUDIT_ONLY")
                ),
            })
            if _would_enforce:
                # Persist to Registry via existing public API · idempotent
                # Use asof as closed_date · include trigger_date in reason
                # so backdating is documented, not applied to Registry.
                close_reason = (
                    f"{event} · trigger crossed {trigger_date} · "
                    f"stop_source={stop_source} · enforced_on={asof}"
                )
                oreg.close(root, pid, asof, reason=close_reason)
                enforced += 1
            elif enforce:
                # Enforce mode was requested but this decision falls back
                # to non-authoritative stop · treat as audit-only
                audit_only += 1
            else:
                audit_only += 1

    result = {
        "engine": "apply_dynamic_exits.bridge.v1",
        "market": market.lower(),
        "asof": asof,
        "mode": "enforce" if enforce else "audit_only",
        "n_decisions": len(decisions),
        "n_enforced": enforced,
        "n_audit_only": audit_only,
        "n_dynamic_stops_available": len(dynamic_stops),
        "n_rec_lookup": len(rec_lookup),
        "decisions": decisions,
        "notes": [
            "This bridge WIRES existing components · it does not add new strategy.",
            "Stops come from dynamic_risk_v2 (ATR/vol-scaled/trailing) when available.",
            "Falls back to rec.entry_zone.stop_loss (from investor_actionable engine).",
            "Fallback of last resort is entry × 0.94 (same 6% baseline the coded engine uses).",
            "ENFORCEMENT INVARIANT (CEO 2026-09-01 final closure): oreg.close()",
            "  is called ONLY when stop_source is dynamic_risk_v2:* (authoritative).",
            "  If we fell back to rec.entry_zone or the 6% fallback, decision is",
            "  emitted as AUDIT_ONLY_NON_AUTHORITATIVE · Registry is NOT mutated.",
            "  This prevents silent substitution of a hardcoded stop for markets",
            "  where the dynamic engine has no per-position ATR data.",
        ],
    }
    out_p = root / "reports" / "audit" / f"dynamic_exit_decisions_{market.lower()}_{asof}.json"
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str),
                      encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--enforce", action="store_true",
                     help="Actually close positions via oreg.close (default: audit-only)")
    args = ap.parse_args()
    for m in (["india", "usa"] if args.market == "both" else [args.market]):
        rep = apply_market(_ROOT, m, args.asof, args.enforce)
        print(f"[dynamic_exits:{m}] mode={rep['mode']} · decisions={rep['n_decisions']} · "
              f"enforced={rep['n_enforced']} · audit_only={rep['n_audit_only']}")
        for d in rep["decisions"][:10]:
            _line = (f"  {d['ticker']:12s} {d['event']:14s} "
                       f"curr={d['current_price']:8.2f} stop={d['stop_price']} "
                       f"src={d['stop_source']} trigger_date={d.get('trigger_date')}")
            print(_line.encode("ascii", errors="replace").decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
