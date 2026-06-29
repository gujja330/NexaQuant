# core/feature_store.py
"""
FEATURE STORE — the backbone every research experiment shares.

One normalized table per market keyed by (symbol, date); each FeatureProvider contributes columns. Raw
data is kept separately (markets/<m>/raw/...); providers NORMALIZE raw -> features here, so experiments
never recompute from scratch and every dataset (technicals, fundamentals, earnings, insider, ETF, macro,
news) lands in the SAME comparable layer.

    RawProvider  ->  normalize  ->  FeatureStore.upsert(symbol,date,<cols>)  ->  research / ranking

A FeatureProvider declares metadata (category · source · point_in_time) so the Feature Registry stays
honest about which columns are trustworthy. Market-agnostic: works for India and USA via a MarketAdapter.

Run:  python -m core.feature_store usa --seed     # seed price/technical features for USA
      python -m core.feature_store usa --show
"""
import sys, warnings
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from core.market_adapter import get_adapter


class FeatureStore:
    KEYS = ["symbol", "date"]

    def __init__(self, market):
        self.market = market
        self.path = ROOT / "markets" / market / "features" / "feature_store.parquet"

    def load(self):
        return pd.read_parquet(self.path) if self.path.exists() else pd.DataFrame(columns=self.KEYS)

    def upsert(self, df):
        """Merge a provider's columns by (symbol,date): adds new rows AND new feature columns; updates
        overlaps with the newer value. Reproducible — re-running a provider just refreshes its columns."""
        df = df.copy(); df["date"] = df["date"].astype(str)
        cur = self.load()
        if cur.empty:
            out = df
        else:
            cur["date"] = cur["date"].astype(str)
            out = cur.merge(df, on=self.KEYS, how="outer", suffixes=("", "_new"))
            for c in df.columns:
                if c in self.KEYS:
                    continue
                nc = c + "_new"
                if nc in out:
                    out[c] = out[nc].combine_first(out[c]); out = out.drop(columns=nc)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(self.path)
        return out


class FeatureProvider(ABC):
    name = "abstract"
    category = "abstract"
    source = "abstract"
    point_in_time = True

    @abstractmethod
    def compute(self, adapter): ...     # -> DataFrame[symbol, date, <feature cols>]

    def run(self, market):
        store = FeatureStore(market)
        df = self.compute(get_adapter(market))
        return store.upsert(df)


class TechnicalProvider(FeatureProvider):
    """Price-derived features (the only ones available before external datasets land)."""
    name, category, source, point_in_time = "technical", "Technical", "price", True

    def compute(self, adapter):
        from india.technical_factors import _rsi
        closes, _, _, _, idx, _, _ = adapter.get_market_data()
        uni = [c for c in closes.columns if c in set(adapter.get_universe())]
        closes = closes[uni]; rets = closes.pct_change()
        hist = rets.tail(120)
        px = closes.iloc[-1]
        nif3 = float(idx.iloc[-1] / idx.iloc[-64] - 1) if len(idx) > 64 else 0.0
        asof = str(closes.index[-1].date())
        rows = []
        for s in uni:
            ser = closes[s].dropna()
            if len(ser) < 60:
                continue
            ma200 = float(ser.tail(200).mean()); hi, lo = float(ser.tail(252).max()), float(ser.tail(252).min())
            mom3 = float(px[s] / closes[s].iloc[-64] - 1) if len(closes) > 64 else np.nan
            rows.append({
                "symbol": s, "date": asof, "sector": adapter.get_sector(s),
                "t_vol_ann": round(float(hist[s].std() * np.sqrt(252) * 100), 1),
                "t_mom_1m": round(float(px[s] / closes[s].iloc[-21] - 1) * 100, 1) if len(closes) > 21 else np.nan,
                "t_mom_3m": round(mom3 * 100, 1),
                "t_rel_str_3m": round((mom3 - nif3) * 100, 1),
                "t_above_200dma": int(px[s] > ma200),
                "t_dist_200dma": round(float(px[s] / ma200 - 1) * 100, 1),
                "t_rsi": round(_rsi(ser)) if len(ser) > 30 else np.nan,
                "t_pos_52w": round(100 * (px[s] - lo) / (hi - lo)) if hi > lo else np.nan,
            })
        return pd.DataFrame(rows)


def main():
    market = sys.argv[1] if len(sys.argv) > 1 else "usa"
    store = FeatureStore(market)
    if "--seed" in sys.argv:
        out = TechnicalProvider().run(market)
        print(f"  seeded technical features -> {store.path.relative_to(ROOT)}")
        print(f"  {len(out)} rows · columns: {[c for c in out.columns]}")
    elif "--show" in sys.argv:
        d = store.load()
        print(f"  feature store: {len(d)} rows, {d.shape[1]} cols · {store.path.relative_to(ROOT)}")
        if not d.empty:
            print(d.head(8).to_string(index=False))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
