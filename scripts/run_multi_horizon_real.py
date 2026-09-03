"""R3-T2-MULTI-HORIZON · real run using Signal Ledger fwd_5/10/20/60d.

Per-horizon rolling IC computed as sign-agreement between ensemble_score
and forward return. Then consensus + disputed flag scored per (asof, ticker).

This module *executes* against real substrate rather than staying scaffold.
If Signal Ledger thin · returns INSUFFICIENT_SAMPLE (not fake PASS).
"""
from __future__ import annotations

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

from backend.research.r3.tier2.multi_horizon_consensus import (
    consensus_probability, disputed_flag,
)


def _rolling_ic(scores: list[float], forwards: list[float]) -> float:
    """Sign-agreement rate · proxy for IC."""
    if not scores or not forwards: return 0.0
    n = min(len(scores), len(forwards))
    agree = sum(1 for i in range(n)
                if float(scores[i] or 0) * float(forwards[i] or 0) > 0)
    return agree / n if n else 0.0


def run(root: Path, market: str) -> dict:
    import pandas as pd
    ledger_path = root / "reports" / "research" / "signal_ledger" / f"{market}.parquet"
    if not ledger_path.exists():
        return {"market": market, "status": "SIGNAL_LEDGER_MISSING"}
    df = pd.read_parquet(ledger_path)
    if df.empty:
        return {"market": market, "status": "SIGNAL_LEDGER_EMPTY"}

    if len(df) < 30:
        return {"market": market, "status": "INSUFFICIENT_SAMPLE",
                "n_rows": int(len(df)),
                "note": "Multi-horizon needs at least 30 (score, forward-return) pairs across horizons"}

    scores = df["ensemble_score"].tolist() if "ensemble_score" in df.columns else []
    per_horizon_ic = {}
    for h_col, h_days in [("ret_5d", 5), ("ret_10d", 10), ("ret_20d", 20), ("ret_60d", 60)]:
        if h_col in df.columns:
            fwds = df[h_col].tolist()
            per_horizon_ic[h_days] = _rolling_ic(scores, fwds)

    # Per-row consensus · sample first 20 rows
    sample_rows = []
    for _, r in df.head(20).iterrows():
        per_horizon_p = {}
        for h_days, h_col in [(5, "ret_5d"), (10, "ret_10d"), (20, "ret_20d"), (60, "ret_60d")]:
            v = r.get(h_col)
            if v is not None:
                try:
                    p = 0.5 + float(v) * 0.5     # naive map [-1,+1] return → [0,1] prob
                    per_horizon_p[h_days] = max(0.0, min(1.0, p))
                except (TypeError, ValueError):
                    pass
        cp = consensus_probability(per_horizon_p, per_horizon_ic)
        disputed = disputed_flag(per_horizon_p, threshold_span=0.30)
        sample_rows.append({
            "ticker": r.get("ticker"),
            "asof": r.get("asof"),
            "per_horizon_p": per_horizon_p,
            "consensus_p": cp,
            "disputed_flag": disputed,
        })

    n_disputed = sum(1 for row in sample_rows if row["disputed_flag"])
    result = {
        "market": market,
        "n_rows_source": int(len(df)),
        "per_horizon_ic_sign_agreement": per_horizon_ic,
        "n_sample_rows_scored": len(sample_rows),
        "n_disputed": n_disputed,
        "sample_first_5": sample_rows[:5],
        "governance_note": ("Diagnostic execution · not a production sizing recommendation. "
                            "Real production use requires walk-forward + OOS + DSR deflation."),
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out = root / "reports" / "research" / "r3" / "tier2"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"multi_horizon_{market}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    args = ap.parse_args()
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = run(_ROOT, m)
        print(f"[multi-horizon] {m} · n_rows={r.get('n_rows_source', r.get('n_rows','?'))} · disputed={r.get('n_disputed','?')} · per_horizon_ic={r.get('per_horizon_ic_sign_agreement','?')}")


if __name__ == "__main__":
    main()
