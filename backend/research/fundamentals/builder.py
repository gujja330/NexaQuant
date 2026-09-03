"""AEGIS Fundamentals Feature Store · builder

Orchestrates layer1-5 derivations per (market, ticker, asof). Reads raw
financial-statement inputs from `backend/research/fundamentals/providers/*`
(one provider adapter per source · yfinance, nseindia, finviz, moneycontrol).

Provider adapters return the standardized input dict expected by the layer
functions. This builder does NOT fetch web data itself · it accepts a
resolved input map produced by the pipeline caller.

Storage:
  reports/research/fundamentals_feature_store/{market}.parquet   (append)
  reports/research/fundamentals_feature_store/{market}.summary.json
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from backend.research.fundamentals.layer1_quality import LAYER1_FUNCTIONS
from backend.research.fundamentals.layer2_value import (
    LAYER2_FUNCTIONS, sector_rel_value_rank,
)
from backend.research.fundamentals.layer3_change import LAYER3_FUNCTIONS
from backend.research.fundamentals.layer4_flow import LAYER4_FUNCTIONS
from backend.research.fundamentals.layer5_event import LAYER5_FUNCTIONS

_ROOT = Path(__file__).resolve().parents[3]

LAYER_MAP = {
    1: LAYER1_FUNCTIONS,
    2: LAYER2_FUNCTIONS,
    3: LAYER3_FUNCTIONS,
    4: LAYER4_FUNCTIONS,
    5: LAYER5_FUNCTIONS,
}


def compute_row(market: str, ticker: str, asof: str,
                fin_inputs: dict,
                sector_cohort_value: Optional[list[dict]] = None) -> dict:
    """Derive one (market, ticker, asof) feature row from provider inputs.

    fin_inputs · standardized dict from a provider adapter.
    sector_cohort_value · optional list of {ticker, fcf_yield, ev_ebitda,
        total_shareholder_yield} for peers on the same asof (Layer 2 rank).
    """
    row: dict = {
        "market": market, "ticker": ticker, "asof": asof,
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": "1.0.0",
    }
    # Layer 1
    for name, fn in LAYER1_FUNCTIONS.items():
        row[name] = fn(fin_inputs)
    # Layer 2
    for name, fn in LAYER2_FUNCTIONS.items():
        row[name] = fn(fin_inputs)
    row["sector_rel_value_rank"] = sector_rel_value_rank(
        row.get("fcf_yield"), row.get("ev_ebitda"),
        row.get("total_shareholder_yield"),
        sector_cohort_value or [],
    )
    # Layer 3
    for name, fn in LAYER3_FUNCTIONS.items():
        row[name] = fn(fin_inputs)
    # Layer 4
    for name, fn in LAYER4_FUNCTIONS.items():
        row[name] = fn(fin_inputs)
    # Layer 5
    row["earnings_calendar_window"] = LAYER5_FUNCTIONS["earnings_calendar_window"](
        fin_inputs, asof
    )
    row["promoter_pledge_pct"] = LAYER5_FUNCTIONS["promoter_pledge_pct"](
        fin_inputs, market
    )
    # Data sources
    row["data_sources"] = fin_inputs.get("data_sources", "")
    return row


def build_feature_store(root: Path, market: str,
                        rows: list[dict]) -> dict:
    """Persist a batch of computed rows to the store · merge dedupe by
    (market, ticker, asof), last-write wins.

    `rows` should be the output of compute_row() calls."""
    import pandas as pd
    if not rows:
        return {"market": market, "n_rows_new": 0}

    out_dir = root / "reports" / "research" / "fundamentals_feature_store"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{market}.parquet"

    new_df = pd.DataFrame(rows)
    if p.exists():
        try:
            existing = pd.read_parquet(p)
            df = pd.concat([existing, new_df], ignore_index=True)
        except Exception:
            df = new_df
    else:
        df = new_df

    df = df.drop_duplicates(subset=["market", "ticker", "asof"], keep="last")
    df = df.sort_values(["ticker", "asof"]).reset_index(drop=True)
    df.to_parquet(p, index=False)

    n_by_layer = {
        1: int(df["piotroski_f"].notna().sum()),
        2: int(df["fcf_yield"].notna().sum()),
        3: int(df["analyst_rev_momentum"].notna().sum()),
        4: int(df["options_pcr"].notna().sum()) if "options_pcr" in df.columns else 0,
        5: int(df["earnings_calendar_window"].notna().sum()) if "earnings_calendar_window" in df.columns else 0,
    }
    n_by_layer["3_incl_13f"] = int(df["inst_13f_change"].notna().sum()) if "inst_13f_change" in df.columns else 0
    summary = {
        "market": market,
        "n_rows_total": int(len(df)),
        "n_rows_new": int(len(new_df)),
        "n_tickers": int(df["ticker"].nunique()),
        "n_asof": int(df["asof"].nunique()),
        "n_with_signal_by_layer": n_by_layer,
        "parquet_path": str(p.relative_to(root)),
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (out_dir / f"{market}.summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def load_feature_store(root: Path, market: str):
    import pandas as pd
    p = root / "reports" / "research" / "fundamentals_feature_store" / f"{market}.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)
