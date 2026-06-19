# india/arjuna_v2.py
"""
ARJUNA v2 — RISK-BASED portfolio construction (the validated direction).

We proved: returns are unpredictable (AUC 0.51) but RISK is (vol AUC 0.76). So v2 stops trying to
pick winners and instead WEIGHTS the broad basket by predictable risk:

  EW       : equal weight (v1 baseline)
  INV_VOL  : weight ~ 1/volatility (risk parity lite -> overweight the predictably-calm names)
  MIN_VAR  : minimum-variance weights from a Ledoit-Wolf shrinkage covariance (long-only)

+ optional REGIME overlay: cut exposure when India VIX is high AND/OR Nifty < 200-DMA.

Goal = HIGHER SHARPE + SMALLER DRAWDOWN (not higher raw return; that's unpredictable). Compared to
equal-weight and Nifty, net of ~21bps, full window. (Vol/cov use trailing data = causal; XGBoost
vol forecast — AUC 0.76, see target_test.py — is the refinement layer on top.)

Run: python india/arjuna_v2.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.feature_engine import load_panels
from india.equity_engine import COST_BPS
from india.data_nse import NIFTY200
from sklearn.covariance import LedoitWolf
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform

REBAL, LOOKBACK = 21, 120          # monthly rebalance; 120d window for vol/covariance


# ---- HRP (Hierarchical Risk Parity, López de Prado) — correlation-cluster aware weights ----
def _ivp(cov):
    iv = 1.0 / np.diag(cov); return iv / iv.sum()


def _cluster_var(cov, items):
    c = cov.loc[items, items]; w = _ivp(c.values).reshape(-1, 1)
    return float((w.T @ c.values @ w)[0, 0])


def _quasi_diag(link):
    link = link.astype(int); s = pd.Series([link[-1, 0], link[-1, 1]]); n = link[-1, 3]
    while s.max() >= n:
        s.index = range(0, s.shape[0] * 2, 2)
        df0 = s[s >= n]; i = df0.index; j = df0.values - n
        s[i] = link[j, 0]; s = pd.concat([s, pd.Series(link[j, 1], index=i + 1)])
        s = s.sort_index(); s.index = range(s.shape[0])
    return s.tolist()


def _hrp(cov, corr):
    dist = ((1 - corr) / 2.0) ** 0.5
    link = linkage(squareform(dist.values, checks=False), "single")
    order = [corr.index[i] for i in _quasi_diag(link)]
    w = pd.Series(1.0, index=order); clusters = [order]
    while clusters:
        clusters = [c[j:k] for c in clusters for j, k in ((0, len(c) // 2), (len(c) // 2, len(c))) if len(c) > 1]
        for i in range(0, len(clusters), 2):
            c0, c1 = clusters[i], clusters[i + 1]
            a = 1 - _cluster_var(cov, c0) / (_cluster_var(cov, c0) + _cluster_var(cov, c1))
            w[c0] *= a; w[c1] *= 1 - a
    return w


def weights_for(method, hist):
    """hist = trailing daily returns (rows=days, cols=stocks, no NaN). Returns weight Series."""
    cols = hist.columns
    if method == "ew":
        w = pd.Series(1.0 / len(cols), index=cols)
    elif method == "inv_vol":
        vol = hist.std()
        iv = 1.0 / vol.replace(0, np.nan)
        w = (iv / iv.sum()).fillna(0)
    elif method == "min_var":
        cov = LedoitWolf().fit(hist.values).covariance_
        raw = np.clip(np.linalg.pinv(cov) @ np.ones(len(cols)), 0, None)
        w = pd.Series(raw / raw.sum() if raw.sum() > 0 else 1.0 / len(cols), index=cols)
    elif method == "hrp":
        cov = pd.DataFrame(LedoitWolf().fit(hist.values).covariance_, index=cols, columns=cols)
        w = _hrp(cov, hist.corr()).reindex(cols).fillna(0)
        w = w / w.sum()
    return w


def backtest(method="ew", regime=False, universe=NIFTY200, cap=0.05, vol_target=0.0):
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    cols = [c for c in closes.columns if c in set(universe)]
    closes = closes[cols]
    rets = closes.pct_change()
    rebal_idx = closes.index[::REBAL]
    W = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    for dt in rebal_idx:
        hist = rets.loc[:dt].tail(LOOKBACK).dropna(axis=1, how="any")
        if hist.shape[1] < 20 or len(hist) < 60:
            continue
        w = weights_for(method, hist).clip(upper=cap)   # per-name cap for diversification
        w = w / w.sum()
        W.loc[dt, w.index] = w.values
    W = W.replace(0.0, np.nan).ffill().fillna(0.0)
    gross = (W.shift(1) * rets.reindex(columns=W.columns)).sum(axis=1)
    net = gross - (W - W.shift(1)).abs().sum(axis=1) * (COST_BPS / 1e4)
    if regime in ("simple", True, "global"):
        scale = pd.Series(1.0, index=net.index)
        if vix is not None:
            hi = (vix > vix.rolling(120, min_periods=30).quantile(0.80)).reindex(net.index).fillna(False)
            scale *= hi.map({True: 0.6, False: 1.0})
        below = (idx < idx.rolling(200).mean()).reindex(net.index).fillna(False)
        scale *= below.map({True: 0.6, False: 1.0})
        if regime == "global":                          # + Global Risk Engine (Tier-1)
            from india.global_risk import global_exposure
            g = global_exposure()
            if g is not None:
                scale *= g.reindex(net.index).ffill().fillna(1.0)
        net = net * scale
    elif regime == "hmm":
        from india.regime_hmm import hmm_exposure
        exp = hmm_exposure().reindex(net.index).shift(1).fillna(1.0)   # shift -> use prior day's state
        net = net * exp
    if vol_target:                                     # dynamic vol-targeting (Bridgewater/AQR style)
        realized = net.rolling(20).std() * np.sqrt(252)
        lev = (vol_target / realized.shift(1)).clip(0.0, 2.0).fillna(1.0)
        net = net * lev
    return net, idx


def stats(net, idx):
    eq = (1 + net).cumprod(); peak = eq.cummax()
    yrs = len(net) / 252
    return dict(cagr=100 * (eq.iloc[-1] ** (1 / yrs) - 1),
                sharpe=net.mean() / (net.std() + 1e-12) * np.sqrt(252),
                dd=100 * ((peak - eq) / peak).max(), end=eq.iloc[-1] * 1e5)


def row(name, net, idx):
    s = stats(net, idx)
    print(f"  {name:<30}{s['cagr']:>7.1f}%{s['sharpe']:>8.2f}{s['dd']:>8.1f}%   Rs{s['end']:>11,.0f}")


if __name__ == "__main__":
    print("=" * 74)
    print("  ARJUNA v2 — RISK-BASED construction (Nifty-200, net of cost, ~5.5y)")
    print("  Goal: higher Sharpe + smaller drawdown (return is unpredictable)")
    print("=" * 74)
    print(f"  {'method':<30}{'CAGR':>7}{'Sharpe':>8}{'maxDD':>8}   {'Rs1L ->':>13}")
    _, idx = backtest("ew")
    row("EW (v1 baseline)", *backtest("ew"))
    row("INV_VOL (risk parity lite)", *backtest("inv_vol"))
    row("MIN_VAR (shrinkage cov)", *backtest("min_var"))
    row("HRP (cluster risk parity)", *backtest("hrp"))
    row("INV_VOL + simple regime", *backtest("inv_vol", regime="simple"))
    row("HRP + simple regime", *backtest("hrp", regime="simple"))
    row("INV_VOL + regime + vol-target 12%", *backtest("inv_vol", regime="simple", vol_target=0.12))
    row("HRP + regime + vol-target 12%", *backtest("hrp", regime="simple", vol_target=0.12))
    nifty = idx.pct_change().fillna(0.0); neq = (1 + nifty).cumprod()
    nsh = nifty.mean() / (nifty.std() + 1e-12) * np.sqrt(252)
    print(f"  {'NIFTY-50 (benchmark)':<30}{100*((neq.iloc[-1])**(1/(len(nifty)/252))-1):>7.1f}%{nsh:>8.2f}"
          f"{100*((neq.cummax()-neq)/neq.cummax()).max():>8.1f}%   Rs{neq.iloc[-1]*1e5:>11,.0f}")
    print("\n  Keep the method with the best Sharpe + lowest drawdown. (Survivorship inflates CAGR;")
    print("  the Sharpe/DD IMPROVEMENT over EW is the honest, transferable signal.)")
