"""Intraday backtest runner · replays historical bars through the full stack.

Runs signals → ensemble → classifier → risk → simulator on each session,
emits per-window + per-slot metrics.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from ..signals import SIGNAL_REGISTRY, SignalScore
from ..ensemble import default_weights, blend_signals, classify
from ..risk import SessionRiskManager
from ..execution import ExecutionSimulator, SessionState, Position
from ..session_clock import SessionWindow, TradingSlot, window_for_time, slot_for_time


@dataclass
class BacktestResult:
    market:            str
    n_sessions:        int
    n_trades:          int
    n_winners:         int
    n_losers:          int
    total_pnl:         float
    win_rate:          float
    avg_winner:        float
    avg_loser:         float
    profit_factor:     float | None
    by_slot:           dict = field(default_factory=dict)
    by_window:         dict = field(default_factory=dict)
    by_signal:         dict = field(default_factory=dict)
    trades:            list = field(default_factory=list)
    run_utc:           str = ""
    market_note:       str = ""


def _profit_factor(pnls) -> float | None:
    wins = sum(p for p in pnls if p > 0)
    losses = abs(sum(p for p in pnls if p < 0))
    if losses == 0:
        return None
    return round(wins / losses, 3)


def _instantiate_signals() -> list:
    return [cls() for cls in SIGNAL_REGISTRY.values()]


def run_intraday_backtest(root: Path, market: str, tickers: list[str],
                              interval: str = "15m",
                              session_capital: float = 100_000.0) -> BacktestResult:
    """Backtest across whatever intraday bars we have cached for each ticker.
    Grouped by session_date · one pass per session · uses `interval` cache."""
    try:
        import pandas as pd
    except ImportError:
        return BacktestResult(market=market, n_sessions=0, n_trades=0,
                                n_winners=0, n_losers=0, total_pnl=0.0,
                                win_rate=0.0, avg_winner=0.0, avg_loser=0.0,
                                profit_factor=None,
                                market_note="pandas_unavailable",
                                run_utc=datetime.now(timezone.utc).isoformat())

    from ..feed.yfinance_adapter import load_cached_bars
    signals = _instantiate_signals()
    weights = default_weights(root)
    ex = ExecutionSimulator(market=market)

    all_trades: list[dict] = []
    n_sessions = 0
    session_dates_seen: set = set()

    for ticker in tickers:
        df = load_cached_bars(root, ticker, market, interval)      # honor requested interval
        if df is None or df.empty:
            df = load_cached_bars(root, ticker, market, "5m")     # fallback
        if df is None or df.empty:
            continue
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        by_session = df.groupby(df.index.date)
        for sess_date, sess_bars in by_session:
            if len(sess_bars) < 10:
                continue
            session_dates_seen.add(sess_date)
            # Progressive: for each bar, use bars up to that bar as history
            for i in range(5, len(sess_bars)):
                window_bars = sess_bars.iloc[: i + 1]
                ts = window_bars.index[-1]
                w = window_for_time(market, ts.to_pydatetime()
                                        if hasattr(ts, "to_pydatetime") else ts)
                slot = slot_for_time(market, ts.to_pydatetime()
                                       if hasattr(ts, "to_pydatetime") else ts)
                if slot == TradingSlot.OFF_SESSION:
                    continue
                # Only entry-allowed slots
                if slot == TradingSlot.SQUARE_OFF:
                    break
                meta = {"ticker": ticker, "market": market, "window": w.value,
                        "slot": slot.value}
                scores = []
                for sig in signals:
                    if not sig.is_active(slot, w):
                        continue
                    s = sig.compute(window_bars, meta)
                    if s is not None:
                        scores.append(s)
                if not scores:
                    continue
                blended = blend_signals(scores, weights=weights)
                classified = classify(blended)
                rec = classified.get(ticker) or {}
                if rec.get("action") not in ("STRONG_LONG", "LONG", "STRONG_SHORT", "SHORT"):
                    continue
                # Pick the highest-magnitude signal as trade template
                lead = max(scores, key=lambda s: abs(s.score))
                # Look ahead within same session to determine outcome
                lookahead = sess_bars.iloc[i + 1:]
                if lookahead.empty:
                    continue
                exit_price = None
                exit_reason = "time_stop"
                for j, bar in lookahead.iterrows():
                    high = float(bar["high"]); low = float(bar["low"])
                    if lead.direction == "LONG":
                        if low <= lead.stop:
                            exit_price = lead.stop
                            exit_reason = "stop_hit"; break
                        if high >= lead.target_2:
                            exit_price = lead.target_2
                            exit_reason = "target_2_hit"; break
                    else:
                        if high >= lead.stop:
                            exit_price = lead.stop
                            exit_reason = "stop_hit"; break
                        if low <= lead.target_2:
                            exit_price = lead.target_2
                            exit_reason = "target_2_hit"; break
                if exit_price is None:
                    exit_price = float(lookahead.iloc[-1]["close"])
                pnl_pct = ((exit_price / lead.entry - 1) * 100
                              if lead.direction == "LONG"
                              else (lead.entry / exit_price - 1) * 100)
                all_trades.append({
                    "session":     str(sess_date),
                    "ticker":      ticker,
                    "signal":      lead.signal_id,
                    "direction":   lead.direction,
                    "entry":       round(lead.entry, 3),
                    "exit":        round(exit_price, 3),
                    "pnl_pct":     round(pnl_pct, 3),
                    "exit_reason": exit_reason,
                    "slot":        slot.value,
                    "window":      w.value,
                })
                break     # one trade per session per ticker for backtest scoring

    n_sessions = len(session_dates_seen)
    pnls = [t["pnl_pct"] for t in all_trades]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p < 0]

    by_slot: dict = {}
    for t in all_trades:
        by_slot.setdefault(t["slot"], []).append(t["pnl_pct"])
    slot_summary = {s: {"n": len(v),
                          "win_rate": round(sum(1 for p in v if p > 0) / max(1, len(v)), 3),
                          "avg_pnl_pct": round(sum(v) / len(v), 3) if v else 0}
                      for s, v in by_slot.items()}

    by_window: dict = {}
    for t in all_trades:
        by_window.setdefault(t["window"], []).append(t["pnl_pct"])
    window_summary = {w: {"n": len(v),
                            "win_rate": round(sum(1 for p in v if p > 0) / max(1, len(v)), 3),
                            "avg_pnl_pct": round(sum(v) / len(v), 3) if v else 0}
                        for w, v in by_window.items()}

    by_signal: dict = {}
    for t in all_trades:
        by_signal.setdefault(t["signal"], []).append(t["pnl_pct"])
    signal_summary = {s: {"n": len(v),
                            "win_rate": round(sum(1 for p in v if p > 0) / max(1, len(v)), 3),
                            "avg_pnl_pct": round(sum(v) / len(v), 3) if v else 0}
                        for s, v in by_signal.items()}

    result = BacktestResult(
        market=market, n_sessions=n_sessions, n_trades=len(all_trades),
        n_winners=len(winners), n_losers=len(losers),
        total_pnl=round(sum(pnls), 3),
        win_rate=round(len(winners) / max(1, len(pnls)), 4),
        avg_winner=round(sum(winners) / len(winners), 3) if winners else 0.0,
        avg_loser=round(sum(losers) / len(losers), 3) if losers else 0.0,
        profit_factor=_profit_factor(pnls),
        by_slot=slot_summary, by_window=window_summary, by_signal=signal_summary,
        trades=all_trades[:200],
        run_utc=datetime.now(timezone.utc).isoformat(),
        market_note="backtest uses cached intraday bars (yfinance) · no live-feed dependency",
    )
    out_dir = root / "reports" / "intraday"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"backtest_{market}.json").write_text(
        json.dumps(asdict(result), indent=2, default=str, ensure_ascii=False),
        encoding="utf-8")
    return result
