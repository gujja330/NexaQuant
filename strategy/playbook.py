# strategy/playbook.py
"""
NexaQuant canonical strategy — one place that composes the validated pieces into a
single, runnable playbook. Entries come from the rules; PROFIT comes from the exit.

THE STRATEGY (evidence-backed on gold H1/H4, OOS, net of cost):
  1. BIAS (top-down)   : trade only WITH the higher-timeframe trend (D1/W1) + macro bias
  2. REGIME GATE       : take CONTINUATION only in a TREND regime; stand aside if VOLATILE
  3. ENTRY             : regime-gated continuation — EMA20>EMA50 (+ SMC structure/FVG)
  4. STOP-LOSS         : hard ATR stop (2 x ATR) — NON-NEGOTIABLE, caps every loser
  5. BIGGER PROFITS    : MOMENTUM-RIDE exit — hold while close > EMA20 (momentum intact),
                         exit when momentum fades. This rides trends for large R-multiples
                         while cutting drawdown ~40% vs "let it run forever".
  6. SMOOTHING (opt)   : scale out 40-50% at +1.5R, move stop to breakeven, ride the rest
  7. SIZING            : volatility-targeted (see strategy/risk.py), fractional Kelly cap
  8. AI (when data-rich): meta-label P(win) gates/sizes entries (strategy/meta_label.py)

Every parameter is here so the playbook is auditable and config-overridable.
"""
import pandas as pd
from strategy.smc import ema, atr, market_structure, fair_value_gaps
from strategy.regime import detect_regime, detect_regime_hmm

# canonical exit config — the winner of research/exit_probe.py (momentum-ride [+ scale-out])
EXIT = dict(stop_mult=2.0, partial_at=1.5, partial_frac=0.4, max_bars=300)


def regime_labels(df, method="adx"):
    """Regime series via the rule gate ('adx') or the learned causal HMM ('hmm').
    HMM beats ADX where data is sufficient (lower drawdown); ADX is the safe default."""
    if method == "hmm":
        return detect_regime_hmm(df, fit_fraction=0.7)
    return detect_regime(df)[0]


def entries(df, side="long", use_smc=True, regime_method="adx", regime=None, avoid_volatility=True):
    """Regime-gated continuation entries, SYMMETRIC (long OR short).
      long : EMA20>EMA50 + bullish structure, in a TREND regime
      short: EMA20<EMA50 + bearish structure, in a TREND regime
    Entry fires when the condition turns ON. avoid_volatility=True suppresses entries
    during realized-vol spikes AND high-impact news windows (stay away from volatility)."""
    reg = regime if regime is not None else regime_labels(df, regime_method)
    fast, slow = ema(df["close"], 20), ema(df["close"], 50)
    if side == "short":
        cont, struct_dir = fast < slow, -1
    else:
        cont, struct_dir = fast > slow, 1
    ok = cont & (reg.reindex(df.index) == "trend")
    if use_smc:
        ok = ok & (market_structure(df) == struct_dir)
    ok = ok.astype(bool)
    ev = ok & (~ok.shift(1, fill_value=False))        # entry = signal turns ON
    if avoid_volatility:                               # then DROP entries in vol/news windows
        from strategy.event_guard import avoid_mask
        ev = ev & (~avoid_mask(df))
    return ev


def confidence_size(df, cap=None):
    """Position-size multiplier scaled by CONFIDENCE = trend strength (ADX).
    Validated: sizing up in strong trends raised both return AND Sharpe (BTC H4).
    Returns 1.0 in weak trends up to `cap` in very strong trends. `cap` from config
    (sizing.confidence_cap); set 1.0 there to disable scaling (hard fixed risk)."""
    from strategy.regime import adx
    from config_loader import cfg
    if cap is None:
        cap = cfg().get("sizing", {}).get("confidence_cap", 3.0)
    if cap <= 1.0:
        return pd.Series(1.0, index=df.index)
    a = adx(df, 14)
    return (1.0 + ((a - 25.0) / 15.0).clip(0, cap - 1)).fillna(1.0)


def momentum_exit_signal(df, fast=20, side="long"):
    """Momentum-fade exit: for a LONG, exit when close drops below fast EMA; for a SHORT,
    exit when close rises back above it. Rides the move while momentum persists."""
    e = ema(df["close"], fast)
    return (df["close"] < e) if side == "long" else (df["close"] > e)


def exit_config(df):
    """Return (exit_signal, params) for backtest.trade_sim.simulate_trades."""
    return momentum_exit_signal(df), EXIT
