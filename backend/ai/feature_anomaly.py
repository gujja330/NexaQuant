"""AI Feature Anomaly Agent v1.0.

Reads a feature snapshot DataFrame + validation result. Identifies outlier
values (|z| > threshold) and narrates the top few. **No recommendations.**
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.ai.base import AgentOutput

VERSION = "v1.0"
Z_THRESHOLD = 5.0


def run(df: pd.DataFrame, market_name: str, asof: date | None = None,
         top_k: int = 10) -> AgentOutput:
    findings: list[dict] = []
    citations = ["backend/feature_store"]
    if df is None or df.empty:
        return AgentOutput(agent="feature_anomaly", version=VERSION, market=market_name,
                             asof=asof or date.today(),
                             headline="No feature snapshot available",
                             narrative="Feature snapshot empty — nothing to check.",
                             confidence=0.0,
                             caveats=["Empty snapshot"])

    # Look for outliers in numeric columns
    outliers: list[dict] = []
    for col in df.columns:
        if col in ("market", "ticker", "asof", "sector", "currency", "mi_regime"):
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        s = df[col].dropna()
        if len(s) < 10: continue
        mu = float(s.mean()); sig = float(s.std())
        if sig == 0: continue
        z = ((df[col] - mu).abs() / sig)
        idx = z[z > Z_THRESHOLD].index
        for i in idx:
            tk = df.at[i, "ticker"] if "ticker" in df.columns else "?"
            outliers.append({
                "ticker": str(tk), "feature": col,
                "value":  float(df.at[i, col]) if pd.notna(df.at[i, col]) else None,
                "z":      round(float(z[i]), 2),
            })
    outliers.sort(key=lambda x: abs(x.get("z", 0)), reverse=True)
    top = outliers[:top_k]
    findings.extend(top)

    if not top:
        head = "No |z|>5 feature outliers detected across the universe."
        narr = ("Feature Store values are within normal ranges for this snapshot. "
                 "This is a positive signal — no ingest anomalies suggesting data corruption "
                 "or lookback errors.")
    else:
        head = f"{len(outliers)} feature outlier(s) flagged (top {min(top_k, len(outliers))} shown)."
        lines = [f"  · {o['ticker']}: {o['feature']} = {o['value']} (z={o['z']})" for o in top]
        narr = (f"{len(outliers)} data points across the universe carry |z|>5 vs their column "
                 f"mean.\n\n" + "\n".join(lines) +
                 "\n\nHigh z-scores are not necessarily wrong (a real 52-week high can be a legitimate extreme), "
                 "but they warrant a look before downstream engines act on them.")

    return AgentOutput(
        agent="feature_anomaly", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=head, narrative=narr,
        findings=findings,
        evidence={"n_outliers": len(outliers), "z_threshold": Z_THRESHOLD,
                    "n_rows": int(len(df)), "n_numeric_cols_scanned": sum(
                       1 for c in df.columns if pd.api.types.is_numeric_dtype(df[c]))},
        citations=citations,
        confidence=1.0 if len(df) > 20 else 0.6,
        caveats=[],
        determinism="template",
    )
