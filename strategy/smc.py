# strategy/smc.py
"""
Smart Money Concepts (SMC) + Fair Value Gap (FVG) detectors -- symbol-agnostic,
strictly leakage-free (every signal is confirmable using only past/closed bars).

Concepts implemented:
  * swings()            : fractal swing highs/lows, confirmed k bars later (causal)
  * market_structure()  : BOS / CHoCH -> structural trend direction in {-1,0,+1}
  * fair_value_gaps()   : 3-candle imbalance (bullish/bearish FVG) + zone levels
  * order_blocks()      : last opposite candle before a structural break
  * liquidity_sweep()   : wick beyond prior swing then close back (stop hunt)

These are building blocks. Signal builders at the bottom combine them into
testable long/short positions for the backtest engine.

NOTE: SMC is designed for low timeframes (M5/M15) where liquidity/imbalance is
crisp. On H1/H4 it is a proxy until M5/M15 are pulled from MT5.
"""
import numpy as np
import pandas as pd


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def swings(df, k=5):
    """Most-recent CONFIRMED swing-high / swing-low LEVEL at each bar (causal).
    A swing at bar i is only known k bars later, so levels are shifted by k."""
    H, L = df["high"], df["low"]
    is_sh = H == H.rolling(2 * k + 1, center=True).max()
    is_sl = L == L.rolling(2 * k + 1, center=True).min()
    sh_level = H.where(is_sh).shift(k).ffill()   # available from confirmation bar onward
    sl_level = L.where(is_sl).shift(k).ffill()
    return sh_level, sl_level


def market_structure(df, k=5):
    """Structural direction: +1 after a bullish Break Of Structure (close > last
    swing high), -1 after a bearish BOS (close < last swing low). A flip = CHoCH."""
    sh, sl = swings(df, k)
    c = df["close"]
    st = pd.Series(np.nan, index=df.index)
    st[c > sh] = 1
    st[c < sl] = -1
    return st.ffill().fillna(0)


def fair_value_gaps(df):
    """3-candle imbalance. Bullish FVG at i: low[i] > high[i-2] (gap below price).
    Returns dir (+1/-1/0 at formation) and the carried-forward active zone bounds.
    Zone for bullish FVG = [high[i-2] (bottom), low[i] (top)]."""
    h2, l0 = df["high"].shift(2), df["low"]
    bull = l0 > h2
    h0, l2 = df["high"], df["low"].shift(2)
    bear = h0 < l2
    fvg_dir = pd.Series(np.where(bull, 1, np.where(bear, -1, np.nan)), index=df.index)
    bull_bottom = df["high"].shift(2).where(bull).ffill()   # support of latest bullish FVG
    bull_top = df["low"].where(bull).ffill()
    bear_top = df["low"].shift(2).where(bear).ffill()        # resistance of latest bearish FVG
    bear_bottom = df["high"].where(bear).ffill()
    return dict(dir=fvg_dir.ffill().fillna(0), bull_bottom=bull_bottom, bull_top=bull_top,
                bear_top=bear_top, bear_bottom=bear_bottom, bull=bull, bear=bear)


def order_blocks(df, k=5):
    """Order Block = the last opposite candle before a structural break.
    Bullish OB (demand): last DOWN candle before a bullish BOS -> its low is support.
    Bearish OB (supply): last UP candle before a bearish BOS -> its high is resistance.
    Levels carried forward (most recent valid OB). Causal: BOS uses confirmed swings."""
    st = market_structure(df, k)
    bos_up = (st == 1) & (st.shift(1) != 1)
    bos_dn = (st == -1) & (st.shift(1) != -1)
    pos = pd.Series(np.arange(len(df)), index=df.index)
    last_down = pos.where(df["close"] < df["open"]).ffill()
    last_up = pos.where(df["close"] > df["open"]).ffill()
    lows, highs = df["low"].values, df["high"].values

    def level_at(pos_series, mask, arr):
        p = pos_series.where(mask).ffill()
        out = pd.Series(np.nan, index=df.index)
        valid = p.notna()
        out[valid] = arr[p[valid].astype(int).values]
        return out

    return dict(bull_ob_low=level_at(last_down, bos_up, lows),    # demand support
                bear_ob_high=level_at(last_up, bos_dn, highs),    # supply resistance
                bos_up=bos_up, bos_dn=bos_dn)


