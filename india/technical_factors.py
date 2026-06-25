# india/technical_factors.py
"""
TECHNICAL FACTOR ENGINE — compute REAL indicators from OHLCV, present them honestly.

Key principle (user's): never mix "available data" with "decision inputs". Every factor is reported as:
  Observed         — the actual computed value (real, causal)
  Used by Strategy — Yes ONLY for what truly drives AEGIS selection (low realised volatility);
                     everything else is observed-but-NOT-used
  Contribution     — Positive / Neutral / (Negative) — honest about its role

This lets an investor see the market picture, what AEGIS actually considered, and what drove the
pick — without pretending unused indicators influenced anything. Fundamentals/news/earnings are
NOT here (no data) and are shown as "Not Evaluated" in the workbook, not invented.

Run (self-test): python india/technical_factors.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")


def _rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0).rolling(n).mean(); dn = (-d.clip(upper=0)).rolling(n).mean()
    return float((100 - 100 / (1 + up / dn.replace(0, np.nan))).iloc[-1])


def _adx(h, l, c, n=14):
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    up = h.diff(); dn = -l.diff()
    plus = 100 * (np.where((up > dn) & (up > 0), up, 0.0)).astype(float)
    minus = 100 * (np.where((dn > up) & (dn > 0), dn, 0.0)).astype(float)
    pdi = pd.Series(plus, index=h.index).rolling(n).mean() / atr.replace(0, np.nan)
    mdi = pd.Series(minus, index=h.index).rolling(n).mean() / atr.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return float(dx.rolling(n).mean().iloc[-1])


def snapshot(closes, highs, lows, vols, idx, s, sector_syms):
    """Return list of (Category, Indicator, Observed, Used, Contribution) for stock s, latest date."""
    c = closes[s].dropna(); h = highs[s].reindex(c.index); l = lows[s].reindex(c.index); v = vols[s].reindex(c.index)
    px = c.iloc[-1]
    ema = {p: c.ewm(span=p).mean().iloc[-1] for p in (20, 50, 100, 200)}
    rvol = c.pct_change().tail(20).std() * np.sqrt(252) * 100           # realised vol — THE driver
    roc20 = (px / c.iloc[-21] - 1) * 100 if len(c) > 21 else np.nan
    mom10 = (px / c.iloc[-11] - 1) * 100 if len(c) > 11 else np.nan
    rs_nifty = (px / c.iloc[-64] - 1 - (idx.iloc[-1] / idx.iloc[-64] - 1)) * 100 if len(c) > 64 else np.nan
    sec_px = closes[[x for x in sector_syms if x in closes.columns]].dropna(how="all")
    rs_sector = np.nan
    if len(sec_px) > 64:
        sret = (sec_px.iloc[-1] / sec_px.iloc[-64] - 1).mean()
        rs_sector = ((px / c.iloc[-64] - 1) - sret) * 100
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]; atr_pct = 100 * atr / px
    bbw = 100 * (4 * c.tail(20).std()) / c.tail(20).mean()              # Bollinger width (2σ band)/mid
    vspike = v.iloc[-1] / v.tail(20).mean() if v.tail(20).mean() > 0 else np.nan
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    obv_up = obv.iloc[-1] > obv.tail(20).mean()
    try:
        adx = _adx(h, l, c)
    except Exception:
        adx = np.nan
    rsi = _rsi(c)
    yn = lambda b: "Yes" if b else "No"
    rows = [
        ("Trend", "Above 20/50/100/200 EMA", "/".join(yn(px > ema[p]) for p in (20, 50, 100, 200)), "No", "Neutral"),
        ("Trend", "50 vs 200 EMA", "Golden" if ema[50] > ema[200] else "Death", "No", "Neutral"),
        ("Momentum", "RSI(14)", f"{rsi:.0f}", "No", "Neutral"),
        ("Momentum", "ROC(20)", f"{roc20:+.1f}%", "No", "Neutral"),
        ("Momentum", "Momentum(10)", f"{mom10:+.1f}%", "No", "Neutral"),
        ("Momentum", "Rel strength vs Nifty (3M)", f"{rs_nifty:+.1f}%", "No", "Neutral"),
        ("Momentum", "Rel strength vs Sector (3M)", f"{rs_sector:+.1f}%" if not np.isnan(rs_sector) else "n/a", "No", "Neutral"),
        ("Trend strength", "ADX(14)", f"{adx:.0f}" if not np.isnan(adx) else "n/a", "No", "Neutral"),
        ("Volatility", "Realised vol (20d, ann.)", f"{rvol:.0f}%", "YES", "Positive (low-vol = the driver)"),
        ("Volatility", "ATR(14) %", f"{atr_pct:.1f}%", "No", "Neutral"),
        ("Volatility", "Bollinger band width", f"{bbw:.1f}%", "No", "Neutral"),
        ("Volume", "Volume spike (vs 20d)", f"{vspike:.1f}x" if not np.isnan(vspike) else "n/a", "No", "Neutral"),
        ("Volume", "OBV trend", "rising" if obv_up else "falling", "No", "Neutral"),
    ]
    return [(s, *r) for r in rows]


def main():
    from india.feature_engine import load_panels
    from india.data_nse import NIFTY200
    from india.sectors import SECTORS, sector_of
    closes, highs, lows, vols, idx, _, _ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    s = "ITC" if "ITC" in closes.columns else closes.columns[0]
    sec_syms = [x for x in closes.columns if SECTORS.get(x) == sector_of(s)]
    print(f"  Technical factor snapshot — {s} ({sector_of(s)})\n")
    print(f"  {'Category':<16}{'Indicator':<30}{'Observed':<18}{'Used':<6}Contribution")
    for _, cat, ind, obs, used, contrib in snapshot(closes, highs, lows, vols, idx, s, sec_syms):
        print(f"  {cat:<16}{ind:<30}{obs:<18}{used:<6}{contrib}")
    print("\n  Only realised volatility is USED by the strategy (low-vol selection). Everything else is")
    print("  OBSERVED context, not a decision input. Fundamentals/news = Not Evaluated (no data).")


if __name__ == "__main__":
    main()
