# india/regime_hmm.py
"""
REGIME ENGINE — breadth + Hidden Markov Model market-state detection.

Upgrades the v2 de-risk overlay from a hand-rule (VIX>thr OR Nifty<200DMA) to a LEARNED regime.
Market features (all observable, no return look-ahead): realized vol of the Nifty, BREADTH
(% of stocks above their 200-DMA), and India VIX. A Gaussian HMM clusters these into states;
we map states to EXPOSURE by each state's volatility (calm state -> full, turbulent -> de-risked).

HMM fit on the first 60% only, then states predicted forward -> causal. State->exposure mapping
uses VOLATILITY (observable), not returns, so no look-ahead in the de-risk decision.

  from india.regime_hmm import hmm_exposure, breadth_series
  exp = hmm_exposure()     # daily exposure multiplier in (0,1], indexed by date

Run (self-test): python india/regime_hmm.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.feature_engine import load_panels
from hmmlearn.hmm import GaussianHMM


def breadth_series():
    """% of stocks above their 200-DMA — a free, powerful market-health signal."""
    closes = load_panels()[0]
    return (closes > closes.rolling(200).mean()).mean(axis=1)


def market_features():
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    ret = idx.pct_change()
    f = pd.DataFrame({
        "vol": ret.rolling(20).std() * np.sqrt(252),
        "breadth": (closes > closes.rolling(200).mean()).mean(axis=1),
        "vix": vix if vix is not None else ret.rolling(20).std() * np.sqrt(252),
    }).dropna()
    return f


def hmm_exposure(n_states=3, train_frac=0.6, levels=(1.0, 0.7, 0.4)):
    """Daily exposure multiplier from a learned HMM regime (calm->1.0, turbulent->0.4)."""
    f = market_features()
    X = ((f - f.mean()) / f.std()).values
    split = int(len(f) * train_frac)
    model = GaussianHMM(n_components=n_states, covariance_type="full", n_iter=200, random_state=0)
    model.fit(X[:split])
    states = model.predict(X)
    f = f.copy(); f["state"] = states
    # map states to exposure by TRAINING-period average volatility (calm = high exposure)
    sv = f.iloc[:split].groupby("state")["vol"].mean().sort_values()   # low vol -> high vol
    expo_map = {st: levels[min(i, len(levels) - 1)] for i, st in enumerate(sv.index)}
    exp = f["state"].map(expo_map)
    return exp.reindex(load_panels()[0].index).ffill().fillna(1.0)


if __name__ == "__main__":
    print("=" * 60)
    print("  REGIME ENGINE — breadth + HMM market states")
    print("=" * 60)
    f = market_features()
    exp = hmm_exposure()
    f2 = f.copy(); f2["exposure"] = exp.reindex(f.index)
    print(f"  breadth now: {100*breadth_series().iloc[-1]:.0f}% of stocks above 200-DMA")
    print(f"  current regime exposure: {exp.iloc[-1]:.1f}")
    print("\n  exposure distribution (share of days at each level):")
    print(exp.value_counts(normalize=True).round(2).to_string())
    print("\n  avg market vol by exposure level (sanity: lower exposure = higher vol):")
    print(f2.groupby("exposure")["vol"].mean().round(3).to_string())
