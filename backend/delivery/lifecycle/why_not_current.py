"""AEGIS · WHY ISN'T THIS STOCK IN CURRENT? · CEO 2026-09-08.

> "Reconcile the lifecycle. Candidate -> R2 eligibility -> Registry NEW ->
>  CURRENT. We need a single auditable answer to: 'Why isn't this stock in
>  CURRENT?'"

ONE ANSWER PER TICKER, FROM ONE PLACE
-------------------------------------
Until now that question had no single owner. The universe lived in
`configs/aegis_universes.yaml`, scoring in the model factory, the 15-name
truncation in `ensemble.json`, the floors in the recommendation engine,
eligibility in the registry, and investability in the lifecycle - so
answering it meant opening six artifacts and inferring the join. Six days
of "NEW 0" went unexplained for exactly that reason.

This walks every name in the scored universe through the real chain and
records the FIRST gate it fails. Every ticker gets exactly one verdict:

    L0_not_scored          no model output for it at all
    L1_truncated           scored, but discarded by ensemble.json's
                           head(10)+tail(5) - production never saw it
    L2_hold                scored and offered, engine said HOLD
    L3_disagreement        models conflicted, collapsed to HOLD
    L4_confidence          below the published confidence floor
    L5_regime              below the regime-adjusted floor
    L6_not_buy             a SELL-family action, correctly not bought
    L7_eligible_no_registry  cleared every gate but the registry has no
                           entry · THIS IS A LIFECYCLE BUG, not a decision
    L8_registry_closed     registry holds it, already closed
    L9_stop_breached       held, but trading below its stop -> EXIT HISTORY
    L10_in_current         investable now · it IS in CURRENT

L7 is the row that matters most. Everything else is the system deciding
something; L7 is the system LOSING something, and it is the only verdict
here that indicates a defect rather than a judgement.

DOWNSTREAM-ONLY
---------------
Reads the shadow evidence, the registry and the canonical lifecycle
dataset. Writes one report. It opens nothing, closes nothing, changes no
threshold and cannot alter what is in CURRENT.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.lifecycle.why_not_current.v1"

VERDICTS = [
    ("L0_not_scored", "no model output for this ticker"),
    ("L1_truncated", "scored but DISCARDED by the ensemble top_10+bottom_5 "
                     "truncation · production never saw it"),
    ("L2_hold", "engine returned HOLD"),
    ("L3_disagreement", "models disagreed · collapsed to HOLD"),
    ("L4_confidence", "below the published confidence floor"),
    ("L5_regime", "below the regime-adjusted confidence floor"),
    ("L6_not_buy", "SELL-family action · correctly not bought"),
    ("L7_eligible_no_registry", "cleared every gate but has NO registry "
                                "entry · LIFECYCLE DEFECT"),
    ("L8_registry_closed", "registry entry exists and is closed"),
    ("L9_stop_breached", "held but below its stop · moved to EXIT HISTORY"),
    ("L10_in_current", "investable now · present in CURRENT"),
]
VERDICT_TEXT = dict(VERDICTS)
DEFECT_VERDICTS = {"L7_eligible_no_registry"}


def _bare(t) -> str:
    """India carries a .NS suffix in feature/model space and bare tickers
    in registry/lifecycle space. Joining them without normalising is how a
    reconciliation silently reports everything as missing."""
    return str(t or "").upper().split(".", 1)[0].strip()


def compute(root: Path, market: str) -> dict:
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    from backend.research.shadow import full_universe_shadow as fus

    m = market.lower()
    shadow = fus.load(root, m) or {}
    life = lc.load(root, m) or {}

    in_current = {_bare(r["ticker"]): r for r in (life.get("current") or [])}
    breached = {_bare(e["ticker"]): e for e in (life.get("exits") or [])
                if e.get("source") == "lifecycle:stop-breach"}
    # ONLY a close dated TODAY answers "why isn't it in CURRENT today".
    # Matching the whole 90-day exit window instead swallowed 489 of 516
    # USA names into L8 and hid every real verdict behind an exit that
    # happened two months ago. A stale terminal state is not a reason.
    _asof = str(life.get("asof") or "")[:10]
    closed = {_bare(e["ticker"]) for e in (life.get("exits") or [])
              if str(e.get("source", "")).startswith("registry:")
              and str(e.get("exit_date") or "")[:10] == _asof}

    rows, tally = [], {}

    def _add(ticker, verdict, detail=None, extra=None):
        tally[verdict] = tally.get(verdict, 0) + 1
        rec = {"ticker": ticker, "verdict": verdict,
               "meaning": VERDICT_TEXT[verdict],
               "is_defect": verdict in DEFECT_VERDICTS}
        if detail:
            rec["detail"] = detail
        if extra:
            rec.update(extra)
        rows.append(rec)

    for s in (shadow.get("rows") or []):
        t = _bare(s.get("ticker"))
        ev = {"action": s.get("action"),
              "ensemble_score": s.get("ensemble_score"),
              "calibrated_confidence": s.get("calibrated_confidence"),
              "regime_adjusted_confidence": s.get("regime_adjusted_confidence")}

        # Terminal states first · being in CURRENT outranks every gate,
        # because the position already exists whatever today's score says.
        if t in in_current:
            _add(t, "L10_in_current",
                 "engine=%s · action=%s" % (in_current[t].get("engine"),
                                            in_current[t].get("action")), ev)
            continue
        if t in breached:
            _add(t, "L9_stop_breached",
                 "P&L %s%%" % breached[t].get("realized_pnl_pct"), ev)
            continue
        if t in closed:
            _add(t, "L8_registry_closed", "closed today", ev)
            continue

        reason = str(s.get("reason") or "")
        if s.get("would_be_new"):
            # Cleared every published gate and is held nowhere. If
            # production also SAW it, the registry should have an entry.
            if s.get("in_persisted_15"):
                _add(t, "L7_eligible_no_registry",
                     "cleared all floors and was inside the 15 production "
                     "sees · no registry entry exists", ev)
            else:
                _add(t, "L1_truncated",
                     "would have cleared every floor · never offered to the "
                     "engine because ensemble.json keeps only 15 rows", ev)
            continue
        if reason.startswith("DISAGREEMENT"):
            _add(t, "L3_disagreement", None, ev)
        elif reason.startswith("CONFIDENCE"):
            _add(t, "L4_confidence", None, ev)
        elif reason.startswith("REGIME"):
            _add(t, "L5_regime", None, ev)
        elif reason.startswith("NOT A BUY"):
            _add(t, "L6_not_buy", None, ev)
        else:
            _add(t, "L2_hold", None, ev)

    # Anything in CURRENT that the scored universe never mentioned still
    # needs a row · a reconciliation with a blind spot is not one.
    seen = {r["ticker"] for r in rows}
    for t, r in in_current.items():
        if t not in seen:
            _add(t, "L10_in_current",
                 "engine=%s · not in today's scored universe"
                 % r.get("engine"), None)

    defects = [r for r in rows if r["is_defect"]]

    # CEO 2026-09-08 · "Every NEW = 0 must show the exact bottleneck /
    # rejection reason." One line the workbook can render verbatim, so the
    # sheet never states a bare count again.
    t = {k: tally.get(k, 0) for k, _ in VERDICTS}
    gates = [("model disagreement", t["L3_disagreement"]),
             ("HOLD", t["L2_hold"]),
             ("regime floor", t["L5_regime"]),
             ("confidence floor", t["L4_confidence"]),
             ("SELL-family", t["L6_not_buy"])]
    top = max(gates, key=lambda kv: kv[1])
    n_scored = len(shadow.get("rows") or [])
    # The headline must state the ACTUAL count · it read "WHY NEW=0" on a
    # day India produced NEW 1 (JIOFIN), which is a false statement on the
    # investor sheet.
    n_new = sum(1 for r in (life.get("current") or [])
                if str(r.get("action")) == "NEW")
    _lead = (f"NEW={n_new} · " if n_new
             else "WHY NEW=0 · ")
    headline = (
        "%s%d scored · %d already in CURRENT · biggest blocker: "
        "%s (%d) · lost to the 15-name ensemble truncation: %d · "
        "lifecycle defects: %d"
        % (_lead, n_scored, t["L10_in_current"], top[0], top[1],
           t["L1_truncated"], len(defects)))

    return {
        "headline": headline,
        "schema_version": SCHEMA_VERSION,
        "market": m,
        "asof": life.get("asof") or shadow.get("asof") or "",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_reconciled": len(rows),
        "tally": {k: tally.get(k, 0) for k, _ in VERDICTS},
        "n_defects": len(defects),
        "defects": defects,
        "truncation_cost": [r for r in rows if r["verdict"] == "L1_truncated"],
        "rows": sorted(rows, key=lambda r: (r["verdict"], r["ticker"])),
        "legend": VERDICT_TEXT,
    }


def artifact_path(root: Path, market: str) -> Path:
    return (root / "reports" / "context"
            / f"why_not_current_{market.lower()}.json")


def emit(root: Path, rep: dict) -> Path:
    p = artifact_path(root, rep["market"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = artifact_path(root, market)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def explain(root: Path, market: str, ticker: str) -> Optional[dict]:
    """The single auditable answer for one name."""
    d = load(root, market)
    if not d:
        return None
    t = _bare(ticker)
    for r in d.get("rows") or []:
        if r["ticker"] == t:
            return r
    return None


def summary_line(rep: dict) -> str:
    t = rep["tally"]
    return (f"why_not_current:{rep['market']} · reconciled {rep['n_reconciled']} "
            f"· CURRENT {t['L10_in_current']} · truncated {t['L1_truncated']} "
            f"· disagreement {t['L3_disagreement']} · confidence "
            f"{t['L4_confidence']} · regime {t['L5_regime']} · DEFECTS "
            f"{rep['n_defects']}")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="AEGIS · why isn't this stock in CURRENT?")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--ticker", default=None,
                    help="explain one ticker instead of the whole market")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = compute(root, m)
        p = emit(root, rep)
        if a.ticker:
            r = explain(root, m, a.ticker)
            print(json.dumps(r, indent=2, default=str) if r
                  else f"{a.ticker}: not in {m}'s reconciled universe")
            continue
        print(summary_line(rep))
        print(f"    -> {p.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
