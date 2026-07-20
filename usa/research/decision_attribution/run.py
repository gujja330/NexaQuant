"""AEGIS USA · Decision Attribution v1.0.

Per-recommendation per-subsystem contribution %. Same 8 subsystems
as India (research / fusion / winner_genome / validation / risk / dna /
sector / market) with USA-tuned raw signals.

Day 1 baseline: subsystem_accuracy reports "insufficient historical
trades" (no learning.parquet-equivalent). Per-rec contributions still
compute from live artefacts.

USD everywhere.
"""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]

SUBSYSTEM_WEIGHTS = {
    "research":       0.22,
    "fusion":         0.20,
    "winner_genome":  0.14,
    "validation":     0.14,
    "risk":           0.10,
    "dna":            0.08,
    "sector":         0.07,
    "market":         0.05,
}


def _minmax(x: pd.Series) -> pd.Series:
    s = x.astype(float)
    lo, hi = s.min(), s.max()
    if pd.isna(lo) or pd.isna(hi) or hi <= lo:
        return s.notna().astype(float) * 0.5
    return ((s - lo) / (hi - lo)).fillna(0.0)


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  AEGIS USA · Decision Attribution v1.0")
    print("=" * 70)

    recs = json.loads((_USA / "reports" / "recommendations.json").read_text(encoding="utf-8"))
    intel = json.loads((_USA / "reports" / "investment_intelligence.json").read_text(encoding="utf-8"))
    risk  = json.loads((_USA / "reports" / "risk_latest.json").read_text(encoding="utf-8"))
    stock_val = json.loads((_USA / "reports" / "stock_validation.json").read_text(encoding="utf-8"))

    intel_by_ticker = {str(r.get("ticker")): r for r in (intel.get("reports") or [])}
    sizing_by_ticker = {str(s.get("ticker")): s for s in (risk.get("sizing") or [])}
    sv_tickers = stock_val.get("tickers") or {}

    rows = []
    for r in (recs.get("recommendations") or []):
        t = str(r.get("ticker"))
        ii = intel_by_ticker.get(t) or {}
        rk = sizing_by_ticker.get(t) or {}
        sv = sv_tickers.get(t) or {}

        s_research  = r.get("composite_decision_score")
        s_fusion    = ii.get("intelligence_score")
        s_wg        = 0.0                                         # no signatures yet on day 1
        s_valid     = (sv.get("win_rate") or 0.0) * ((sv.get("reliability_stars") or 0) / 5.0)
        verdict     = (rk.get("verdict") or "").upper()
        tw          = float(rk.get("target_weight") or 0.0)
        s_risk      = tw if verdict == "PASS" else (tw * 0.5 if verdict == "WARNING" else 0.0)
        s_dna       = 0.5                                         # placeholder — no DNA archive yet
        s_sector    = r.get("sector_score")
        s_market    = 50.0                                        # neutral for now

        rows.append({
            "ticker":         t,
            "research":       s_research,
            "fusion":         s_fusion,
            "winner_genome":  s_wg,
            "validation":     s_valid,
            "risk":           s_risk,
            "dna":            s_dna,
            "sector":         s_sector,
            "market":         s_market,
        })

    df = pd.DataFrame(rows)
    scaled = pd.DataFrame(index=df.index)
    scaled["ticker"] = df["ticker"]
    for sub in SUBSYSTEM_WEIGHTS:
        s = df[sub] if sub in df.columns else pd.Series([0.0] * len(df))
        scaled[sub + "_scaled"] = _minmax(s)

    weighted = pd.DataFrame(index=df.index)
    weighted["ticker"] = df["ticker"]
    for sub, w in SUBSYSTEM_WEIGHTS.items():
        weighted[sub] = scaled[sub + "_scaled"] * w
    subs = list(SUBSYSTEM_WEIGHTS.keys())
    totals = weighted[subs].sum(axis=1)
    for c in subs:
        with np.errstate(divide="ignore", invalid="ignore"):
            weighted[c] = np.where(totals > 0,
                                     (weighted[c] / totals) * 100.0,
                                     100.0 / len(subs))
    weighted["decision_strength"] = totals

    per_rec = {}
    for i in range(len(df)):
        t = str(df.iloc[i]["ticker"])
        per_rec[t] = {
            "contributions": {s: round(float(weighted.iloc[i][s]), 2) for s in subs},
            "raw_signals":   {s: (float(df.iloc[i][s]) if pd.notna(df.iloc[i][s]) else None) for s in subs},
            "decision_strength": round(float(weighted.iloc[i]["decision_strength"]), 4),
        }

    out = {
        "engine":            "usa_decision_attribution",
        "version":           "v1.0",
        "market":            "USA",
        "run_utc":           datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "n_recommendations": len(per_rec),
        "subsystem_weights": dict(SUBSYSTEM_WEIGHTS),
        "per_recommendation": per_rec,
        "subsystem_accuracy": {
            "available": False,
            "reason":    "No historical closed trades yet — USA has no learning.parquet-equivalent. Populates when paper portfolio accumulates ≥ 30 closed positions.",
        },
        "n_trade_attributions":  0,
        "top_alpha_creators":    [],
        "top_alpha_destroyers":  [],
    }
    (_USA / "reports" / "decision_attribution.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")

    print(f"  attributed:    {len(per_rec)} recommendations")
    print(f"  subsystems:    {len(SUBSYSTEM_WEIGHTS)}")
    print(f"  historical accuracy: (deferred — no closed trades on day 1)")
    print(f"  elapsed:       {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
