# india/feature_engine.py
"""
STAGE A2 — Feature pipeline for the Aegis AI ranker.

Builds ~30 signals per stock per rebalance date, the RICH feature set the literature says
ML needs (my earlier price-only test was starved -> AUC 0.47). Groups:
  * TECHNICAL  (clean, zero look-ahead): multi-horizon momentum, vol, RSI, ADX, MA distance,
                turnover/liquidity, drawdown.
  * CORRELATION/BETA: beta & corr to Nifty, crowding (corr to the equal-weight pack).
  * SECTOR: sector momentum, sector rank, stock-vs-sector relative strength.
  * MACRO/REGIME: India VIX level+regime, Nifty trend, S&P momentum.
  * FUNDAMENTAL (snapshot, flagged OPTIMISTIC/look-ahead): ROE, margin, growth, debt, PE, PB, quality.

Output: a long panel DataFrame indexed by (date, symbol), one column per feature, sampled at the
rebalance frequency. Technical/corr/sector/macro features are causal (use only past data).
Fundamentals are a current snapshot broadcast across history -> look-ahead; kept separate so the
backtest can run an HONEST-FLOOR (no fundamentals) vs OPTIMISTIC (with) comparison.

Run (self-test): python india/feature_engine.py
"""
import sys, glob, os, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")                # silence pandas stack/downcast FutureWarnings
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.sectors import SECTORS

RAW = ROOT / "data" / "raw" / "india"
INDEX = "NSEI"
NON_STOCKS = ("NSEI", "NSEBANK", "SP500", "INDIAVIX", "fundamentals")
STEP = {"W": 5, "M": 21}                       # trading days per rebalance bucket

# the causal (no look-ahead) feature columns — used to build the "honest floor" model
PRICE_FEATURES = [
    "mom_1m", "mom_3m", "mom_6m", "mom_12m", "vol_3m", "dvol_3m", "rsi_14", "adx_14",
    "dist_ma20", "dist_ma50", "dist_ma200", "above_ma200", "turnover_log", "dd_3m",
    "beta_nifty", "corr_nifty", "crowding", "sector_mom", "sector_rank", "rel_str_sector",
    "vix_z", "vix_regime", "nifty_mom_6m", "spx_mom_6m",
]
FUND_FEATURES = ["f_roe", "f_margin", "f_growth", "f_debt2eq", "f_pe", "f_pb", "f_quality"]


# ---------- loading ----------
def _load_one(sym):
    return pd.read_parquet(RAW / f"{sym}_D1.parquet").sort_index()


def load_panels():
    """Return aligned OHLCV panels (date x stock) + index/vix/spx series."""
    data = {}
    for f in sorted(glob.glob(str(RAW / "*_D1.parquet"))):
        s = os.path.basename(f).replace("_D1.parquet", "")
        data[s] = pd.read_parquet(f).sort_index()
    stocks = [s for s in data if s not in NON_STOCKS]
    closes = pd.DataFrame({s: data[s]["close"] for s in stocks}).dropna(how="all").sort_index()
    highs = pd.DataFrame({s: data[s]["high"] for s in stocks}).reindex(closes.index)
    lows = pd.DataFrame({s: data[s]["low"] for s in stocks}).reindex(closes.index)
    vols = pd.DataFrame({s: data[s].get("tick_volume", pd.Series(dtype=float)) for s in stocks}).reindex(closes.index)
    idx = data[INDEX]["close"].reindex(closes.index).ffill() if INDEX in data else closes.mean(axis=1)
    vix = data["INDIAVIX"]["close"].reindex(closes.index).ffill() if "INDIAVIX" in data else None
    spx = data["SP500"]["close"].reindex(closes.index).ffill() if "SP500" in data else None
    return closes, highs, lows, vols, idx, vix, spx


# ---------- indicators (vectorized, column-wise on panels) ----------
def _rsi(close, n=14):
    d = close.diff()
    gain = d.clip(lower=0).rolling(n).mean()
    loss = (-d.clip(upper=0)).rolling(n).mean()
    rs = gain / (loss + 1e-12)
    return 100 - 100 / (1 + rs)


def _adx(high, low, close, n=14):
    prev = close.shift()
    tr = pd.DataFrame(np.maximum.reduce([(high - low).values,
                                         (high - prev).abs().values,
                                         (low - prev).abs().values]),
                      index=close.index, columns=close.columns)
    up, dn = high.diff(), -low.diff()
    plus_dm = up.where((up > dn) & (up > 0), 0.0)
    minus_dm = dn.where((dn > up) & (dn > 0), 0.0)
    atr = tr.rolling(n).mean() + 1e-12
    plus_di = 100 * plus_dm.rolling(n).mean() / atr
    minus_di = 100 * minus_dm.rolling(n).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-12)
    return dx.rolling(n).mean()


def _zrows(df):
    return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)


