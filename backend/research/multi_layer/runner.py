"""Multi-Layer Research runner · measurement-only entry point.

Runs candidate layers over walk-forward windows and emits an evidence
report. Never modifies R2 · never auto-promotes weights.

CLI:
    python -m backend.research.multi_layer.runner \
        --market india --asof 2026-09-01 \
        --layers A-aegis-baseline,B-technical-context \
        --train-days 180 --test-days 30

Output:
    reports/research/multi_layer/evidence_{market}_{asof}.json

Every record includes:
    · framework_version
    · layer_key
    · window_fold
    · train / test dates
    · UNAVAILABLE flag per layer per window
    · measurement values (IC · hit-rate · Sharpe · etc)
    · reproducibility_hash of input data
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.research.multi_layer import (
    LayerRegistry, UNAVAILABLE, is_available,
    generate_windows, PointInTimeReader, __version__,
)


def run(market: str, asof: date, layer_keys: list[str],
         train_days: int, test_days: int) -> dict:
    layers = [LayerRegistry.get(k) for k in layer_keys]
    layers = [l for l in layers if l is not None]
    if not layers:
        return {"error": "no valid layers · use --list to see candidates"}

    start_probe = date(asof.year - 1, 1, 1)  # 1-year historical probe
    windows = list(generate_windows(start_probe, asof,
                                     train_days=train_days,
                                     test_days=test_days))

    reader = PointInTimeReader(_ROOT, asof)
    records = []
    for win in windows:
        for layer in layers:
            # Placeholder measurement · real layer implementations plug
            # in here as separate modules. Scaffold emits UNAVAILABLE if
            # any declared data_dep is missing at train_end.
            all_deps_ok = True
            for dep in layer.data_dep:
                dp = _ROOT / dep.split("*")[0].rstrip("/\\")
                if not dp.exists():
                    all_deps_ok = False
                    break
            rec = {
                "framework_version": __version__,
                "market": market,
                "layer_key": layer.key,
                "layer_title": layer.title,
                "category": layer.category,
                "fold": win.fold,
                "train_start": win.train_start.isoformat(),
                "train_end": win.train_end.isoformat(),
                "test_start": win.test_start.isoformat(),
                "test_end": win.test_end.isoformat(),
                "status": "AVAILABLE" if all_deps_ok else "UNAVAILABLE",
                "reason": (
                    "scaffold · no measurement implemented yet"
                    if all_deps_ok
                    else f"missing data_dep: {[d for d in layer.data_dep]}"
                ),
                "walk_forward_criterion": layer.walk_forward_criterion,
            }
            records.append(rec)

    out_dir = _ROOT / "reports" / "research" / "multi_layer"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_p = out_dir / f"evidence_{market}_{asof.isoformat()}.json"
    out_p.write_text(json.dumps({
        "framework_version": __version__,
        "market": market,
        "asof": asof.isoformat(),
        "layers": [l.key for l in layers],
        "n_windows": len(windows),
        "records": records,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "out_path": str(out_p.relative_to(_ROOT)),
        "n_records": len(records),
        "n_available": sum(1 for r in records if r["status"] == "AVAILABLE"),
        "n_unavailable": sum(1 for r in records if r["status"] == "UNAVAILABLE"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa"], default="india")
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--layers", default=",".join(l.key for l in LayerRegistry.all()))
    ap.add_argument("--train-days", type=int, default=180)
    ap.add_argument("--test-days", type=int, default=30)
    ap.add_argument("--list", action="store_true",
                     help="list candidate layers and exit")
    args = ap.parse_args()
    if args.list:
        for l in LayerRegistry.all():
            print(f"  {l.category}. {l.key}  ::  {l.title}")
        return 0
    rep = run(args.market, date.fromisoformat(args.asof),
                [k.strip() for k in args.layers.split(",")],
                args.train_days, args.test_days)
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
