"""02_Today_Momentum funnel diagnostic
Sprint A · CEO 2026-09-03 · same rigor as r2_signal_funnel.py but pointed
at the momentum ledger that feeds sheet 02.

Answers: "why did 02_Today_Momentum scan only N tickers when the universe
has M?" · surfaces the per-stage drop for both markets.

Reads:
  reports/research/multi_layer/momentum_ledger_{market}_{asof}.json

Emits:
  reports/research/momentum_funnel/{market}/{asof}.json
  reports/research/momentum_funnel/{market}/latest.json
  reports/research/momentum_funnel/{market}/summary.md
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# CEO 2026-09-08 · M4 READ THE WRONG FIELD.
#
# It read `n_universe_scanned`, which the ledger itself labels
# `n_universe_scanned_DEPRECATED_MEANING: "in-universe candidate count ·
# NOT the number of tickers scanned"`. So a day where the producer
# evaluated all 230 tickers and found 4 candidates - all of them outside
# the declared NIFTY-50 production universe - was reported as
# "CRITICAL · only 0 of 230 raw universe tickers actually scanned",
# sending the investigation after a scan failure that never happened.
#
# The producer publishes its own truthful funnel; use it.
MOMENTUM_STAGES = [
    "M1_universe_raw",              # n_universe_scanned_raw
    "M2_production_universe",        # n_production_universe
    "M3_evaluated",                  # producer_funnel.n_evaluated · TRUTH
    "M4_producer_candidates",        # producer_funnel.n_candidates
    "M5_candidates_in_universe",     # n_candidates_source (after universe filter)
    "M6_classified",                 # n_candidates_classified
    "M7_accepted",                   # by_terminal_state.ACCEPTED
    "M8_watch",                      # by_terminal_state.WATCH
]


def _load_ledger(root: Path, market: str, asof: str) -> dict:
    p = root / "reports" / "research" / "multi_layer" / f"momentum_ledger_{market}_{asof}.json"
    if not p.exists(): return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def compute_funnel(root: Path, market: str, asof: str) -> dict:
    d = _load_ledger(root, market, asof)
    if not d:
        return {"market": market, "asof": asof, "error": "momentum ledger missing"}
    raw = int(d.get("n_universe_scanned_raw", 0) or 0)
    prod = int(d.get("n_production_universe") or raw or 0)
    dropped = int(d.get("n_out_of_universe_dropped", 0) or 0)
    scanned = int(d.get("n_universe_scanned", 0) or 0)
    candidates = int(d.get("n_candidates_source", 0) or 0)
    classified = int(d.get("n_candidates_classified", 0) or 0)
    bts = d.get("by_terminal_state", {}) or {}
    n_accepted = int(bts.get("ACCEPTED", 0) or 0)
    n_watch = int(bts.get("WATCH", 0) or 0)

    pf = d.get("producer_funnel") or {}
    n_eval = int(pf.get("n_evaluated") or 0)
    n_prod_cand = int(pf.get("n_candidates") or 0)

    counts = {
        "M1_universe_raw": raw,
        "M2_production_universe": prod,
        "M3_evaluated": n_eval,
        "M4_producer_candidates": n_prod_cand,
        "M5_candidates_in_universe": candidates,
        "M6_classified": classified,
        "M7_accepted": n_accepted,
        "M8_watch": n_watch,
    }

    # Bottleneck · biggest stage-to-stage drop
    prev_k = prev_v = None; worst_drop = 0; worst = ""
    for k in MOMENTUM_STAGES:
        v = counts.get(k, 0)
        if prev_v is not None and isinstance(v, int):
            drop = max(0, prev_v - v)
            if drop > worst_drop:
                worst_drop = drop; worst = f"{prev_k}→{k}"
        prev_k, prev_v = k, v

    # Diagnosis
    diag = []
    # A real evaluation failure · the producer did not look at the universe.
    if n_eval <= 5 and raw >= 50:
        diag.append(
            f"CRITICAL · producer evaluated only {n_eval} of {raw} tickers · "
            f"this is a genuine scan failure · check the momentum producer"
        )
    # NOT a failure · candidates were found and then filtered out by the
    # DECLARED production universe. Reported as its own line so it is never
    # mistaken for a scan failure again.
    elif n_prod_cand > 0 and candidates == 0:
        diag.append(
            f"UNIVERSE-BOUND · producer evaluated {n_eval} tickers and found "
            f"{n_prod_cand} candidate(s), but ALL fall outside the declared "
            f"production universe ({prod} names · configs/aegis_universes.yaml) "
            f"· 0 reach classification · this is the declared constraint "
            f"working, not a defect"
        )
    if n_accepted == 0 and n_watch == 0 and classified > 0:
        diag.append(
            f"WARN · {classified} classified but 0 ACCEPTED + 0 WATCH · "
            f"all rejected or NO_EVIDENCE · check score→terminal_state thresholds"
        )
    # Surface the DOMINANT rejection reason · USA loses 17 of 18 in-universe
    # candidates to R_QUALITY_UNAVAILABLE, which is a data-coverage defect
    # and was invisible while only stage counts were reported.
    _codes = d.get("by_reason_code") or {}
    if classified > 0 and _codes:
        _top, _n = max(_codes.items(), key=lambda kv: kv[1])
        if _n >= max(2, classified * 0.5):
            _kind = ("DATA" if "UNAVAILABLE" in _top or "MISSING" in _top
                     else "RULE")
            diag.append(
                f"{_kind} · {_n} of {classified} classified candidate(s) end in "
                f"{_top} · this single reason decides the day's momentum output"
            )
    if raw - prod > raw * 0.4:
        diag.append(
            f"INFO · raw({raw}) → production({prod}) drops {raw-prod} tickers via universe filter (expected)"
        )
    if worst_drop > 50 and worst != "M3_evaluated→M4_producer_candidates":
        diag.append(f"BOTTLENECK · biggest drop at {worst} · lost {worst_drop} tickers")
    if not diag:
        diag.append("OK · funnel counts look consistent")

    return {
        "market": market, "asof": asof,
        "stages": counts,
        "bottleneck": {"transition": worst, "drop": worst_drop},
        "diagnosis": diag,
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_ledger": str((root / "reports" / "research" / "multi_layer" /
                              f"momentum_ledger_{market}_{asof}.json").relative_to(root)),
    }


def _emit_md(root: Path, market: str, asof: str, payload: dict) -> Path:
    out_dir = root / "reports" / "research" / "momentum_funnel" / market
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Momentum Funnel · {market.upper()} · {asof}\n",
        "\n## Stage counts\n",
        "| Stage | Count | Δ vs prev |",
        "|---|---:|---:|",
    ]
    prev = None
    for k in MOMENTUM_STAGES:
        v = payload["stages"].get(k, 0)
        d = "" if prev is None else f"{v - prev:+d}"
        lines.append(f"| {k} | {v} | {d} |")
        prev = v
    lines.append(f"\n## Bottleneck\n\n**{payload['bottleneck']['transition']}** · "
                 f"lost {payload['bottleneck']['drop']} tickers\n")
    lines.append("\n## Diagnosis\n")
    for line in payload["diagnosis"]:
        lines.append(f"- {line}")
    lines.append("")
    p = out_dir / "summary.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
        # CEO 2026-09-08 · defaults to today so the daily pipeline can run
    # this as a step · the runner passes script_args verbatim and does
    # not inject --asof.
    ap.add_argument("--asof", default=date.today().isoformat(),
                    help="YYYY-MM-DD (default: today)")
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    payload = compute_funnel(root, args.market, args.asof)
    out_dir = root / "reports" / "research" / "momentum_funnel" / args.market
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.asof}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (out_dir / "latest.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    _emit_md(root, args.market, args.asof, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
