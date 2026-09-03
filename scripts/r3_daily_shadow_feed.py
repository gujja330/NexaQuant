"""R3 · Daily shadow feed · Sprint A · Batch B
CEO 2026-09-03 · starts the Day-30 shadow clock NOW · runs in parallel
with substrate repair per PDF Phase 3.

Runs daily:
  1. Refresh R3 Tier-1 GBM training (uses current Outcome Dataset + Fundamentals FS)
  2. Score today's universe with the trained model
  3. Emit top-N picks to reports/research/r3/shadow_ledger.jsonl
     (via backend.research.r3.shadow_ledger.append_shadow_pick)

Isolation invariants (mechanically enforced by tests/isolation/):
  - Never writes to Registry
  - Never writes to Exit History
  - Never appears in delivered workbook
  - Uses its own Position ID namespace (implicit · no PIDs emitted)
  - Never modifies R2 weights / R2 SSoT / retirement config

Idempotent per (asof, market). Safe to re-run.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def run_daily_shadow(root: Path, market: str, top_n: int = 10) -> dict:
    """One full daily shadow cycle for a market."""
    from backend.research.r3.tier1_gbm import train_gbm, FEATURE_COLUMNS, build_training_frame
    from backend.research.r3.shadow_ledger import append_shadow_pick

    asof = datetime.now().strftime("%Y-%m-%d")

    # Step 1 · refresh training
    train_summary = train_gbm(root, market)
    if train_summary.get("status") not in ("TRAINED",):
        return {"market": market, "asof": asof, "status": "TRAIN_SKIPPED",
                "reason": train_summary.get("status"),
                "detail": train_summary}

    # Step 2 · load the fitted model shape · re-fit deterministic on same data
    # (For genuinely stable inference we should persist the fitted model to
    # disk; current implementation retrains on every call · fine for daily.)
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        import pandas as pd
    except ImportError:
        return {"market": market, "status": "SKLEARN_MISSING"}

    df = build_training_frame(root, market)
    if df.empty:
        return {"market": market, "asof": asof, "status": "NO_TRAINING_DATA"}
    X_cols = [c for c in FEATURE_COLUMNS if c in df.columns]
    X = df[X_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    y = df["win"].astype(int) if "win" in df.columns else (df["realized_return_pct"] > 0).astype(int)
    gbm = GradientBoostingClassifier(n_estimators=100, max_depth=3,
                                     learning_rate=0.05, random_state=42)
    gbm.fit(X, y)

    # Step 3 · score today's universe candidates.
    # In Sprint A initial ship we score every ticker in today's Outcome Dataset ·
    # the daily job that scores fresh universe candidates hooks in here.
    # Use latest per-ticker rows as candidate proxies.
    latest = df.sort_values("entry_date").groupby("ticker").tail(1)
    latest_X = latest[X_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    probs = gbm.predict_proba(latest_X)[:, 1] if len(latest_X) else []
    latest = latest.copy()
    latest["r3_calibrated_p"] = probs

    top = latest.nlargest(top_n, "r3_calibrated_p")

    n_written = 0
    for _, row in top.iterrows():
        p = float(row["r3_calibrated_p"])
        action = "BUY" if p >= 0.55 else ("WATCH" if p >= 0.45 else "AVOID")
        feats = {c: float(row[c]) for c in X_cols if pd.notna(row[c])}
        append_shadow_pick(
            root, market, str(row.get("ticker", "")).upper(), asof,
            r3_score=p, r3_calibrated_p=p, action=action,
            features=feats, model_id="aegis.r3.gbm_tier1.v1",
        )
        n_written += 1

    return {
        "market": market, "asof": asof, "status": "APPENDED",
        "n_picks_written": n_written,
        "top_n": top_n,
        "isolation_note": "Writes ONLY to reports/research/r3/shadow_ledger.jsonl",
        "day_30_gate_note": "Fires once shadow ledger has >= 20 picks (across days)",
        "run_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = run_daily_shadow(root, m, top_n=args.top_n)
        print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()