def premium_discount(df, k=5):
    """Within the latest confirmed swing range, position price 0..1 (Fibonacci-style).
    Thresholds: <0.25 DEEP discount (strong buy zone), <0.5 discount, >0.5 premium,
    >0.75 DEEP premium (strong sell zone). Causal via confirmed swings."""
    sh, sl = swings(df, k)
    rng = (sh - sl).replace(0, np.nan)
    ratio = ((df["close"] - sl) / rng).clip(0, 1)        # 0 = range low, 1 = range high
    zone = pd.Series(np.where(ratio < 0.5, 1, np.where(ratio > 0.5, -1, 0)), index=df.index)
    deep = pd.Series(np.where(ratio < 0.25, 1, np.where(ratio > 0.75, -1, 0)), index=df.index)
    return dict(zone=zone, deep=deep, ratio=ratio, eq=(sh + sl) / 2.0,
                range_high=sh, range_low=sl)


def liquidity_sweep(df, k=5):
    """Stop hunt: bar wicks BELOW prior swing low but CLOSES back above it (bullish
    sweep), or wicks above prior swing high but closes back below (bearish sweep)."""
    sh, sl = swings(df, k)
    bull_sweep = (df["low"] < sl) & (df["close"] > sl)
    bear_sweep = (df["high"] > sh) & (df["close"] < sh)
    return bull_sweep.fillna(False), bear_sweep.fillna(False)


# ---------------- combined, testable signal builders (positions in {-1,0,1}) ----------------
def sig_fvg_trend(df, k=5, long_only=True):
    """Long while: structure bullish AND latest FVG bullish AND price holding above
    its support (classic SMC continuation / 'FVG as support')."""
    st = market_structure(df, k)
    f = fair_value_gaps(df)
    long_ = (st == 1) & (f["dir"] == 1) & (df["close"] > f["bull_bottom"])
    if long_only:
        return pd.Series(np.where(long_, 1, 0), index=df.index)
    short_ = (st == -1) & (f["dir"] == -1) & (df["close"] < f["bear_top"])
    return pd.Series(np.where(long_, 1, np.where(short_, -1, 0)), index=df.index)


def sig_sweep_reversal(df, k=5):
    """Long after a bullish liquidity sweep (stop hunt then reclaim); flat on bearish
    sweep. Holds until opposite sweep. Mean-reversion flavour of SMC."""
    bull, bear = liquidity_sweep(df, k)
    pos = pd.Series(np.nan, index=df.index)
    pos[bull] = 1
    pos[bear] = 0
    return pos.ffill().fillna(0)


def sig_smc_confluence(df, k=5):
    """Highest-conviction long: bullish structure + bullish FVG support + a recent
    bullish liquidity sweep within the last few bars (confluence)."""
    st = market_structure(df, k)
    f = fair_value_gaps(df)
    bull_sweep, _ = liquidity_sweep(df, k)
    recent_sweep = bull_sweep.rolling(k).max().fillna(0) > 0
    long_ = (st == 1) & (f["dir"] == 1) & (df["close"] > f["bull_bottom"]) & recent_sweep
    return pd.Series(np.where(long_, 1, 0), index=df.index)


def sig_smc_a_plus(df, k=5):
    """A+ setup stacking all five SMC pillars for a long:
      (1) bullish market structure (BOS), (2) price in DISCOUNT zone (<50%, ideally deep),
      (3) at a bullish FVG support OR (4) a bullish Order Block, (5) after a liquidity sweep.
    This is the textbook 'buy the discount in an uptrend at institutional demand'."""
    st = market_structure(df, k)
    f = fair_value_gaps(df)
    pd_ = premium_discount(df, k)
    ob = order_blocks(df, k)
    bull_sweep, _ = liquidity_sweep(df, k)
    recent_sweep = bull_sweep.rolling(k).max().fillna(0) > 0
    at_demand = (df["close"] > f["bull_bottom"]) | (df["close"] > ob["bull_ob_low"])
    long_ = (st == 1) & (pd_["zone"] == 1) & at_demand & recent_sweep
    return pd.Series(np.where(long_, 1, 0), index=df.index)
