"""AEGIS USA · Risk & Capital Engine v1.0.

Position sizing + concentration limits + portfolio-level risk verdict.
Emits usa/reports/risk_latest.json.

Sizing formula (matches India's spirit — fractional-Kelly with caps):

    target_weight = min(
        max_weight_per_position,
        conviction * confidence * kelly_fraction
    )

Where:
    max_weight_per_position  = 0.08   (8% cap)
    kelly_fraction           = 0.25   (quarter-Kelly · survival bias)
    conviction               = score / 100

Deterministic. All amounts in USD ($).
"""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]


# ── Sizing knobs (locked at v1.0 — post-freeze changes require evidence)
MAX_WEIGHT_PER_POSITION   = 0.08   # 8% hard cap
KELLY_FRACTION            = 0.25   # quarter-Kelly
MIN_POSITION_WEIGHT       = 0.01   # 1% floor (below this → skip)
MAX_SECTOR_WEIGHT         = 0.30   # 30% per sector

VOL_HEALTHY_MAX_ANN       = 0.35   # 35% ann vol → healthy portfolio
VOL_WARN_MAX_ANN          = 0.50   # 35-50% → WARNING
                                     # >50%   → BLOCK


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  AEGIS USA · Risk & Capital Engine v1.0")
    print("=" * 70)

    recs_p = _USA / "reports" / "recommendations.json"
    if not recs_p.exists():
        print("FATAL: recommendations.json missing.")
        return 1
    recs = json.loads(recs_p.read_text(encoding="utf-8"))

    sizing: list[dict] = []
    total_weight = 0.0
    sector_weight: dict[str, float] = {}

    # Pass 1 — proposed weights per position
    for r in (recs.get("recommendations") or []):
        score  = r.get("composite_decision_score") or 0.0
        conf   = r.get("confidence") or 0.0
        action = r.get("recommendation")
        sector = r.get("sector") or "?"

        # Only Strong-Buy / Buy / Accumulate get positive sizing
        if action not in ("Strong-Buy", "Buy", "Accumulate"):
            sizing.append({
                "ticker":         r.get("ticker"),
                "sector":         sector,
                "target_weight":  0.0,
                "verdict":        "SKIP",
                "reason":         f"action={action}",
                "factors":        {"score": score, "confidence": conf},
                "counterfactuals": {},
            })
            continue

        conviction = score / 100.0
        raw = conviction * conf * KELLY_FRACTION
        target = min(MAX_WEIGHT_PER_POSITION, max(0.0, raw))

        if target < MIN_POSITION_WEIGHT:
            verdict = "SKIP"
            reason = f"below_floor:{target:.4f}"
            target = 0.0
        else:
            verdict = "PASS"
            reason = None

        sizing.append({
            "ticker":          r.get("ticker"),
            "sector":          sector,
            "target_weight":   round(target, 4),
            "verdict":         verdict,
            "reason":          reason,
            "factors":         {
                "score":            score,
                "confidence":       conf,
                "kelly_fraction":   KELLY_FRACTION,
                "conviction":       round(conviction, 4),
            },
            "counterfactuals": {
                "if_full_kelly":     round(min(1.0, conviction * conf), 4),
                "if_max_confidence": round(min(MAX_WEIGHT_PER_POSITION, conviction * KELLY_FRACTION), 4),
            },
        })

    # Pass 2 — enforce sector caps
    for row in sorted(sizing, key=lambda x: -x["target_weight"]):
        if row["target_weight"] <= 0: continue
        s = row["sector"]
        used = sector_weight.get(s, 0.0)
        cap_left = MAX_SECTOR_WEIGHT - used
        if cap_left <= 0:
            row["target_weight"] = 0.0
            row["verdict"] = "BLOCK"
            row["reason"]  = f"sector_cap_exceeded:{s}"
            continue
        if row["target_weight"] > cap_left:
            row["reason"] = f"sector_cap_clip:{s}"
            row["verdict"] = "WARNING"
            row["target_weight"] = round(cap_left, 4)
        sector_weight[s] = sector_weight.get(s, 0.0) + row["target_weight"]
        total_weight += row["target_weight"]

    # Portfolio verdict
    cash_pct = max(0.0, 1.0 - total_weight)
    n_positions = sum(1 for x in sizing if x["target_weight"] > 0)

    # Proxy portfolio vol: weighted average of per-position ann_vol
    port_vol = 0.0
    weight_sum = 0.0
    for r in (recs.get("recommendations") or []):
        row = next((x for x in sizing if x["ticker"] == r.get("ticker")), None)
        if not row or row["target_weight"] <= 0: continue
        vol = ((r.get("entry_exit") or {}).get("annualised_vol_pct") or 25.0) / 100.0
        port_vol += vol * row["target_weight"]
        weight_sum += row["target_weight"]
    port_vol = round(port_vol / weight_sum, 4) if weight_sum else 0.0

    if   port_vol < VOL_HEALTHY_MAX_ANN: port_verdict = "PASS"
    elif port_vol < VOL_WARN_MAX_ANN:    port_verdict = "WARNING"
    else:                                 port_verdict = "BLOCK"

    alerts = []
    for s, w in sector_weight.items():
        if w >= MAX_SECTOR_WEIGHT - 0.005:
            alerts.append({"kind": "SECTOR_CAP", "sector": s, "weight": round(w, 4)})

    out = {
        "engine":              "usa_risk_capital",
        "version":             "v1.0",
        "market":              "USA",
        "currency":            "USD",
        "run_utc":             datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "portfolio_risk": {
            "n_positions":         n_positions,
            "total_weight":        round(total_weight, 4),
            "cash_pct":            round(cash_pct, 4),
            "portfolio_vol_annual": port_vol,
            "verdict":             port_verdict,
            "alerts":              alerts,
        },
        "sector_weights":      {k: round(v, 4) for k, v in sorted(sector_weight.items())},
        "sizing":              sizing,
        "config": {
            "max_weight_per_position": MAX_WEIGHT_PER_POSITION,
            "kelly_fraction":          KELLY_FRACTION,
            "min_position_weight":     MIN_POSITION_WEIGHT,
            "max_sector_weight":       MAX_SECTOR_WEIGHT,
        },
    }
    (_USA / "reports" / "risk_latest.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")

    print(f"  positions sized:   {n_positions}")
    print(f"  total deployment:  {total_weight * 100:.2f}%")
    print(f"  cash:              {cash_pct * 100:.2f}%")
    print(f"  portfolio vol:     {port_vol * 100:.2f}% annualised")
    print(f"  verdict:           {port_verdict}")
    print(f"  sector caps:       {len(alerts)} alerts")
    print(f"  elapsed:           {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
