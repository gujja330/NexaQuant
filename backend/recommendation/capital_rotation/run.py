"""Daily runner for Capital Rotation Engine.

Wave Y · L1 BUILT → L2 WIRED. Consumes portfolio_v3.json + recommendations_v3.json
+ macro_regime.json + sector_context.json · emits reports/rotation_plan.json.

Usage:
    python -m backend.recommendation.capital_rotation.run --market india
    python -m backend.recommendation.capital_rotation.run --market usa
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

from backend.recommendation.capital_rotation.engine import (  # noqa: E402
    CapitalRotationEngine, Position, Candidate,
)


def _reports_dir(market: str) -> Path:
    if market == "usa":
        return _ROOT / "usa" / "reports"
    return _ROOT / "reports"


def _load_positions(reports: Path) -> list[Position]:
    p = reports / "portfolio_v3.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    positions = d.get("positions", []) if isinstance(d, dict) else []
    out: list[Position] = []
    for pos in positions:
        try:
            out.append(Position(
                ticker=pos.get("ticker", ""),
                entry_score=float(pos.get("entry_score", 50.0)),
                current_score=float(pos.get("current_score", pos.get("score", 50.0))),
                entry_confidence=float(pos.get("entry_confidence", 0.5)),
                current_confidence=float(pos.get("current_confidence", pos.get("confidence", 0.5))),
                entry_rank=int(pos.get("entry_rank", 999)),
                current_rank=int(pos.get("current_rank", pos.get("rank", 999))),
                entry_price=float(pos.get("entry_price", pos.get("price", 100.0))),
                current_price=float(pos.get("current_price", pos.get("price", 100.0))),
                sector=str(pos.get("sector", "")),
                upside_remaining_pct=float(pos.get("upside_remaining_pct", 0.0)),
                pnl_pct=float(pos.get("pnl_pct", 0.0)),
            ))
        except (TypeError, ValueError):
            continue
    return out


def _load_candidates(reports: Path) -> list[Candidate]:
    p = reports / "recommendations_v3.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    recs = d.get("recommendations", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])
    out: list[Candidate] = []
    for i, r in enumerate(recs):
        try:
            out.append(Candidate(
                ticker=r.get("ticker", ""),
                score=float(r.get("ensemble_score", r.get("score", 0.0))),
                confidence=float(r.get("calibrated_confidence", r.get("confidence", 0.5))),
                rank=int(r.get("rank", i + 1)),
                sector=str(r.get("sector", "")),
                upside_pct=float(r.get("upside_pct", 0.0)),
            ))
        except (TypeError, ValueError):
            continue
    return out


def _load_macro(reports: Path) -> str:
    p = reports / "macro_regime.json"
    if not p.exists():
        return "unknown"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return str(d.get("regime", "unknown"))
    except Exception:
        return "unknown"


def _load_sector_strengths(reports: Path) -> dict[str, float]:
    p = reports / "sector_context.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        sectors = d.get("sectors")
        out: dict[str, float] = {}
        if isinstance(sectors, list):
            for s in sectors:
                if isinstance(s, dict):
                    name = str(s.get("display_name") or s.get("sector_key") or "").strip()
                    if not name:
                        continue
                    score = s.get("score")
                    if score is None:
                        continue
                    # Same convention as C0 fix: (score-50)/2.5 gives ~[-20,+20]
                    out[name] = (float(score) - 50.0) / 2.5
        return out
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD")
    args = ap.parse_args()

    reports = _reports_dir(args.market)
    reports.mkdir(parents=True, exist_ok=True)

    positions = _load_positions(reports)
    candidates = _load_candidates(reports)
    macro = _load_macro(reports)
    sectors = _load_sector_strengths(reports)
    asof = date.fromisoformat(args.asof) if args.asof else date.today()
    run_utc = datetime.now(timezone.utc).isoformat()

    engine = CapitalRotationEngine(args.market)
    plan = engine.run(positions, candidates, sectors, macro, asof, run_utc)

    out_path = reports / "rotation_plan.json"
    out_path.write_text(json.dumps({
        **{k: v for k, v in plan.__dict__.items() if not k.startswith("_")},
    }, indent=2, default=str), encoding="utf-8")

    print(f"[capital_rotation:{args.market}] "
          f"n_positions={plan.n_positions} n_candidates={plan.n_candidates} "
          f"exit={plan.n_exit} trim={plan.n_trim} keep={plan.n_keep} rotate={plan.n_rotate} "
          f"macro_gate={plan.macro_gate} -> {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
