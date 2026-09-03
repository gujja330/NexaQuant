"""AEGIS Outcome Dataset · builder

Joins:
  reports/research/opportunity_registry.jsonl           (positions + open/close)
  reports/research/signal_ledger/{market}.parquet       (entry signal snapshot + fwd returns)
  data/raw/{market}/{TICKER}_D1.parquet                 (OHLC · for MFE/MAE + ATR)
  reports/research/fundamentals_feature_store/{market}.parquet   (fundamentals @ entry)  [optional]

Output:
  reports/research/outcome_dataset/{market}.parquet
  reports/research/outcome_dataset/{market}.summary.json

Schema declared in configs/outcome_dataset_schema.yaml. This builder is
the SOLE source of truth for every P0-P5 experiment · they never
re-derive from raw jsonl.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]


def _clean_ticker(t: str) -> str:
    if not t: return ""
    t = str(t).upper()
    for suf in (".NS", ".BO", ".NSE", ".BSE"):
        if t.endswith(suf):
            return t[: -len(suf)]
    return t


def _parquet_path(root: Path, market: str, ticker: str) -> Path:
    from backend.research._paths import price_parquet_path
    resolved = price_parquet_path(root, market, ticker)
    if resolved: return resolved
    return root / "data" / "raw" / market / f"{ticker}_D1.parquet"


def _is_administrative_exit(entry_date: str, exit_date: str,
                            entry_price: float, exit_price: float) -> bool:
    """Structural filter · same-day OR zero-price-delta (within 0.005%).

    Mirrors scripts/build_aegis_3sheet_workbook.py::_is_administrative_exit
    · the single source of truth used by builder + reconciler + A23 + I20."""
    try:
        if entry_date and exit_date and entry_date == exit_date:
            return True
        if entry_price and exit_price:
            ep = float(entry_price); xp = float(exit_price)
            if ep > 0 and abs(xp - ep) / ep <= 0.00005:
                return True
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return False


def _load_registry_rows(root: Path, market: str) -> list[dict]:
    p = root / "reports" / "research" / "opportunity_registry.jsonl"
    if not p.exists(): return []
    rows: list[dict] = []
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line: continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("market") != market: continue
            rows.append(o)
    return rows


def _load_signal_ledger(root: Path, market: str):
    import pandas as pd
    p = root / "reports" / "research" / "signal_ledger" / f"{market}.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()


def _snapshot_signal_at_entry(ledger, ticker: str, entry_date: str) -> dict:
    if ledger is None or ledger.empty: return {}
    tkr = _clean_ticker(ticker)
    q = ledger[(ledger["ticker"] == tkr) & (ledger["asof"] == entry_date)]
    if q.empty:
        # nearest snapshot at or before entry
        q = ledger[(ledger["ticker"] == tkr) & (ledger["asof"] <= entry_date)]
        if q.empty:
            return {}
        q = q.sort_values("asof").tail(1)
    r = q.iloc[0].to_dict()
    return {
        "entry_signal_score":      r.get("ensemble_score"),
        "entry_calibrated_conf":   r.get("calibrated_confidence"),
        "entry_regime_adj_conf":   r.get("regime_adjusted_confidence"),
        "entry_model_agreement":   r.get("model_agreement"),
        "entry_n_models_scoring":  r.get("n_models_scoring"),
        "entry_disagreement":      bool(r.get("disagreement_flag", False)),
        "sector":                  r.get("sector"),
        "industry":                r.get("industry"),
    }


def _load_prices(root: Path, market: str, ticker: str):
    import pandas as pd
    p = _parquet_path(root, market, _clean_ticker(ticker))
    if not p.exists(): return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


def _atr14(closes, highs, lows, entry_idx: int) -> Optional[float]:
    """Point-in-time ATR-14 · uses ONLY data at or before entry_idx."""
    if entry_idx < 14: return None
    trs = []
    for i in range(max(1, entry_idx - 13), entry_idx + 1):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1]),
        )
        trs.append(tr)
    if not trs: return None
    return sum(trs) / len(trs)


def _mfe_mae(closes, highs, lows, entry_idx: int, exit_idx: int) -> tuple[Optional[float], Optional[float]]:
    """Max Favorable / Adverse Excursion in decimal % from entry_close."""
    if entry_idx < 0 or exit_idx < entry_idx: return (None, None)
    ep = float(closes[entry_idx])
    if ep <= 0: return (None, None)
    win_hi = max(highs[entry_idx:exit_idx+1])
    win_lo = min(lows[entry_idx:exit_idx+1])
    mfe = (float(win_hi) / ep) - 1.0
    mae = (float(win_lo) / ep) - 1.0
    return (mfe, mae)


def _find_idx(df, date_str: str) -> Optional[int]:
    import pandas as pd
    if df is None or df.empty or not date_str: return None
    try:
        target = pd.to_datetime(date_str).normalize()
        if target in df.index:
            return df.index.get_loc(target)
        mask = df.index <= target
        if not mask.any(): return None
        return int(mask.sum()) - 1
    except Exception:
        return None


def build_outcome_dataset(root: Path, market: str) -> dict:
    import pandas as pd

    registry_rows = _load_registry_rows(root, market)
    ledger = _load_signal_ledger(root, market)

    out_rows: list[dict] = []
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    for o in registry_rows:
        ticker = _clean_ticker(o.get("ticker", ""))
        if not ticker: continue
        entry_date = str(o.get("created_date") or "")
        exit_date = str(o.get("closed_date") or "") or None

        prices = _load_prices(root, market, ticker)
        entry_idx = _find_idx(prices, entry_date)
        exit_idx = _find_idx(prices, exit_date) if exit_date else None

        entry_price = None; exit_price = None
        atr = None; mfe = None; mae = None
        if prices is not None and not prices.empty and entry_idx is not None:
            closes = prices["close"].to_numpy()
            highs = prices["high"].to_numpy()
            lows = prices["low"].to_numpy()
            entry_price = float(closes[entry_idx])
            atr = _atr14(closes, highs, lows, entry_idx)
            if exit_idx is not None and exit_idx >= entry_idx:
                exit_price = float(closes[exit_idx])
                mfe, mae = _mfe_mae(closes, highs, lows, entry_idx, exit_idx)

        realized_ret = None
        holding_days = None
        if entry_price and exit_price and entry_price > 0:
            realized_ret = (exit_price / entry_price) - 1.0
        if entry_date and exit_date:
            try:
                d0 = pd.to_datetime(entry_date); d1 = pd.to_datetime(exit_date)
                holding_days = int((d1 - d0).days)
            except Exception:
                pass

        signal_snap = _snapshot_signal_at_entry(ledger, ticker, entry_date)

        is_admin = _is_administrative_exit(entry_date, exit_date or "",
                                           entry_price or 0.0, exit_price or 0.0)
        closed_reason = str(o.get("closed_reason") or "")
        # dynamic-stop reconstruction · k=2.0 · target m=3.0 · horizon 60d
        dyn_stop = (entry_price - 2.0 * atr) if (entry_price and atr) else None
        target = (entry_price + 3.0 * atr) if (entry_price and atr) else None

        row = {
            "position_id":  o.get("opportunity_id"),
            "market": market,
            "runner": o.get("runner"),
            "ticker": ticker,
            "sector": signal_snap.get("sector"),
            "industry": signal_snap.get("industry"),
            "cap_bucket": None,   # populated by cap-classifier separately
            "entry_date": entry_date,
            "entry_price": entry_price,
            "entry_action": str(o.get("initial_signal") or "").upper() or "HOLD",
            **signal_snap,
            "regime_at_entry": None,       # populated by regime enricher
            "sector_regime_at_entry": None,
            "market_breadth_at_entry": None,
            "vix_at_entry": None,
            "piotroski_f": None, "beneish_m": None, "altman_z": None,
            "sloan_accruals": None, "interest_coverage": None,
            "fcf_yield": None, "ev_ebitda": None, "total_shareholder_yield": None,
            "sector_rel_value_rank": None,
            "analyst_rev_momentum": None, "guidance_rev": None,
            "earnings_surprise": None, "insider_f4_signal": None,
            "inst_13f_change": None,
            "fii_dii_net_flow_z": None, "options_pcr": None,
            "short_interest_pct": None,
            "earnings_calendar_window": None, "promoter_pledge_pct": None,
            "exit_date": exit_date,
            "exit_price": exit_price,
            "exit_reason": closed_reason,
            "holding_days": holding_days,
            "realized_return_pct": realized_ret,
            "max_favorable_excursion": mfe,
            "max_adverse_excursion": mae,
            "was_stop_hit": "STOP" in closed_reason.upper(),
            "was_target_hit": "TARGET" in closed_reason.upper(),
            "was_horizon_expired": "HORIZON" in closed_reason.upper(),
            "is_administrative_exit": is_admin,
            "atr14_at_entry": atr,
            "dynamic_stop_at_entry": dyn_stop,
            "target_at_entry": target,
            "horizon_days_at_entry": 60,
            "source_snapshot_date": entry_date,
            "built_utc": now,
        }
        out_rows.append(row)

    if not out_rows:
        return {"market": market, "n_rows": 0, "note": "no registry rows"}

    df = pd.DataFrame(out_rows)
    df = df.drop_duplicates(subset=["position_id"], keep="last")
    df = df.sort_values(["entry_date", "ticker"]).reset_index(drop=True)

    out_dir = root / "reports" / "research" / "outcome_dataset"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{market}.parquet"
    df.to_parquet(p, index=False)

    # Summary — sample-size tier per runner and Phase-0 gate check
    closed = df[df["exit_date"].notna() & ~df["is_administrative_exit"]]
    by_runner = df.groupby("runner").size().to_dict()
    by_runner_closed = closed.groupby("runner").size().to_dict()
    total_closed = int(len(closed))

    def _tier(n):
        if n < 5: return "observation_only"
        if n < 15: return "hypothesis"
        if n < 30: return "research_signal"
        if n < 50: return "stronger_evidence"
        return "validation_candidate"

    tiers = {r: _tier(int(v)) for r, v in by_runner_closed.items()}

    phase0_gate = total_closed >= 50

    summary = {
        "market": market,
        "n_positions": int(len(df)),
        "n_closed_non_admin": total_closed,
        "n_by_runner_all": {str(k): int(v) for k, v in by_runner.items()},
        "n_by_runner_closed": {str(k): int(v) for k, v in by_runner_closed.items()},
        "sample_tiers_closed_by_runner": tiers,
        "phase0_gate_50_closed": phase0_gate,
        "phase0_gate_note": (
            "PASS · Outcome Dataset queryable + >=50 closed"
            if phase0_gate else
            f"BLOCKED · only {total_closed} non-admin closed positions · gate needs >=50"
        ),
        "parquet_path": str(p.relative_to(root)),
        "built_utc": now,
    }
    (out_dir / f"{market}.summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def load_outcome_dataset(root: Path, market: str):
    import pandas as pd
    p = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    summary = build_outcome_dataset(Path(args.root), args.market)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
