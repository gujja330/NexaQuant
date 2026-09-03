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
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


MOMENTUM_STAGES = [
    "M1_universe_raw",              # n_universe_scanned_raw
    "M2_production_universe",        # n_production_universe
    "M3_after_out_of_universe_drop", # M1 - n_out_of_universe_dropped
    "M4_actually_scanned",           # n_universe_scanned
    "M5_candidates_source",          # n_candidates_source
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

    counts = {
        "M1_universe_raw": raw,
        "M2_production_universe": prod,
        "M3_after_out_of_universe_drop": max(0, raw - dropped),
        "M4_actually_scanned": scanned,
        "M5_candidates_source": candidates,
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
    if scanned <= 5 and raw >= 50:
        diag.append(
            f"CRITICAL · only {scanned} of {raw} raw universe tickers actually scanned · "
            f"investigate momentum-engine filter chain between raw universe and scan pool"
        )
    if n_accepted == 0 and n_watch == 0 and classified > 0:
        diag.append(
            f"WARN · {classified} classified but 0 ACCEPTED + 0 WATCH · "
            f"all rejected or NO_EVIDENCE · check score→terminal_state thresholds"
        )
    if raw - prod > raw * 0.4:
        diag.append(
            f"INFO · raw({raw}) → production({prod}) drops {raw-prod} tickers via universe filter (expected)"
        )
    if worst_drop > 50:
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
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
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
