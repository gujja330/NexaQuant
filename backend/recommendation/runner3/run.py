"""Runner 3 · Daily runner script.

    python -m backend.recommendation.runner3.run --market india
    python -m backend.recommendation.runner3.run --market usa

Isolation-respecting flow:
    1. Read universe from R2's rec-file (READ-ONLY · never writes back)
    2. Build feature vector per ticker via features_free adapters
    3. Predict via engine (if model trained) OR skip (Day 1 case)
    4. Append picks to shadow_ledger.jsonl (Runner 3 owned)
    5. Emit day30_gate verdict + three_runner_comparison
    6. Never touches R1 or R2 output files

Exits 0 even when model isn't trained yet (Day 1) so daily orchestrator
optional-step check doesn't false-trip.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date as _date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.runner3 import (  # noqa: E402
    engine, features_free, shadow_ledger, day30_gate, three_runner_comparison,
)


def _load_universe_from_r2(root: Path, market: str) -> list[dict]:
    """READ-ONLY view of R2's rec list · we use this as our universe but
    never write to it. If R2 hasn't run yet · returns empty."""
    p = (root / "usa/reports/recommendations.json"
             if market == "usa" else root / "reports/recommendations.json")
    if not p.exists(): return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("recommendations") or []
    except Exception:
        return []


def _extract_tech_features(rec: dict) -> dict:
    """Pull already-computed technical features from R2's rec (read-only)."""
    fv = {}
    for k in ("ensemble_score", "confidence", "calibrated_confidence",
                 "raw_confidence", "regime_adjusted_confidence",
                 "model_agreement", "composite_decision_score"):
        v = rec.get(k)
        if isinstance(v, (int, float)): fv[f"r2_{k}"] = float(v)
    attr = (rec.get("attribution") or {}).get("per_model") or []
    for m in attr[:8]:
        mid = m.get("model_id", "?").replace("aegis.", "").replace(".v1", "")
        s = m.get("share_pct")
        if isinstance(s, (int, float)): fv[f"share_{mid}"] = float(s) / 100.0
    return fv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=_date.today().isoformat())
    args = ap.parse_args()

    print(f"[runner3:{args.market}] asof={args.asof}")

    # Read cfg · confirm shadow mode
    cfg_p = _ROOT / "configs" / "runner3.json"
    cfg = json.loads(cfg_p.read_text(encoding="utf-8")) if cfg_p.exists() else {}
    if not cfg.get("shadow_only", True):
        print(f"[runner3:{args.market}] cfg.shadow_only=False · refusing to run "
              f"in non-shadow mode without CEO override (RL-Runner3 gate)")
        return 0

    # Universe from R2 (read-only)
    universe = _load_universe_from_r2(_ROOT, args.market)
    if not universe:
        print(f"[runner3:{args.market}] no R2 universe available · skipping")
        return 0

    # Build feature vectors
    feature_rows: list[dict] = []
    tickers: list[str] = []
    prices: dict[str, float] = {}
    for rec in universe:
        t = rec.get("ticker") or ""
        if not t: continue
        tech = _extract_tech_features(rec)
        fv = features_free.build_feature_vector(_ROOT, args.market, t,
                                                              args.asof, tech_features=tech)
        feature_rows.append(fv)
        tickers.append(t)
        ez = ((rec.get("position_plan") or {}).get("entry_zone") or {})
        cp = ez.get("current_price")
        if isinstance(cp, (int, float)): prices[t] = float(cp)
    print(f"[runner3:{args.market}] built features for {len(tickers)} tickers")

    # Predict (if model trained · else empty)
    picks = engine.predict(_ROOT, args.market, feature_rows, tickers)
    if not picks:
        print(f"[runner3:{args.market}] model not trained yet · logging feature "
              f"snapshots only (Day 1 case · train() will fire once we have "
              f"~30 labeled outcomes in the shadow ledger)")
        # Still log feature snapshots with neutral 0.5 confidence so we can
        # bootstrap the ledger for the Day-30 gate
        for i, t in enumerate(tickers):
            shadow_ledger.append(_ROOT, args.asof, args.market, t,
                                       rank=i+1, raw_score=0.5,
                                       calibrated_confidence=0.5,
                                       predicted_probability=0.5,
                                       features_used=feature_rows[i],
                                       entry_price=prices.get(t))
    else:
        print(f"[runner3:{args.market}] emitted {len(picks)} ranked picks")
        for p in picks:
            shadow_ledger.append(_ROOT, args.asof, args.market, p.ticker,
                                       rank=p.rank, raw_score=p.raw_score,
                                       calibrated_confidence=p.calibrated_confidence,
                                       predicted_probability=p.predicted_probability,
                                       features_used=p.features_used,
                                       entry_price=prices.get(p.ticker))

    # Emit Day-30 gate verdict
    verdict = day30_gate.evaluate(_ROOT, args.market, args.asof)
    day30_gate.emit(_ROOT, args.market, verdict)
    print(f"[runner3:{args.market}] day30_gate verdict={verdict['verdict']} · "
          f"n_days={verdict['n_days']} · n_pos={verdict['n_positions']} · "
          f"reason={verdict['reason']}")

    # Emit 3-runner comparison
    cmp = three_runner_comparison.build(_ROOT, args.market, args.asof)
    three_runner_comparison.emit(_ROOT, args.market, cmp)
    print(f"[runner3:{args.market}] 3-runner comparison written")

    # Also write today's picks as a snapshot (JSON only · no Telegram · shadow)
    out = _ROOT / "reports" / "research" / "runner3" / f"picks_{args.market}_{args.asof}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "engine":  "aegis.recommendation.runner3.v0.1",
        "asof":    args.asof, "market": args.market,
        "shadow_only": True,
        "n_picks": len(picks) if picks else len(tickers),
        "picks": [
            {"rank": p.rank, "ticker": p.ticker,
             "calibrated_confidence": round(p.calibrated_confidence, 3),
             "raw_score": round(p.raw_score, 3)}
            for p in (picks or [])
        ] if picks else [
            {"rank": i+1, "ticker": t,
             "calibrated_confidence": 0.5, "raw_score": 0.5,
             "note": "model_not_trained_yet"}
            for i, t in enumerate(tickers)
        ],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[runner3:{args.market}] shadow picks -> {out.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
