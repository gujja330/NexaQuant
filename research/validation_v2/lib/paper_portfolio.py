"""Validation Engine v2.0 · paper-portfolio ledger.

Deterministic paper-trading ledger. Every open position, close, and
mark-to-market event is content-addressed and append-only.

Not a broker adapter. Never executes real trades. The purpose is to
maintain a live shadow portfolio whose realised outcomes can be
reconciled against DEV023 recommendations."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd


_ROOT = Path(__file__).resolve().parents[3]
LEDGER_DIR = _ROOT / "data" / "market_intelligence" / "derived" / "validation_v2"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)

POSITIONS_PATH = LEDGER_DIR / "paper_positions.parquet"
TRADES_PATH    = LEDGER_DIR / "paper_trades.parquet"
MTM_PATH       = LEDGER_DIR / "paper_mtm.parquet"


@dataclass
class PaperTrade:
    trade_id:      str            # content hash
    action:        str            # OPEN | CLOSE | ADJUST
    ticker:        str
    entry_date:    str
    exit_date:     str | None
    entry_price:   float
    exit_price:    float | None
    weight:        float
    rec_type:      str            # Strong-Buy / Buy / Hold / etc.
    rec_source:    str            # v1.4 | v2.0
    return_pct:    float | None
    holding_days:  int | None
    reason_close:  str | None
    committed_at:  str            # ISO UTC


def _content_id(payload: dict) -> str:
    stable = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]


def _load(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


def _append(path: Path, df: pd.DataFrame) -> None:
    if path.exists():
        try:
            old = pd.read_parquet(path)
            combined = pd.concat([old, df], ignore_index=True)
        except Exception:
            combined = df
    else:
        combined = df
    combined.to_parquet(path, index=False)


def open_position(ticker: str, entry_price: float, weight: float,
                     rec_type: str, rec_source: str,
                     entry_date: str | None = None) -> PaperTrade:
    entry_date = entry_date or date.today().isoformat()
    payload = {
        "action":       "OPEN",
        "ticker":       ticker,
        "entry_date":   entry_date,
        "entry_price":  round(float(entry_price), 4),
        "weight":       round(float(weight), 5),
        "rec_type":     rec_type,
        "rec_source":   rec_source,
    }
    tid = _content_id(payload)
    trade = PaperTrade(
        trade_id=tid,
        action="OPEN",
        ticker=ticker,
        entry_date=entry_date,
        exit_date=None,
        entry_price=round(float(entry_price), 4),
        exit_price=None,
        weight=round(float(weight), 5),
        rec_type=rec_type,
        rec_source=rec_source,
        return_pct=None,
        holding_days=None,
        reason_close=None,
        committed_at=datetime.now(timezone.utc).isoformat(),
    )

    # Dedup: if a trade with the same content id already exists, skip
    existing = _load(TRADES_PATH)
    if not existing.empty and (existing["trade_id"] == tid).any():
        return trade

    _append(TRADES_PATH, pd.DataFrame([asdict(trade)]))
    _refresh_open_positions()
    return trade


def close_position(ticker: str, exit_price: float, reason: str,
                       exit_date: str | None = None) -> PaperTrade | None:
    exit_date = exit_date or date.today().isoformat()
    trades = _load(TRADES_PATH)
    if trades.empty:
        return None

    open_mask = (trades["ticker"] == ticker) & (trades["action"] == "OPEN")
    if not open_mask.any():
        return None
    open_trade = trades[open_mask].sort_values("committed_at").iloc[-1]

    # Skip if already closed
    close_mask = (trades["ticker"] == ticker) & (trades["action"] == "CLOSE") \
                    & (trades["entry_date"] == open_trade["entry_date"])
    if close_mask.any():
        return None

    entry_price = float(open_trade["entry_price"])
    ret = (float(exit_price) - entry_price) / entry_price
    holding = (pd.Timestamp(exit_date) - pd.Timestamp(open_trade["entry_date"])).days

    payload = {
        "action":       "CLOSE",
        "ticker":       ticker,
        "entry_date":   open_trade["entry_date"],
        "exit_date":    exit_date,
        "exit_price":   round(float(exit_price), 4),
        "reason":       reason,
    }
    tid = _content_id(payload)

    trade = PaperTrade(
        trade_id=tid, action="CLOSE",
        ticker=ticker,
        entry_date=str(open_trade["entry_date"]),
        exit_date=exit_date,
        entry_price=entry_price,
        exit_price=round(float(exit_price), 4),
        weight=float(open_trade["weight"]),
        rec_type=str(open_trade["rec_type"]),
        rec_source=str(open_trade["rec_source"]),
        return_pct=round(ret, 6),
        holding_days=int(holding),
        reason_close=reason,
        committed_at=datetime.now(timezone.utc).isoformat(),
    )
    _append(TRADES_PATH, pd.DataFrame([asdict(trade)]))
    _refresh_open_positions()
    return trade


def _refresh_open_positions() -> None:
    trades = _load(TRADES_PATH)
    if trades.empty:
        return
    opens = trades[trades["action"] == "OPEN"]
    closes = trades[trades["action"] == "CLOSE"]
    closed_keys = set(zip(closes["ticker"].astype(str),
                             closes["entry_date"].astype(str)))
    still_open = opens[~opens.apply(lambda r: (str(r["ticker"]), str(r["entry_date"])) in closed_keys,
                                        axis=1)]
    still_open = still_open[["ticker", "entry_date", "entry_price", "weight",
                                "rec_type", "rec_source"]].reset_index(drop=True)
    still_open.to_parquet(POSITIONS_PATH, index=False)


def open_positions() -> pd.DataFrame:
    return _load(POSITIONS_PATH)


def closed_trades() -> pd.DataFrame:
    trades = _load(TRADES_PATH)
    if trades.empty:
        return pd.DataFrame()
    return trades[trades["action"] == "CLOSE"].reset_index(drop=True)


def mark_to_market(prices_by_ticker: dict[str, float],
                       as_of: str | None = None) -> pd.DataFrame:
    as_of = as_of or date.today().isoformat()
    positions = open_positions()
    if positions.empty:
        return pd.DataFrame()

    rows = []
    for _, pos in positions.iterrows():
        mark = prices_by_ticker.get(pos["ticker"])
        if mark is None:
            continue
        pnl_pct = (float(mark) - float(pos["entry_price"])) / float(pos["entry_price"])
        rows.append({
            "as_of":         as_of,
            "ticker":        pos["ticker"],
            "entry_date":    pos["entry_date"],
            "entry_price":   float(pos["entry_price"]),
            "mark_price":    float(mark),
            "weight":        float(pos["weight"]),
            "pnl_pct":       round(pnl_pct, 6),
            "weighted_pnl":  round(pnl_pct * float(pos["weight"]), 6),
            "rec_type":      pos["rec_type"],
            "rec_source":    pos["rec_source"],
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    _append(MTM_PATH, df)
    return df


def mtm_history() -> pd.DataFrame:
    return _load(MTM_PATH)
