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


def entries(df, side="long", use_smc=True, regime_method="adx", regime=None,
            avoid_volatility=True, tsm_confirm=0.0, macro_gate=False):
    """Regime-gated continuation entries, SYMMETRIC (long OR short).
      long : EMA20>EMA50 + bullish structure, in a TREND regime
      short: EMA20<EMA50 + bearish structure, in a TREND regime
    Entry fires when the condition turns ON. avoid_volatility=True suppresses entries
    during realized-vol spikes AND high-impact news windows (stay away from volatility).

    tsm_confirm (0..1): if >0, also require >= this fraction of multi-lookback TSM horizons
    to agree with the side. Validated PER-SYMBOL (research/tsm_test.py): turns gold H4 from a
    loser (Sharpe -0.14) into a winner (+0.55 at 1.0) but HURTS BTC -> set per-instrument in
    config (instruments.<SYM>.tsm_confirm), default 0 (off)."""
    reg = regime if regime is not None else regime_labels(df, regime_method)
    fast, slow = ema(df["close"], 20), ema(df["close"], 50)
    if side == "short":
        cont, struct_dir = fast < slow, -1
    else:
        cont, struct_dir = fast > slow, 1
    ok = cont & (reg.reindex(df.index) == "trend")
    if use_smc:
        ok = ok & (market_structure(df) == struct_dir)
    if tsm_confirm and tsm_confirm > 0:
        ok = ok & (tsm_score(df, side=side) >= tsm_confirm)
    if macro_gate:                                     # fundamentals must agree (gold drivers)
        from strategy.fundamental_bias import macro_agrees
        ok = ok & macro_agrees(df, side)
    ok = ok.astype(bool)
    ev = ok & (~ok.shift(1, fill_value=False))        # entry = signal turns ON
    if avoid_volatility:                               # then DROP entries in vol/news windows
        from strategy.event_guard import avoid_mask
        ev = ev & (~avoid_mask(df))
    return ev


def expansion_confirm(df, k=1.5):
    """LENGTHY-CANDLE confirmation: True where the just-closed bar's BODY >= k*ATR.
    Validated (research/expansion_test.py): regime entries confirmed by a lengthy candle
    won at 52% / PF 3.38 / 1,444 avg pips vs 84 baseline — big candles are a powerful
    CONFIRMATION (not a standalone trigger; pure expansion entries lose, PF 0.96)."""
    a = atr(df, 14)
    body = (df["close"] - df["open"]).abs()
    return (body >= k * a).shift(1, fill_value=False)


def tsm_score(df, side="long", lookbacks=None):
    """Multi-lookback TIME-SERIES MOMENTUM agreement in [0,1]: the fraction of lookbacks
    over which price has risen (for long) / fallen (for short). Moskowitz/AQR show TSM is a
    robust, decades-stable edge; requiring several horizons to AGREE is a quality filter on
    our single-EMA entry. Lookbacks (in bars) are config-driven (signals.tsm_lookbacks)."""
    from config_loader import cfg
    if lookbacks is None:
        lookbacks = cfg().get("signals", {}).get("tsm_lookbacks", [20, 60, 120, 240])
    c = df["close"]
    agree = sum(((c > c.shift(L)) if side == "long" else (c < c.shift(L))).astype(float)
                for L in lookbacks) / len(lookbacks)
    return agree.fillna(0.0)


def confidence_size(df, cap=None, vol_target=None, crash_protect=None):
    """Position-size multiplier scaled by CONFIDENCE = trend strength (ADX), with an
    extra boost when the entry bar is confirmed by a LENGTHY candle (range expansion),
    and an OPTIONAL volatility-targeting overlay (size up in calm, down in wild markets).
    Validated: sizing up in strong trends raised both return AND Sharpe (BTC H4); the
    lengthy-candle confirm marks the highest-quality trades (PF 3.38) for a bigger size.
    Returns 1.0 in weak trends up to `cap` in very strong trends. `cap` from config
    (sizing.confidence_cap); set 1.0 there to disable scaling (hard fixed risk).

    vol_target: None -> read sizing.vol_target from config (default off). When True, multiply
    by typical_ATR/current_ATR (causal) so each trade contributes more equal risk. NOTE: our
    risk-%/ATR-stop sizing ALREADY targets vol implicitly, so this overlay is gated by A/B test
    (research/vol_target_test.py) and stays off until it proves it beats the champion."""
    from strategy.regime import adx
    from config_loader import cfg
    scfg = cfg().get("sizing", {})
    if cap is None:
        cap = scfg.get("confidence_cap", 3.0)
    if cap <= 1.0:
        return pd.Series(1.0, index=df.index)
    a = adx(df, 14)
    base = 1.0 + ((a - 25.0) / 15.0).clip(0, cap - 1)
    boost = 1.0 + 0.5 * expansion_confirm(df).astype(float)   # +50% size on lengthy-candle confirm
    size = base * boost
    if vol_target is None:
        vol_target = bool(scfg.get("vol_target", False))
    if vol_target:
        from strategy.risk import vol_target_size
        vt = vol_target_size(df, atr_n=scfg.get("atr_n", 14),
                             ref_window=scfg.get("ref_window", 200),
                             cap=cap, floor=scfg.get("floor", 0.25))
        size = size * vt
    if crash_protect is None:
        crash_protect = bool(scfg.get("crash_protect", False))
    if crash_protect:                                    # asymmetric de-risk in vol spikes
        from strategy.event_guard import crash_risk_scale
        rcfg = cfg().get("regime", {})
        size = size * crash_risk_scale(df, fast=rcfg.get("vol_fast", 14),
                                       slow=rcfg.get("vol_slow", 100),
                                       floor=scfg.get("crash_floor", 0.3))
    return size.clip(upper=cap).fillna(1.0)


def momentum_exit_signal(df, fast=20, side="long"):
    """Momentum-fade exit: for a LONG, exit when close drops below fast EMA; for a SHORT,
    exit when close rises back above it. Rides the move while momentum persists."""
    e = ema(df["close"], fast)
    return (df["close"] < e) if side == "long" else (df["close"] > e)


def exit_config(df):
    """Return (exit_signal, params) for backtest.trade_sim.simulate_trades."""
    return momentum_exit_signal(df), EXIT
