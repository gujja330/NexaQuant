# india/dataset.py
"""
Shared dataset builder: join the feature panel (A2) with the labels (A3) into one
(date, symbol) table the AI models train on. Cached to data/cache so Stage D doesn't
rebuild features on every backtest pass.
"""
import sys, warnings
from pathlib import Path
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.feature_engine import build_features, PRICE_FEATURES, FUND_FEATURES
from india.labels import build_labels

CACHE = ROOT / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)


def feature_list(feature_set="full"):
    """'floor' = causal price/macro/sector only (no look-ahead). 'full' = + snapshot fundamentals."""
    return PRICE_FEATURES if feature_set == "floor" else PRICE_FEATURES + FUND_FEATURES


def build_dataset(freq="M", force=False):
    """Joined features+labels for one rebalance frequency. Cached per freq."""
    cache = CACHE / f"dataset_{freq}.parquet"
    if cache.exists() and not force:
        return pd.read_parquet(cache)
    feats = build_features(freq=freq, with_fundamentals=True)
    labs = build_labels(freq=freq)
    df = feats.join(labs, how="left")
    df.to_parquet(cache)
    return df


if __name__ == "__main__":
    for freq in ("W", "M"):
        df = build_dataset(freq, force=True)
        print(f"  {freq}: {df.shape[0]:,} rows x {df.shape[1]} cols  "
              f"({df.index.get_level_values('date').nunique()} dates)")
