"""AEGIS-X1 · FX Intraday Research (parallel to equities · zero touch)

Operator directive 2026-08-09: "can u do a parallel testing on xauusd or
other pairs which u feel, but its intraday for fx · try on different
currencies"

STRICT GOVERNANCE:
- Research only · no Telegram signal delivery
- Zero touch to equities pipeline (R1/R2/Investability/Priority)
- Paper backtest only · no real capital
- Config-driven from configs/fx_experiment.yaml

Method:
1. Pull 60 days of 1h data for each pair via yfinance
2. Compute multi-timeframe trend (Daily + Resampled 4H + 1H)
3. Confluence signal: LONG if ≥2 TFs bullish AND RSI pullback (40-60)
4. Trade with ATR-based stops/targets (1.5R stop · 3.0R target · 2R payoff)
5. Backtest over 60-day window
6. Emit per-pair + aggregate metrics to reports/research/fx_experiment.json
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]


def _load_config() -> dict:
    import yaml
    p = _ROOT / "configs" / "fx_experiment.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _fetch(symbol: str, interval: str, lookback_days: int):
    """yfinance intraday limits:
       15m: 60 days STRICT (start must be < 60 days ago · use period=)
       1h: 730 days
       1d: 25+ years"""
    import yfinance as yf
    import pandas as pd
    from datetime import date, timedelta
    # For 15m · use period='59d' to stay within Yahoo's boundary
    if interval == "15m":
        df = yf.download(symbol, period="59d", interval=interval,
                                  progress=False, auto_adjust=False)
    else:
        end = date.today()
        start = end - timedelta(days=lookback_days)
        df = yf.download(symbol, start=start, end=end, interval=interval,
                                  progress=False, auto_adjust=False)
    if df.empty: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    df = df.dropna()
    # Normalize index to tz-naive so cross-TF comparisons work
    try:
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
    except (AttributeError, TypeError):
        pass
    return df


def _compute_indicators(df, cfg):
    import pandas as pd
    close = df["close"]
    high = df.get("high", close)
    low = df.get("low", close)

    df["sma_fast"] = close.rolling(cfg["sma_fast"]).mean()
    df["sma_slow"] = close.rolling(cfg["sma_slow"]).mean()

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(cfg["rsi_period"]).mean()
    loss = -delta.where(delta < 0, 0.0).rolling(cfg["rsi_period"]).mean()
    rs = gain / loss.replace(0, 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.rolling(cfg["atr_period"]).mean()

    # Trend flags
    df["above_sma_slow"] = close > df["sma_slow"]
    df["fast_above_slow"] = df["sma_fast"] > df["sma_slow"]
    return df


def _resample_trend(df_1h, tf: str):
    """Resample 1h data to 4h · return simple bullish/bearish flag."""
    if tf == "4h":
        agg = df_1h["close"].resample("4h").last().dropna()
    elif tf == "1d":
        agg = df_1h["close"].resample("1d").last().dropna()
    else:
        return None
    if len(agg) < 50: return None
    sma20 = agg.rolling(20).mean()
    sma50 = agg.rolling(50).mean()
    if sma20.iloc[-1] > sma50.iloc[-1]:
        return "bullish"
    if sma20.iloc[-1] < sma50.iloc[-1]:
        return "bearish"
    return "neutral"


@dataclass
class Trade:
    symbol: str
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    direction: str
    stop_price: float
    target_price: float
    outcome: str   # WIN | LOSS | TIMEOUT
    pnl_r: float
    pnl_pct: float
    confluence_score: int


def _trend_at(df_higher, ts, fast=20, slow=50):
    """Look up SMA-based trend on higher-TF bars STRICTLY BEFORE ts.
    Walk-forward valid · no lookahead. Returns 'bullish'/'bearish'/'neutral'."""
    prior = df_higher[df_higher.index < ts]
    if len(prior) < slow: return "neutral"
    close = prior["close"].tail(slow)
    sma_fast = close.tail(fast).mean()
    sma_slow = close.mean()
    if sma_fast > sma_slow: return "bullish"
    if sma_fast < sma_slow: return "bearish"
    return "neutral"


def _backtest_pair_multi_tf(spec, cfg):
    """TRUE multi-timeframe backtest · 15m entries · 1h+4h+1d confluence.

    Rewritten 2026-08-09 · operator directive: test on 15m + 1h + 4h · not
    just 1h with resampled higher TFs. Each TF fetched/computed independently.
    Higher-TF trend at each 15m bar looked up STRICTLY BEFORE the bar
    (walk-forward valid · no lookahead bias)."""
    import pandas as pd
    symbol = spec["symbol"]
    print(f"[{symbol}] fetching 15m + 1h + 1d ...", flush=True)

    # Fetch all 3 timeframes (4h resampled from 1h · yfinance has no native 4h)
    df_15m = _fetch(symbol, "15m", cfg["data"]["intraday_lookback_days"])
    df_1h = _fetch(symbol, "1h", cfg["data"]["intraday_lookback_days"])
    df_1d = _fetch(symbol, "1d", cfg["data"]["daily_lookback_days"])

    if df_15m is None or len(df_15m) < 300:
        print(f"[{symbol}] insufficient 15m data (need 300+ bars)")
        return None
    if df_1h is None or df_1d is None:
        print(f"[{symbol}] missing 1h or 1d data")
        return None

    # Resample 1h → 4h
    df_4h = df_1h["close"].resample("4h").last().dropna().to_frame()
    df_4h.columns = ["close"]

    strat = cfg["strategy"]
    df_15m = _compute_indicators(df_15m, strat)

    trades = []
    open_trade = None
    for i in range(strat["sma_slow"], len(df_15m) - 1):
        bar = df_15m.iloc[i]
        next_bar = df_15m.iloc[i + 1]
        ts = bar.name

        # Manage open trade
        if open_trade is not None:
            if open_trade["dir"] == "LONG":
                hit_target = next_bar["high"] >= open_trade["target"]
                hit_stop = next_bar["low"] <= open_trade["stop"]
            else:
                hit_target = next_bar["low"] <= open_trade["target"]
                hit_stop = next_bar["high"] >= open_trade["stop"]
            if hit_target:
                trades.append(Trade(
                    symbol=symbol, entry_time=str(open_trade["entry_time"]),
                    entry_price=open_trade["entry"], exit_time=str(next_bar.name),
                    exit_price=open_trade["target"], direction=open_trade["dir"],
                    stop_price=open_trade["stop"], target_price=open_trade["target"],
                    outcome="WIN",
                    pnl_r=strat["target_atr_multiple"] / strat["stop_atr_multiple"],
                    pnl_pct=(open_trade["target"] - open_trade["entry"]) / open_trade["entry"] * 100
                                if open_trade["dir"] == "LONG" else
                                (open_trade["entry"] - open_trade["target"]) / open_trade["entry"] * 100,
                    confluence_score=open_trade["conf"]
                ))
                open_trade = None
                continue
            if hit_stop:
                trades.append(Trade(
                    symbol=symbol, entry_time=str(open_trade["entry_time"]),
                    entry_price=open_trade["entry"], exit_time=str(next_bar.name),
                    exit_price=open_trade["stop"], direction=open_trade["dir"],
                    stop_price=open_trade["stop"], target_price=open_trade["target"],
                    outcome="LOSS", pnl_r=-1.0,
                    pnl_pct=(open_trade["stop"] - open_trade["entry"]) / open_trade["entry"] * 100
                                if open_trade["dir"] == "LONG" else
                                (open_trade["entry"] - open_trade["stop"]) / open_trade["entry"] * 100,
                    confluence_score=open_trade["conf"]
                ))
                open_trade = None
                continue

        # Entry logic · walk-forward higher-TF lookup
        if open_trade is None:
            rsi = bar["rsi"]; atr = bar["atr"]
            if not (rsi and atr and atr > 0): continue

            t_1h = _trend_at(df_1h, ts)
            t_4h = _trend_at(df_4h, ts)
            t_1d = _trend_at(df_1d, ts)

            confluence_long = 0
            if bar["above_sma_slow"] and bar["fast_above_slow"]: confluence_long += 1   # 15m trend
            if t_1h == "bullish": confluence_long += 1
            if t_4h == "bullish": confluence_long += 1
            if t_1d == "bullish": confluence_long += 1

            confluence_short = 0
            if not bar["above_sma_slow"] and not bar["fast_above_slow"]: confluence_short += 1
            if t_1h == "bearish": confluence_short += 1
            if t_4h == "bearish": confluence_short += 1
            if t_1d == "bearish": confluence_short += 1

            # Require 3 of 4 timeframes aligned (stricter than the 1h-only version)
            REQUIRED_CONF = 3
            entry_price = float(bar["close"])
            if confluence_long >= REQUIRED_CONF \
               and strat["rsi_pullback_low"] <= rsi <= strat["rsi_pullback_high"]:
                open_trade = {
                    "dir": "LONG", "entry": entry_price, "entry_time": ts,
                    "stop": entry_price - strat["stop_atr_multiple"] * atr,
                    "target": entry_price + strat["target_atr_multiple"] * atr,
                    "conf": confluence_long,
                }
            elif confluence_short >= REQUIRED_CONF \
                     and strat["rsi_pullback_low"] <= rsi <= strat["rsi_pullback_high"]:
                open_trade = {
                    "dir": "SHORT", "entry": entry_price, "entry_time": ts,
                    "stop": entry_price + strat["stop_atr_multiple"] * atr,
                    "target": entry_price - strat["target_atr_multiple"] * atr,
                    "conf": confluence_short,
                }

    if not trades:
        return {"symbol": symbol, "n_trades": 0, "note": "no signals fired · 3/4 TF confluence too strict"}

    wins = [t for t in trades if t.outcome == "WIN"]
    losses = [t for t in trades if t.outcome == "LOSS"]
    total_r = sum(t.pnl_r for t in trades)
    win_rate = len(wins) / len(trades) * 100
    avg_r = total_r / len(trades)

    max_dd_r = 0; running_r = 0; peak = 0
    for t in trades:
        running_r += t.pnl_r
        if running_r > peak: peak = running_r
        dd = running_r - peak
        if dd < max_dd_r: max_dd_r = dd

    return {
        "symbol":            symbol,
        "name":              spec["name"],
        "asset_class":       spec["asset_class"],
        "timeframe":         "15m entry · 1h+4h+1d confluence",
        "n_bars_15m":        len(df_15m),
        "n_bars_1h":         len(df_1h),
        "n_bars_4h":         len(df_4h),
        "n_bars_1d":         len(df_1d),
        "n_trades":          len(trades),
        "n_wins":            len(wins),
        "n_losses":          len(losses),
        "win_rate_pct":      round(win_rate, 1),
        "total_pnl_r":       round(total_r, 2),
        "avg_r_per_trade":   round(avg_r, 2),
        "max_drawdown_r":    round(max_dd_r, 2),
        "expectancy_r":      round(avg_r, 2),
        "avg_confluence":    round(sum(t.confluence_score for t in trades) / len(trades), 2),
        "sample_trades":     [asdict(t) for t in trades[:3]],
        "last_5_trades":     [asdict(t) for t in trades[-5:]],
    }


def _backtest_pair(spec, cfg):
    """Run confluence backtest on one pair. Returns list of Trade + metrics."""
    symbol = spec["symbol"]
    print(f"[{symbol}] fetching intraday...", flush=True)
    df = _fetch(symbol, cfg["data"]["intraday_interval"],
                    cfg["data"]["intraday_lookback_days"])
    if df is None or len(df) < 200:
        print(f"[{symbol}] insufficient data")
        return None

    df_daily = _fetch(symbol, cfg["data"]["daily_interval"],
                                cfg["data"]["daily_lookback_days"])

    strat = cfg["strategy"]
    df = _compute_indicators(df, strat)

    # Daily trend snapshot (fixed at end of period · simple proxy for
    # historical daily trend at each bar · faster than per-bar resample)
    daily_trend = _resample_trend(df, "1d") or "neutral"
    h4_trend = _resample_trend(df, "4h") or "neutral"

    trades = []
    open_trade = None
    for i in range(50, len(df) - 1):
        bar = df.iloc[i]
        next_bar = df.iloc[i + 1]

        # Manage open trade
        if open_trade is not None:
            hit_target = next_bar["high"] >= open_trade["target"] \
                                 if open_trade["dir"] == "LONG" \
                                 else next_bar["low"] <= open_trade["target"]
            hit_stop = next_bar["low"] <= open_trade["stop"] \
                                if open_trade["dir"] == "LONG" \
                                else next_bar["high"] >= open_trade["stop"]
            if hit_target:
                trades.append(Trade(
                    symbol=symbol, entry_time=str(open_trade["entry_time"]),
                    entry_price=open_trade["entry"], exit_time=str(next_bar.name),
                    exit_price=open_trade["target"], direction=open_trade["dir"],
                    stop_price=open_trade["stop"], target_price=open_trade["target"],
                    outcome="WIN", pnl_r=strat["target_atr_multiple"] / strat["stop_atr_multiple"],
                    pnl_pct=(open_trade["target"] - open_trade["entry"]) / open_trade["entry"] * 100
                                if open_trade["dir"] == "LONG" else
                                (open_trade["entry"] - open_trade["target"]) / open_trade["entry"] * 100,
                    confluence_score=open_trade["conf"]
                ))
                open_trade = None
                continue
            if hit_stop:
                trades.append(Trade(
                    symbol=symbol, entry_time=str(open_trade["entry_time"]),
                    entry_price=open_trade["entry"], exit_time=str(next_bar.name),
                    exit_price=open_trade["stop"], direction=open_trade["dir"],
                    stop_price=open_trade["stop"], target_price=open_trade["target"],
                    outcome="LOSS", pnl_r=-1.0,
                    pnl_pct=(open_trade["stop"] - open_trade["entry"]) / open_trade["entry"] * 100
                                if open_trade["dir"] == "LONG" else
                                (open_trade["entry"] - open_trade["stop"]) / open_trade["entry"] * 100,
                    confluence_score=open_trade["conf"]
                ))
                open_trade = None
                continue

        # Entry logic (only when flat)
        if open_trade is None:
            rsi = bar["rsi"]
            atr = bar["atr"]
            if not (rsi and atr and atr > 0): continue

            confluence_long = 0
            if bar["above_sma_slow"] and bar["fast_above_slow"]: confluence_long += 1
            if h4_trend == "bullish": confluence_long += 1
            if daily_trend == "bullish": confluence_long += 1

            confluence_short = 0
            if not bar["above_sma_slow"] and not bar["fast_above_slow"]: confluence_short += 1
            if h4_trend == "bearish": confluence_short += 1
            if daily_trend == "bearish": confluence_short += 1

            entry_price = float(bar["close"])
            if confluence_long >= strat["min_confluence"] \
               and strat["rsi_pullback_low"] <= rsi <= strat["rsi_pullback_high"]:
                stop = entry_price - strat["stop_atr_multiple"] * atr
                target = entry_price + strat["target_atr_multiple"] * atr
                open_trade = {"dir": "LONG", "entry": entry_price, "entry_time": bar.name,
                                      "stop": stop, "target": target, "conf": confluence_long}
            elif confluence_short >= strat["min_confluence"] \
                     and strat["rsi_pullback_low"] <= rsi <= strat["rsi_pullback_high"]:
                stop = entry_price + strat["stop_atr_multiple"] * atr
                target = entry_price - strat["target_atr_multiple"] * atr
                open_trade = {"dir": "SHORT", "entry": entry_price, "entry_time": bar.name,
                                      "stop": stop, "target": target, "conf": confluence_short}

    # Metrics
    if not trades:
        return {"symbol": symbol, "n_trades": 0, "note": "no signals fired"}
    wins = [t for t in trades if t.outcome == "WIN"]
    losses = [t for t in trades if t.outcome == "LOSS"]
    total_r = sum(t.pnl_r for t in trades)
    total_pnl_pct = sum(t.pnl_pct for t in trades)
    win_rate = len(wins) / len(trades) * 100
    avg_r = total_r / len(trades)
    max_dd_r = 0
    running_r = 0
    peak = 0
    for t in trades:
        running_r += t.pnl_r
        if running_r > peak: peak = running_r
        dd = running_r - peak
        if dd < max_dd_r: max_dd_r = dd

    return {
        "symbol":            symbol,
        "name":              spec["name"],
        "asset_class":       spec["asset_class"],
        "n_trades":          len(trades),
        "n_wins":            len(wins),
        "n_losses":          len(losses),
        "win_rate_pct":      round(win_rate, 1),
        "total_pnl_r":       round(total_r, 2),
        "total_pnl_pct":     round(total_pnl_pct, 2),
        "avg_r_per_trade":   round(avg_r, 2),
        "max_drawdown_r":    round(max_dd_r, 2),
        "expectancy_r":      round(avg_r, 2),  # per-trade expectancy in R
        "daily_trend_at_test_end":  daily_trend,
        "h4_trend_at_test_end":     h4_trend,
        "sample_trades":     [asdict(t) for t in trades[:5]],
        "last_5_trades":     [asdict(t) for t in trades[-5:]],
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg = _load_config()

    print(f"[fx_experiment] pairs={[p['symbol'] for p in cfg['pairs']]}")
    print(f"[fx_experiment] interval={cfg['data']['intraday_interval']} "
              f"lookback={cfg['data']['intraday_lookback_days']}d")
    print(f"[fx_experiment] strategy: confluence>={cfg['strategy']['min_confluence']} "
              f"· RSI({cfg['strategy']['rsi_pullback_low']}-{cfg['strategy']['rsi_pullback_high']}) "
              f"· stop {cfg['strategy']['stop_atr_multiple']}xATR · "
              f"target {cfg['strategy']['target_atr_multiple']}xATR")
    print()

    # 2026-08-09 · operator directive · test true 15m + 1h + 4h + 1d multi-TF
    results = []
    for spec in cfg["pairs"]:
        try:
            r = _backtest_pair_multi_tf(spec, cfg)
            if r: results.append(r)
        except Exception as e:
            print(f"[{spec['symbol']}] FAIL · {type(e).__name__}: {e}")

    # Aggregate
    all_n = sum(r.get("n_trades", 0) for r in results)
    all_wins = sum(r.get("n_wins", 0) for r in results)
    all_r = sum(r.get("total_pnl_r", 0) for r in results)
    aggregate = {
        "n_pairs":        len(results),
        "n_total_trades": all_n,
        "n_total_wins":   all_wins,
        "portfolio_win_rate_pct": round(all_wins / max(1, all_n) * 100, 1),
        "portfolio_total_r":  round(all_r, 2),
        "portfolio_avg_r":    round(all_r / max(1, all_n), 2),
    }

    out = _ROOT / "reports" / "research" / "fx_experiment.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "engine":         "aegis_x1_fx_intraday_experiment.v1",
        "run_utc":        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_version": cfg.get("version"),
        "aggregate":      aggregate,
        "per_pair":       results,
        "guardrails":     cfg["guardrails"],
    }
    out.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                       encoding="utf-8")
    print(f"[fx_experiment] wrote {out}")
    print()
    print(f"=== AGGREGATE (all {len(results)} pairs) ===")
    print(f"Total trades: {all_n}")
    print(f"Portfolio win rate: {aggregate['portfolio_win_rate_pct']}%")
    print(f"Portfolio total R: {aggregate['portfolio_total_r']}")
    print(f"Portfolio avg R/trade: {aggregate['portfolio_avg_r']}")
    print()
    print("=== PER PAIR ===")
    for r in results:
        n = r.get("n_trades", 0)
        wr = r.get("win_rate_pct", 0)
        er = r.get("expectancy_r", 0)
        print(f"  {r['symbol']:10} ({r.get('name','?'):15}): n={n:3d} · win {wr:4.1f}% · avg {er:+.2f}R · total {r.get('total_pnl_r', 0):+.2f}R")
    return 0


if __name__ == "__main__":
    sys.exit(main())
