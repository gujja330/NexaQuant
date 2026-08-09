"""AEGIS-X1 V2 · Full-stack FX/Crypto research engine.

Answers: "Does the strategy have edge across multiple regimes with
realistic costs and macro-aware entry filtering?"

Components:
  · Data ingest (primary + cross-market)
  · Regime classifier (4-state · ADX + ATR)
  · Cross-market context (DXY · yields · VIX · S&P)
  · Regime-adaptive strategy (trend-follow vs mean-revert)
  · Realistic cost model (spread + commission + slippage per asset class)
  · Walk-forward backtest with per-regime metrics
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict


# ═══════════════════════════════════════════════════════════════════════
# Data ingest
# ═══════════════════════════════════════════════════════════════════════
def fetch(symbol: str, interval: str, lookback_days: int):
    """yfinance fetch with tz-naive normalization."""
    import yfinance as yf
    from datetime import date, timedelta
    if interval == "15m":
        df = yf.download(symbol, period="59d", interval=interval,
                                  progress=False, auto_adjust=False)
    elif interval == "1h" and lookback_days > 700:
        df = yf.download(symbol, period="720d", interval=interval,
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
    try:
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
    except (AttributeError, TypeError):
        pass
    return df


# ═══════════════════════════════════════════════════════════════════════
# Indicators
# ═══════════════════════════════════════════════════════════════════════
def add_indicators(df, cfg):
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

    # ATR + True Range
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["tr"] = tr
    df["atr"] = tr.rolling(14).mean()

    # ADX (14-period · standard Wilder-style approximation)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)
    atr_14 = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr_14.replace(0, 1e-10))
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr_14.replace(0, 1e-10))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10)
    df["adx"] = dx.rolling(14).mean()
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    # ATR percentile (rolling 500-bar)
    df["atr_pctl"] = df["atr"].rolling(500).apply(
        lambda x: (x.iloc[-1] > x).sum() / len(x) * 100 if len(x) > 0 else 50)

    return df


# ═══════════════════════════════════════════════════════════════════════
# Regime classifier
# ═══════════════════════════════════════════════════════════════════════
def classify_regime(row, regime_cfg):
    """4-state classifier per bar."""
    adx = row.get("adx")
    atr_pctl = row.get("atr_pctl", 50)
    close = row.get("close", 0)
    sma_slow = row.get("sma_slow", 0)

    if pd.isna(adx) or pd.isna(atr_pctl):
        return "UNKNOWN"

    # High-vol regime (danger zone · no trade)
    if atr_pctl >= regime_cfg["vol_high_percentile"]:
        return "HIGH_VOL"

    # Trending
    if adx >= regime_cfg["adx_trending_threshold"]:
        if close > sma_slow:
            return "TRENDING_UP"
        return "TRENDING_DOWN"

    # Ranging (low ADX · price near mean)
    if adx <= regime_cfg["adx_ranging_threshold"]:
        return "RANGING"

    return "TRANSITION"  # ADX between 20-25 · unclear


# ═══════════════════════════════════════════════════════════════════════
# Cross-market context
# ═══════════════════════════════════════════════════════════════════════
def build_cross_market(cfg):
    """Fetch DXY · 10Y · VIX · S&P daily bars · return {symbol: df}."""
    xm = {}
    for key, sym in cfg["cross_market"].items():
        df = fetch(sym, "1d", cfg["data"]["daily_lookback_days"])
        if df is None or df.empty:
            print(f"[cross_market] {key}={sym} FETCH FAILED")
            continue
        xm[key] = df
    return xm


def cross_market_context(ts, xm, cfg):
    """Compute risk-on/off flag at a specific timestamp."""
    ctx = {"risk_state": "neutral", "vix": None, "dxy_5d_pct": None,
               "yield_5d_pct": None, "sp500_trend": "unknown"}
    ctx_cfg = cfg["context"]

    for key, df in xm.items():
        prior = df[df.index < ts]
        if len(prior) < 10: continue
        last = prior["close"].iloc[-1]
        earlier = prior["close"].iloc[-5] if len(prior) >= 5 else last
        pct_5d = ((last - earlier) / earlier * 100) if earlier else 0
        if key == "vix":
            ctx["vix"] = float(last)
        elif key == "dxy":
            ctx["dxy_5d_pct"] = round(pct_5d, 2)
        elif key == "us_10y":
            ctx["yield_5d_pct"] = round(pct_5d, 2)
        elif key == "sp500":
            sma_20 = prior["close"].tail(20).mean() if len(prior) >= 20 else last
            ctx["sp500_trend"] = "up" if last > sma_20 else "down"

    # Aggregate risk state
    risk_off = 0
    if ctx["vix"] is not None and ctx["vix"] > ctx_cfg["vix_stress_min"]: risk_off += 1
    if ctx["yield_5d_pct"] is not None and ctx["yield_5d_pct"] > ctx_cfg["yield_spike_pct"]: risk_off += 1
    if ctx["dxy_5d_pct"] is not None and ctx["dxy_5d_pct"] > ctx_cfg["dxy_strong_pct"]: risk_off += 1
    if ctx["sp500_trend"] == "down": risk_off += 1

    risk_on = 0
    if ctx["vix"] is not None and ctx["vix"] < ctx_cfg["vix_calm_max"]: risk_on += 1
    if ctx["sp500_trend"] == "up": risk_on += 1

    if risk_off >= 2:
        ctx["risk_state"] = "off"
    elif risk_on >= 2 and risk_off == 0:
        ctx["risk_state"] = "on"
    return ctx


def trend_at(df, ts, fast=20, slow=50):
    """Walk-forward higher-TF trend lookup · strictly before ts."""
    prior = df[df.index < ts]
    if len(prior) < slow: return "neutral"
    close = prior["close"].tail(slow)
    if close.tail(fast).mean() > close.mean(): return "bullish"
    if close.tail(fast).mean() < close.mean(): return "bearish"
    return "neutral"


# ═══════════════════════════════════════════════════════════════════════
# Cost model
# ═══════════════════════════════════════════════════════════════════════
def apply_costs(entry_price, exit_price, direction, spec, cost_cfg):
    """Return net PnL % after spread + commission + slippage."""
    asset_class = spec["class"]
    spread_pips = spec["spread_pips"]
    pip_size = spec["pip_size"]

    # Spread cost (paid on entry)
    spread_cost_price = spread_pips * pip_size
    # Commission bps per side (entry + exit)
    commission_bps = cost_cfg["commission_bps"].get(asset_class, 5.0)
    # Slippage bps per side
    slippage_bps = cost_cfg["slippage_bps"].get(asset_class, 1.0)

    # Gross return
    if direction == "LONG":
        gross_pct = (exit_price - entry_price) / entry_price * 100
    else:
        gross_pct = (entry_price - exit_price) / entry_price * 100

    # Deduct spread as % of entry
    spread_pct = spread_cost_price / entry_price * 100
    # Deduct commission (round-trip in bps · convert to %)
    comm_pct = (commission_bps * 2) / 100.0
    # Deduct slippage (both sides)
    slip_pct = (slippage_bps * 2) / 100.0

    return gross_pct - spread_pct - comm_pct - slip_pct


# ═══════════════════════════════════════════════════════════════════════
# Trade dataclass
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class Trade:
    symbol: str
    strategy: str      # "trend_follow" | "mean_revert"
    regime_at_entry: str
    risk_state:      str
    entry_time:  str
    entry_price: float
    exit_time:   str
    exit_price:  float
    direction:   str
    outcome:     str
    gross_pnl_pct: float
    net_pnl_pct:   float
    r_multiple:    float


# ═══════════════════════════════════════════════════════════════════════
# Regime-adaptive backtest
# ═══════════════════════════════════════════════════════════════════════
def backtest_pair(spec, cfg, xm):
    """Full regime-adaptive backtest for one pair."""
    symbol = spec["symbol"]
    print(f"[{symbol}] fetching {cfg['data']['primary_lookback_days']}d of 1h + 2yr daily...", flush=True)

    df_1h = fetch(symbol, "1h", cfg["data"]["primary_lookback_days"])
    df_1d = fetch(symbol, "1d", cfg["data"]["daily_lookback_days"])

    if df_1h is None or len(df_1h) < cfg["data"]["min_bars_required"]:
        print(f"[{symbol}] insufficient 1h data")
        return None
    if df_1d is None:
        print(f"[{symbol}] no daily context")
        return None

    df_4h = df_1h["close"].resample("4h").last().dropna().to_frame()
    df_4h.columns = ["close"]

    strat = cfg["strategy"]
    df_1h = add_indicators(df_1h, strat)

    trades = []
    open_trade = None

    for i in range(strat["sma_slow"], len(df_1h) - 1):
        bar = df_1h.iloc[i]
        next_bar = df_1h.iloc[i + 1]
        ts = bar.name

        # Manage open trade
        if open_trade is not None:
            if open_trade["dir"] == "LONG":
                hit_target = next_bar["high"] >= open_trade["target"]
                hit_stop = next_bar["low"] <= open_trade["stop"]
            else:
                hit_target = next_bar["low"] <= open_trade["target"]
                hit_stop = next_bar["high"] >= open_trade["stop"]

            exit_at = None
            outcome = None
            if hit_target:
                exit_at = open_trade["target"]; outcome = "WIN"
            elif hit_stop:
                exit_at = open_trade["stop"]; outcome = "LOSS"

            if exit_at is not None:
                net_pct = apply_costs(open_trade["entry"], exit_at,
                                                  open_trade["dir"], spec, cfg["costs"])
                gross_pct = ((exit_at - open_trade["entry"]) / open_trade["entry"] * 100
                                     if open_trade["dir"] == "LONG"
                                     else (open_trade["entry"] - exit_at) / open_trade["entry"] * 100)
                # R-multiple based on stop distance
                stop_dist = abs(open_trade["entry"] - open_trade["stop"])
                target_dist = abs(open_trade["entry"] - open_trade["target"])
                r_mult = target_dist / stop_dist if outcome == "WIN" else -1.0

                trades.append(Trade(
                    symbol=symbol, strategy=open_trade["strat"],
                    regime_at_entry=open_trade["regime"],
                    risk_state=open_trade["risk"],
                    entry_time=str(open_trade["entry_time"]),
                    entry_price=open_trade["entry"],
                    exit_time=str(next_bar.name), exit_price=exit_at,
                    direction=open_trade["dir"], outcome=outcome,
                    gross_pnl_pct=round(gross_pct, 3),
                    net_pnl_pct=round(net_pct, 3),
                    r_multiple=round(r_mult, 2)
                ))
                open_trade = None
                continue

        # Entry logic
        if open_trade is None:
            regime = classify_regime(bar, cfg["regime"])
            if regime in ("HIGH_VOL", "UNKNOWN", "TRANSITION"):
                continue    # no trade in dangerous or unclear regime

            # Cross-market context lookup
            xm_ctx = cross_market_context(ts, xm, cfg)
            risk_state = xm_ctx["risk_state"]

            # Higher-TF trend confluence
            t_4h = trend_at(df_4h, ts)
            t_1d = trend_at(df_1d, ts)

            entry_price = float(bar["close"])
            atr = bar["atr"]
            rsi = bar["rsi"]
            if not (atr and atr > 0 and rsi): continue

            # ═══ REGIME-ADAPTIVE ENTRY ═══

            if regime == "TRENDING_UP":
                confluence = (1 if bar["sma_fast"] > bar["sma_slow"] else 0) \
                                    + (1 if t_4h == "bullish" else 0) \
                                    + (1 if t_1d == "bullish" else 0)
                # Only long trending-up + risk not off + RSI pullback
                if confluence >= strat["min_higher_tf_confluence"] \
                   and risk_state != "off" \
                   and strat["trend_rsi_pullback"][0] <= rsi <= strat["trend_rsi_pullback"][1]:
                    open_trade = {
                        "dir": "LONG", "entry": entry_price, "entry_time": ts,
                        "stop": entry_price - strat["trend_stop_atr"] * atr,
                        "target": entry_price + strat["trend_target_atr"] * atr,
                        "strat": "trend_follow", "regime": regime, "risk": risk_state,
                    }

            elif regime == "TRENDING_DOWN":
                confluence = (1 if bar["sma_fast"] < bar["sma_slow"] else 0) \
                                    + (1 if t_4h == "bearish" else 0) \
                                    + (1 if t_1d == "bearish" else 0)
                if confluence >= strat["min_higher_tf_confluence"] \
                   and risk_state != "on" \
                   and strat["trend_rsi_pullback"][0] <= rsi <= strat["trend_rsi_pullback"][1]:
                    open_trade = {
                        "dir": "SHORT", "entry": entry_price, "entry_time": ts,
                        "stop": entry_price + strat["trend_stop_atr"] * atr,
                        "target": entry_price - strat["trend_target_atr"] * atr,
                        "strat": "trend_follow", "regime": regime, "risk": risk_state,
                    }

            elif regime == "RANGING":
                # Mean-reversion: buy oversold · sell overbought
                if rsi <= strat["mr_rsi_oversold"]:
                    open_trade = {
                        "dir": "LONG", "entry": entry_price, "entry_time": ts,
                        "stop": entry_price - strat["mr_stop_atr"] * atr,
                        "target": entry_price + strat["mr_target_atr"] * atr,
                        "strat": "mean_revert", "regime": regime, "risk": risk_state,
                    }
                elif rsi >= strat["mr_rsi_overbought"]:
                    open_trade = {
                        "dir": "SHORT", "entry": entry_price, "entry_time": ts,
                        "stop": entry_price + strat["mr_stop_atr"] * atr,
                        "target": entry_price - strat["mr_target_atr"] * atr,
                        "strat": "mean_revert", "regime": regime, "risk": risk_state,
                    }

    return trades, {"n_bars_1h": len(df_1h), "n_bars_1d": len(df_1d),
                            "n_bars_4h": len(df_4h)}


# ═══════════════════════════════════════════════════════════════════════
# Metrics aggregation
# ═══════════════════════════════════════════════════════════════════════
def summarize_trades(trades, spec):
    if not trades:
        return {"n_trades": 0, "note": "no signals fired"}

    n = len(trades)
    wins = [t for t in trades if t.outcome == "WIN"]
    losses = [t for t in trades if t.outcome == "LOSS"]

    gross_total = sum(t.gross_pnl_pct for t in trades)
    net_total = sum(t.net_pnl_pct for t in trades)
    cost_drag = gross_total - net_total

    # Sharpe (simplified · per-trade return series)
    net_returns = [t.net_pnl_pct for t in trades]
    if len(net_returns) > 1:
        std = np.std(net_returns)
        sharpe = np.mean(net_returns) / std * np.sqrt(252) if std > 0 else 0
    else:
        sharpe = 0

    # Max drawdown
    equity = np.cumsum(net_returns)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(dd.min()) if len(dd) > 0 else 0

    # Per-regime breakdown
    by_regime = {}
    for regime in ("TRENDING_UP", "TRENDING_DOWN", "RANGING"):
        rt = [t for t in trades if t.regime_at_entry == regime]
        if not rt: continue
        by_regime[regime] = {
            "n":            len(rt),
            "win_rate_pct": round(sum(1 for t in rt if t.outcome == "WIN") / len(rt) * 100, 1),
            "gross_total":  round(sum(t.gross_pnl_pct for t in rt), 2),
            "net_total":    round(sum(t.net_pnl_pct for t in rt), 2),
            "avg_net":      round(sum(t.net_pnl_pct for t in rt) / len(rt), 3),
        }

    # Per-strategy breakdown
    by_strategy = {}
    for strategy in ("trend_follow", "mean_revert"):
        st = [t for t in trades if t.strategy == strategy]
        if not st: continue
        by_strategy[strategy] = {
            "n":            len(st),
            "win_rate_pct": round(sum(1 for t in st if t.outcome == "WIN") / len(st) * 100, 1),
            "net_total":    round(sum(t.net_pnl_pct for t in st), 2),
            "avg_net":      round(sum(t.net_pnl_pct for t in st) / len(st), 3),
        }

    return {
        "symbol":            spec["symbol"],
        "name":              spec["name"],
        "class":             spec["class"],
        "n_trades":          n,
        "n_wins":            len(wins),
        "n_losses":          len(losses),
        "win_rate_pct":      round(len(wins) / n * 100, 1),
        "gross_total_pct":   round(gross_total, 2),
        "net_total_pct":     round(net_total, 2),
        "cost_drag_pct":     round(cost_drag, 2),
        "avg_net_per_trade": round(net_total / n, 3),
        "sharpe_annualized": round(float(sharpe), 2),
        "max_drawdown_pct":  round(max_dd, 2),
        "by_regime":         by_regime,
        "by_strategy":       by_strategy,
        "expectancy_net_pct": round(net_total / n, 3),
    }