# ---------- the feature build ----------
def build_features(freq="W", with_fundamentals=True):
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    rets = closes.pct_change()
    feats = {}

    # --- TECHNICAL ---
    feats["mom_1m"] = closes.shift(5) / closes.shift(21) - 1
    feats["mom_3m"] = closes.shift(5) / closes.shift(63) - 1
    feats["mom_6m"] = closes.shift(10) / closes.shift(126) - 1
    feats["mom_12m"] = closes.shift(21) / closes.shift(252) - 1
    feats["vol_3m"] = rets.rolling(63).std() * np.sqrt(252)
    feats["dvol_3m"] = rets.clip(upper=0).rolling(63).std() * np.sqrt(252)
    feats["rsi_14"] = _rsi(closes)
    feats["adx_14"] = _adx(highs, lows, closes)
    feats["dist_ma20"] = closes / closes.rolling(20).mean() - 1
    feats["dist_ma50"] = closes / closes.rolling(50).mean() - 1
    feats["dist_ma200"] = closes / closes.rolling(200).mean() - 1
    feats["above_ma200"] = (closes > closes.rolling(200).mean()).astype(float)
    feats["turnover_log"] = np.log((closes * vols).rolling(20).mean() + 1.0)
    roll_max = closes.rolling(63).max()
    feats["dd_3m"] = closes / roll_max - 1                        # 0 at highs, negative in drawdown

    # --- CORRELATION / BETA ---
    idx_ret = idx.pct_change()
    var_idx = idx_ret.rolling(120).var()
    feats["beta_nifty"] = rets.rolling(120).cov(idx_ret).div(var_idx + 1e-12, axis=0)
    feats["corr_nifty"] = rets.rolling(120).corr(idx_ret)
    pack_ret = rets.mean(axis=1)                                  # equal-weight universe (the "pack")
    feats["crowding"] = rets.rolling(60).corr(pack_ret)          # high = moves with the herd

    # --- SECTOR ---
    sect = pd.Series({s: SECTORS.get(s, "Other") for s in closes.columns})
    mom6 = feats["mom_6m"]
    sector_mom = mom6.T.groupby(sect).transform("mean").T        # each stock <- its sector's avg 6m mom
    feats["sector_mom"] = sector_mom
    feats["rel_str_sector"] = mom6 - sector_mom                  # stock vs its sector
    feats["sector_rank"] = sector_mom.rank(axis=1, pct=True)     # 0..1 rank of the stock's sector strength

    # --- MACRO / REGIME (same across stocks each date; conditions the model) ---
    ones = pd.DataFrame(1.0, index=closes.index, columns=closes.columns)
    if vix is not None:
        vz = (vix - vix.rolling(252).mean()) / (vix.rolling(252).std() + 1e-12)
        hi = vix > vix.rolling(120, min_periods=30).quantile(0.80)
        feats["vix_z"] = ones.mul(vz, axis=0)
        feats["vix_regime"] = ones.mul(hi.astype(float), axis=0)
    else:
        feats["vix_z"] = ones * 0; feats["vix_regime"] = ones * 0
    feats["nifty_mom_6m"] = ones.mul(idx.shift(10) / idx.shift(126) - 1, axis=0)
    if spx is not None:
        feats["spx_mom_6m"] = ones.mul(spx.shift(10) / spx.shift(126) - 1, axis=0)
    else:
        feats["spx_mom_6m"] = ones * 0

    # --- sample at rebalance dates, stack to a long panel ---
    step = STEP.get(freq, 5)
    rebal = closes.index[::step]
    cols = PRICE_FEATURES
    panel = pd.concat({c: feats[c].reindex(rebal).stack(dropna=False) for c in cols}, axis=1)
    panel.index.names = ["date", "symbol"]

    # --- FUNDAMENTALS (snapshot, broadcast -> OPTIMISTIC/look-ahead) ---
    if with_fundamentals:
        fp = RAW / "fundamentals.parquet"
        if fp.exists():
            f = pd.read_parquet(fp)
            ren = {"returnOnEquity": "f_roe", "profitMargins": "f_margin",
                   "earningsGrowth": "f_growth", "debtToEquity": "f_debt2eq",
                   "trailingPE": "f_pe", "priceToBook": "f_pb", "quality_score": "f_quality"}
            f = f.rename(columns=ren)[[c for c in ren.values() if c in [ren[k] for k in ren]]]
            f = f[[c for c in FUND_FEATURES if c in f.columns]]
            panel = panel.join(f, on="symbol")
        else:
            for c in FUND_FEATURES:
                panel[c] = np.nan

    return panel


if __name__ == "__main__":
    print("=" * 70)
    print("  STAGE A2 — feature engine self-test")
    print("=" * 70)
    for freq in ("W", "M"):
        p = build_features(freq=freq, with_fundamentals=True)
        n_dates = p.index.get_level_values("date").nunique()
        n_syms = p.index.get_level_values("symbol").nunique()
        # drop rows with no price-feature history (warm-up period)
        valid = p.dropna(subset=["mom_12m", "rsi_14"])
        print(f"\n  freq={freq}: panel {p.shape[0]:,} rows  ({n_dates} dates x {n_syms} stocks)")
        print(f"           usable after warm-up: {valid.shape[0]:,} rows")
        fund_cov = valid[[c for c in FUND_FEATURES if c in valid.columns]].notna().any(axis=1).mean()
        print(f"           fundamental coverage: {100*fund_cov:.0f}% of usable rows")
    print("\n  columns:", list(p.columns))
    print("\n  sample (last date, top 3 rows):")
    last = p.index.get_level_values("date").max()
    print(p.loc[last].head(3).to_string())
