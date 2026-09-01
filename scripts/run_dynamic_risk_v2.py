"""Invoke the existing dynamic_risk_v2 engine for both markets.

CEO 2026-09-01 final closure · this wrapper does NOT modify the engine ·
it only invokes the existing `backend.risk.dynamic_risk_v2.compute` +
`emit` for each market so that both `reports/context/dynamic_risk_india.json`
and `reports/context/dynamic_risk_usa.json` are produced daily.

Without this wrapper, USA has no dynamic_risk output · the bridge falls
back to non-authoritative stops · no USA exits get enforced.

Idempotent · read-only against Registry · writes only to
reports/context/dynamic_risk_{market}.json.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.risk import dynamic_risk_v2 as drv


def run_market(market: str, asof: str) -> dict:
    rep = drv.compute(_ROOT, market, asof)
    out_p = drv.emit(_ROOT, rep)
    return {
        "market": market,
        "asof": asof,
        "n_positions": rep.n_positions,
        "n_atr_updated": rep.n_atr_updated,
        "n_vol_scaled": rep.n_vol_scaled,
        "n_trailing_lifted": rep.n_trailing_lifted,
        "n_unchanged": rep.n_unchanged,
        "out_path": str(out_p.relative_to(_ROOT)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    args = ap.parse_args()
    import json
    for m in (["india", "usa"] if args.market == "both" else [args.market]):
        rep = run_market(m, args.asof)
        print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
