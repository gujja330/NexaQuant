# strategy/regime.py
"""
Market regime detector -- the gate that decides WHICH SMC pillars to trust.

Our evidence: continuation pillars (Structure+FVG) win in TRENDS; mean-reversion
pillars (sweeps, discount) only make sense in RANGES; both should stand aside when
VOLATILE. This module classifies each bar (causally) into trend / range / volatile
/ neutral so the strategy can switch behaviour.

Indicators (all leakage-free; use only past/closed bars):
  * ADX (Wilder)          -> trend strength
  * ATR-fast / ATR-slow   -> volatility expansion (regime instability)
Thresholds are config-driven (see config/base_config.yaml -> regime).
"""
import numpy as np
import pandas as pd


def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    up, dn = h.diff(), -l.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / n, adjust=False).mean().replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


DEFAULTS = dict(adx_n=14, vol_fast=14, vol_slow=100,
                adx_trend=25.0, adx_range=18.0, vol_spike=1.8)


def detect_regime(df, **kw):
    """Return a Series of {'trend','range','volatile','neutral'} per bar (causal).
    'volatile' overrides everything (vol expansion = stand aside / size down)."""
    p = {**DEFAULTS, **{k: v for k, v in kw.items() if v is not None}}
    a = adx(df, p["adx_n"])
    vol_ratio = atr(df, p["vol_fast"]) / atr(df, p["vol_slow"]).replace(0, np.nan)
    reg = pd.Series("neutral", index=df.index)
    reg[a >= p["adx_trend"]] = "trend"
    reg[a <= p["adx_range"]] = "range"
    reg[vol_ratio >= p["vol_spike"]] = "volatile"
    return reg, a, vol_ratio


def regime_summary(reg):
    return reg.value_counts(normalize=True).round(3).to_dict()


# ----------------------------------------------------------- ML regime (HMM)
def detect_regime_hmm(df, n_states=3, fit_fraction=0.7, seed=0):
    """LEARNED regime via a Gaussian HMM on [trend-strength (ADX), volatility (log ATR)].

    Leakage-safe by construction:
      * HMM parameters are FIT only on the first `fit_fraction` of data (no test leak)
      * states are then assigned by a CAUSAL forward filter (posterior uses only past
        observations) — NOT Viterbi/smoothing which would peek at the future
    States are mapped to {trend, range, volatile} by their learned feature means, so the
    labels are interpretable and comparable to the rule-based detect_regime()."""
    from hmmlearn.hmm import GaussianHMM
    from scipy.special import logsumexp

    # features: trend strength, volatility level, recent move size (separates 3 regimes)
    a = adx(df, 14)
    vol = np.log(atr(df, 14).replace(0, np.nan))
    absret = df["close"].pct_change().abs().rolling(10).mean()
    feat = pd.concat([a, vol, absret], axis=1).dropna()
    feat.columns = ["adx", "logatr", "absret"]
    X = ((feat - feat.mean()) / feat.std()).values            # standardise
    n_fit = max(int(len(X) * fit_fraction), 50)

    # full covariance + best-of-N restarts (HMM is init-sensitive; diag/single-init collapses).
    # For long series the fit dominates runtime, so fit on a capped, evenly-sampled subset
    # (regimes are persistent — subsampling preserves them) and use fewer restarts.
    n_restarts = 4
    fit_X = X[:n_fit]
    if len(fit_X) > 12000:                          # cap fit size for speed on big TFs
        step = len(fit_X) // 12000 + 1
        fit_X = fit_X[::step]
    model = None
    for s in range(seed, seed + n_restarts):
        m = GaussianHMM(n_components=n_states, covariance_type="full",
                        n_iter=120, tol=1e-3, random_state=s)
        try:
            m.fit(fit_X)
            if model is None or m.score(fit_X) > model.score(fit_X):
                model = m
        except Exception:
            continue
    if model is None:
        return pd.Series("neutral", index=df.index)

    # causal forward filter: P(state_t | x_1..x_t). Vectorised numpy log-sum-exp per step
    # (sequential over time, but each step is a tiny KxK op) -> fast even on 50k+ bars.
    fl = model._compute_log_likelihood(X)
    logA = np.log(model.transmat_ + 1e-12)

    def _lse(v, axis=None):                      # numerically-stable log-sum-exp
        m = np.max(v, axis=axis, keepdims=True)
        out = m + np.log(np.sum(np.exp(v - m), axis=axis, keepdims=True))
        return out if axis is None else np.squeeze(out, axis=axis)

    T = len(X)
    la = np.empty((T, n_states))
    a0 = np.log(model.startprob_ + 1e-12) + fl[0]
    la[0] = a0 - _lse(a0)
    for t in range(1, T):
        M = la[t - 1][:, None] + logA          # (K,K): prev-state j -> state k
        a = _lse(M, axis=0) + fl[t]            # marginalise over previous state
        la[t] = a - _lse(a)
    states = la.argmax(1)

    # map states -> labels using learned means (means_ is in standardised space)
    means = model.means_                                       # [n_states, (adx, logatr)]
    order_vol = np.argsort(means[:, 1])                        # by volatility
    volatile = order_vol[-1]                                   # highest vol = volatile
    rest = [s for s in range(n_states) if s != volatile]
    trend = max(rest, key=lambda s: means[s, 0])               # highest ADX = trend
    label_map = {volatile: "volatile", trend: "trend"}
    for s in rest:
        label_map.setdefault(s, "range")
    labels = pd.Series([label_map[s] for s in states], index=feat.index)
    return labels.reindex(df.index).ffill().fillna("neutral")
