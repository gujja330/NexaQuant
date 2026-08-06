"""Sprint G-D · Turnover-Based Flow Adapter · reads NSE bhavcopy history.

Sources: reports/nse_bhavcopy/*.parquet (last 20 days)

Rules:
    · Ticker's today turnover > 3σ vs 20d mean → institutional accumulation +2.5
    · Ticker's today turnover 1.5-3σ            → mild accumulation +1.0
    · Ticker's today turnover < 0.3× 20d mean   → drying up -2.0
    · Normal range                              → 0.0

Uses TURNOVER_LACS column from NSE bhavcopy.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class TurnoverAdapter:
    engine_name = "institutional_flow"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        # India-only for now (bhavcopy is NSE)
        if market != "india":
            return zero_contribution(self.engine_name + "_turnover",
                                              "USA turnover data pending")

        bhav_dir = root / "reports" / "nse_bhavcopy"
        if not bhav_dir.exists():
            return zero_contribution(self.engine_name + "_turnover",
                                              "no bhavcopy dir")
        pqs = sorted(bhav_dir.glob("*.parquet"))
        if not pqs:
            return zero_contribution(self.engine_name + "_turnover",
                                              "no bhavcopy parquets")

        try:
            import pandas as pd
        except ImportError:
            return zero_contribution(self.engine_name + "_turnover",
                                              "pandas not installed")

        ticker = str(rec.get("ticker") or "").replace(".NS", "").replace(".BO", "").upper()

        # Load last 20 days of bhavcopy for this ticker
        turnovers = []
        for pq in pqs[-20:]:
            try:
                df = pd.read_parquet(pq)
                if "SYMBOL" not in df.columns or "TURNOVER_LACS" not in df.columns:
                    continue
                row = df[df["SYMBOL"].str.strip().str.upper() == ticker]
                if row.empty: continue
                # Take EQ series preferentially
                if "SERIES" in row.columns:
                    eq = row[row["SERIES"].str.strip() == "EQ"]
                    if not eq.empty: row = eq
                val = float(row["TURNOVER_LACS"].iloc[0])
                turnovers.append(val)
            except Exception:
                continue

        if len(turnovers) < 5:
            return zero_contribution(self.engine_name + "_turnover",
                                              f"only {len(turnovers)} days of bhavcopy history")

        today_val = turnovers[-1]
        prior = turnovers[:-1]
        mean = sum(prior) / len(prior)
        variance = sum((x - mean) ** 2 for x in prior) / len(prior)
        std = variance ** 0.5 if variance > 0 else 0
        sigma = (today_val - mean) / std if std > 0 else 0

        if sigma >= 3:      pts, sev = 2.5, "info"; label = "surge >3σ"
        elif sigma >= 1.5:  pts, sev = 1.0, "info"; label = f"elevated {sigma:.1f}σ"
        elif today_val < mean * 0.3:
            pts, sev = -2.0, "warning"; label = f"drying up ({today_val/mean:.1%} of avg)"
        else:
            return zero_contribution(self.engine_name + "_turnover",
                                              f"{ticker} turnover normal ({sigma:.1f}σ)")

        reason = (f"{ticker} turnover {label} · today {today_val:.0f}L "
                     f"vs 20d avg {mean:.0f}L → {pts:+.1f}pts")
        return ContextContribution(
            engine_name=self.engine_name + "_turnover", contribution_pts=pts,
            reason=reason, severity=sev, data_available=True,
            metadata={"ticker": ticker, "today_turnover_lacs": today_val,
                          "20d_mean_lacs": mean, "sigma": sigma},
        )
