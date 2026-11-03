"""Production step · USA universe selection + risk alerts for the excluded.

CEO 2026-11-03 · WHY THIS RUNS AFTER SCORING, NOT BEFORE
--------------------------------------------------------
The obvious place for a universe selector is upstream: shortlist the
names, then score only those, and the pipeline gets cheaper. That design
cannot work here, and the reason is worth stating because it reverses the
original motivation.

Measured on 2026-11-03, USA produced 18 actionable calls (12 BUY, 6 SELL).
The 248-slot shortlist retained 100% of the BUYs and 50% of the SELLs, and
at top_50 it retained NONE of them. Every name a momentum-ranked shortlist
drops is a SELL, because a SELL candidate is by construction a weak name.
The approved mitigation is a separately visible risk-alert path for
excluded names carrying SELL evidence - and an alert can only exist if the
excluded name was SCORED. Shortlist before scoring and the alerts are
empty by construction: the pipeline would be blind to exactly the signals
the mitigation exists to catch, while reporting zero misses.

So R2 continues to score the FULL eligible universe, unchanged, and this
step applies the selection afterwards as an auditable priority decision.
That also satisfies the standing instruction to preserve full
eligible-universe scoring and evidence calculations.

CONSEQUENCE, STATED PLAINLY: this buys no runtime. The universe
measurement already showed capacity was never the constraint - USA scored
516 of 516 at full size and the selection pass itself costs 0.05-0.13s -
so there was no runtime to buy.

WHAT IT GUARANTEES
------------------
- USA only. India is refused by configuration AND by an explicit market
  check, because `preserve_existing_universe` alone is a config away from
  being wrong.
- The selected universe is the UNION of 248 ranked discretionary slots
  and every open position, deduplicated on normalised ticker identity.
  248 is a count of ranked slots, never of the total.
- Nothing is written that any downstream consumer treats as the scoring
  universe. The audit is evidence, not an input to R2.
- The historical registry and the PIE research population are not read,
  not filtered and not touched.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402

from backend.universe import risk_alerts as _ra  # noqa: E402
from backend.universe import top_selection as _ts  # noqa: E402

#: Markets this step is permitted to act on. India is absent deliberately:
#: the standing instruction is that its universe and selection behaviour do
#: not change, and a config flag is a weaker guarantee than a refusal.
ALLOWED_MARKETS = ("usa",)

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_NO_INPUT = 3

STATE_APPLIED = "APPLIED"
STATE_DISABLED = "DISABLED"
STATE_REFUSED_MARKET = "REFUSED_MARKET"
STATE_NO_SNAPSHOT = "NO_SNAPSHOT"


def snapshot_path(root: Path, market: str, asof: str) -> Path:
    return Path(root) / "features" / str(market).lower() / ("%s.parquet"
                                                            % str(asof)[:10])


def reports_dir(root: Path, market: str) -> Path:
    return Path(root) / ("usa/reports" if str(market).lower() == "usa"
                         else "reports")


def result_path(root: Path, market: str) -> Path:
    return (Path(root) / "reports" / "universe"
            / ("selection_applied_%s.json" % str(market).lower()))


def load_snapshot(root: Path, market: str, asof: str):
    """Today's feature snapshot · the selector's only scoring input.

    A snapshot for another date is not today's evidence, so no fallback to
    the most recent file: the step reports NO_SNAPSHOT instead. Silently
    selecting on yesterday's features is the freshness-theatre failure
    this repository has already paid for.
    """
    p = snapshot_path(root, market, asof)
    if not p.exists():
        return None, p
    try:
        return pd.read_parquet(p), p
    except Exception:
        return None, p


def load_recommendations(root: Path, market: str) -> list:
    p = reports_dir(root, market) / "recommendations.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    return d.get("recommendations") or []


def run(root: Path, market: str, asof: Optional[str] = None,
        write: bool = True) -> dict:
    """Select, alert, and write the audit. Returns the result record."""
    root = Path(root)
    mkt = str(market).lower()
    asof = str(asof or date.today().isoformat())[:10]
    started = time.perf_counter()

    base = {
        "engine": "aegis.universe.selection_step.v1",
        "schema_version": "1.0.0",
        "market": mkt,
        "asof": asof,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    if mkt not in ALLOWED_MARKETS:
        return {**base, "state": STATE_REFUSED_MARKET, "exit": EXIT_REFUSED,
                "reason": ("this step runs for %s only · %s's universe and "
                           "selection behaviour are unchanged by instruction"
                           % ("/".join(ALLOWED_MARKETS), mkt))}

    cfg = _ts.load_config(root, mkt)
    if not cfg.get("universe_selection_enabled"):
        return {**base, "state": STATE_DISABLED, "exit": EXIT_OK,
                "reason": "universe_selection_enabled is false for %s" % mkt,
                "config": cfg}

    snap, sp = load_snapshot(root, mkt, asof)
    if snap is None or snap.empty:
        return {**base, "state": STATE_NO_SNAPSHOT, "exit": EXIT_NO_INPUT,
                "reason": "no feature snapshot for %s at %s" % (mkt, asof),
                "snapshot_path": str(sp)}

    sel, audit = _ts.select(root, mkt, snap, asof, cfg)
    select_s = time.perf_counter() - started

    kept_rank = sum(1 for e in audit["selected_evidence"]
                    if e.get("kept_because") == _ts.KEEP_RANK)
    kept_open = sum(1 for e in audit["selected_evidence"]
                    if e.get("kept_because") == _ts.KEEP_OPEN_POSITION)
    selected = list(audit["selected_tickers"])
    # Deterministic dedup on normalised identity. `select` already returns
    # one row per ticker, so this is a guard against a future caller
    # concatenating two sources, not a fix for a known duplicate.
    seen, union = set(), []
    for t in selected:
        b = _ts.bare_ticker(t)
        if b not in seen:
            seen.add(b)
            union.append(t)

    recs = load_recommendations(root, mkt)
    coverage = _ra.coverage(recs, union)
    alerts = _ra.build(root, mkt, recommendations=recs,
                       selected_tickers=union, asof=asof,
                       eligible_tickers=union)

    out = {
        **base,
        "state": STATE_APPLIED,
        "exit": EXIT_OK,
        "config": cfg,
        "target_ranked_slots": _ts.effective_top_n(cfg),
        "counts": {
            "snapshot": int(len(snap)),
            "eligible": int(audit["eligible"]),
            "ranked": kept_rank,
            "open_positions": kept_open,
            "selected_union": len(union),
            "excluded": int(audit["excluded"]),
        },
        "exclusion_reasons": audit["exclusion_reasons"],
        "coverage": coverage,
        "risk_alerts": {
            "n_alerts": alerts["n_alerts"],
            "n_critical": alerts["n_critical"],
            "tickers": [a["ticker"] for a in alerts["alerts"]],
            "known_residual": alerts["known_residual"]["tickers"],
        },
        "abstention_counts": audit.get("abstention_counts") or {},
        "sector_distribution": audit.get("sector_distribution") or {},
        "data_completeness_mean": audit.get("data_completeness_mean"),
        "selected_tickers": union,
        "runtime_s": {"selection": round(select_s, 4),
                      "total": round(time.perf_counter() - started, 4)},
        "note": ("Advisory priority decision. R2 scored the FULL eligible "
                 "universe and this step does not filter its input; see the "
                 "module docstring for why selecting before scoring would "
                 "empty the risk-alert path."),
    }

    if write:
        _ts.write_audit(root, mkt, asof, audit)
        _ra.write(root, mkt, alerts)
        p = result_path(root, mkt)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        out["written_to"] = str(p)
    return out


def _show(r: dict) -> None:
    print("  [universe] %-6s %s" % (r["market"], r["state"]))
    if r["state"] != STATE_APPLIED:
        print("             %s" % r.get("reason"))
        return
    c = r["counts"]
    print("             snapshot=%d eligible=%d -> selected=%d "
          "(ranked %d + held %d)  target_ranked_slots=%s"
          % (c["snapshot"], c["eligible"], c["selected_union"], c["ranked"],
             c["open_positions"], r["target_ranked_slots"]))
    print("             exclusions: %s" % (r["exclusion_reasons"] or {}))
    cov = r["coverage"]
    for fam in ("BUY", "SELL", "ALL_ACTIONABLE"):
        f = cov.get(fam) or {}
        print("             coverage %-14s %s/%s = %s%%  missed=%s"
              % (fam, f.get("covered"), f.get("n"), f.get("coverage_pct"),
                 f.get("missed", "-")))
    ra = r["risk_alerts"]
    print("             risk alerts: %d (%d CRITICAL) %s"
          % (ra["n_alerts"], ra["n_critical"], ra["tickers"]))
    print("             runtime: selection %.3fs total %.3fs"
          % (r["runtime_s"]["selection"], r["runtime_s"]["total"]))
    print("             written: %s" % r.get("written_to"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="usa")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--root", default=str(_ROOT))
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when the step could not be applied")
    a = ap.parse_args(argv)
    r = run(Path(a.root), a.market, a.asof)
    _show(r)
    if a.strict and r["state"] not in (STATE_APPLIED, STATE_DISABLED):
        return int(r["exit"])
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
