"""Daily runner for Portfolio Attribution Engine.

Wave Y · L1 BUILT → L2 WIRED. Consumes portfolio_v3.json + ensemble.json
+ execution_ledger · emits reports/portfolio_attribution.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.portfolio.monitoring.attribution import (  # noqa: E402
    PortfolioAttributionEngine, ATTRIBUTION_FACTORS,
)


def _reports_dir(market: str) -> Path:
    if market == "usa":
        return _ROOT.joinpath("usa", "reports")
    return _ROOT / "reports"


def _load_ensemble_weights(reports: Path) -> dict[str, dict[str, float]]:
    """Load per-ticker factor weights from ensemble.json."""
    p = reports / "ensemble.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict[str, float]] = {}
    entries = d.get("predictions", d.get("per_ticker", [])) if isinstance(d, dict) else []
    for e in entries or []:
        t = e.get("ticker", "")
        if not t:
            continue
        # Try common shapes for per-model contributions
        contribs = e.get("model_contributions") or e.get("per_model") or {}
        weights: dict[str, float] = {}
        if isinstance(contribs, dict):
            for k, v in contribs.items():
                try:
                    weights[str(k).lower()] = float(v)
                except (TypeError, ValueError):
                    pass
        out[t] = weights
    return out


def _load_positions(reports: Path, ens: dict[str, dict[str, float]]):
    p = reports / "portfolio_v3.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    positions = d.get("positions", []) if isinstance(d, dict) else []
    out = []
    for pos in positions:
        t = pos.get("ticker", "")
        if not t:
            continue
        realized = float(pos.get("realized_return_pct",
                                 pos.get("pnl_pct",
                                         pos.get("unrealized_pnl_pct", 0.0))))
        weights = ens.get(t, {})
        # Map model names → attribution factors where possible
        factor_weights: dict[str, float] = {}
        for f in ATTRIBUTION_FACTORS:
            if f in weights:
                factor_weights[f] = weights[f]
        out.append({
            "ticker": t,
            "realized_return_pct": realized,
            "factor_weights": factor_weights,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=None)
    args = ap.parse_args()

    reports = _reports_dir(args.market)
    reports.mkdir(parents=True, exist_ok=True)

    ens = _load_ensemble_weights(reports)
    positions = _load_positions(reports, ens)
    asof = date.fromisoformat(args.asof) if args.asof else date.today()

    engine = PortfolioAttributionEngine(args.market)
    rep = engine.run(positions, asof, datetime.now(timezone.utc).isoformat())

    out_path = reports / "portfolio_attribution.json"
    payload = {k: v for k, v in rep.__dict__.items() if not k.startswith("_")}
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"[portfolio_attribution:{args.market}] "
          f"n_positions={rep.n_positions} "
          f"total_realized_return_pct={rep.total_realized_return_pct} "
          f"-> {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
