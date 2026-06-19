# india/validation.py
"""
RIGOR GATE — Deflated Sharpe Ratio + purged walk-forward (López de Prado).

After trying many variants you WILL find a high Sharpe by luck. The Deflated Sharpe Ratio (DSR)
discounts for the number of trials, sample length, skew and kurtosis, and returns the probability
the TRUE Sharpe is > 0. DSR > 0.95 = robust; < 0.95 = likely overfit.

  from india.validation import deflated_sharpe
  deflated_sharpe(daily_returns, n_trials=20)
"""
import numpy as np
import pandas as pd
from scipy.stats import norm

EMC = 0.5772156649015329          # Euler-Mascheroni


def deflated_sharpe(returns, n_trials=10, ppy=252):
    r = np.asarray(returns, float); r = r[~np.isnan(r)]
    T = len(r)
    mu, sd = r.mean(), r.std(ddof=1)
    if sd == 0 or T < 30:
        return dict(dsr=np.nan, sr_ann=np.nan, sr0_ann=np.nan, T=T)
    sr = mu / sd                                   # per-period Sharpe
    g3 = float(((r - mu) ** 3).mean() / sd ** 3)   # skew
    g4 = float(((r - mu) ** 4).mean() / sd ** 4)   # kurtosis (non-excess)
    # expected max Sharpe over n_trials of zero-skill strategies (deflation benchmark)
    sr_trial_std = np.sqrt(1.0 / (T - 1))          # SR-estimator std under the null
    sr0 = sr_trial_std * ((1 - EMC) * norm.ppf(1 - 1.0 / n_trials) +
                          EMC * norm.ppf(1 - 1.0 / (n_trials * np.e)))
    denom = np.sqrt(max(1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2, 1e-9))
    dsr = float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / denom))
    return dict(dsr=dsr, sr_ann=sr * np.sqrt(ppy), sr0_ann=sr0 * np.sqrt(ppy), T=T)


def pbo(returns_df, S=8):
    """Probability of Backtest Overfitting (Bailey-López de Prado CSCV). returns_df: T x N daily
    returns, one column per strategy CONFIG. High PBO (>0.5) = picking the best config is overfit."""
    from itertools import combinations
    R = returns_df.dropna(how="any")
    T, N = R.shape
    if N < 2:
        return np.nan
    blocks = np.array_split(np.arange(T), S)
    def sharpe(sub):
        m, s = sub.mean(), sub.std()
        return (m / s.replace(0, np.nan)).fillna(-1e9)
    logits = []
    for IS in combinations(range(S), S // 2):
        is_i = np.concatenate([blocks[b] for b in IS])
        oos_i = np.concatenate([blocks[b] for b in range(S) if b not in IS])
        n_star = sharpe(R.iloc[is_i]).idxmax()
        rank = sharpe(R.iloc[oos_i]).rank()[n_star]          # 1=worst .. N=best (OOS)
        w = rank / (N + 1)
        logits.append(np.log(w / (1 - w)))
    return float((np.array(logits) <= 0).mean())


def strategy_matrix():
    """Daily-return matrix across candidate v2 configs (for PBO)."""
    from india.arjuna_v2 import backtest
    cfgs = {"ew": ("ew", None), "inv_vol": ("inv_vol", "simple"), "min_var": ("min_var", "simple"),
            "hrp": ("hrp", "simple"), "hrp_global": ("hrp", "global"), "iv_global": ("inv_vol", "global"),
            "mv_global": ("min_var", "global"), "ew_global": ("ew", "global"),
            "hrp_none": ("hrp", None), "iv_none": ("inv_vol", None)}
    cols = {}
    for name, (m, r) in cfgs.items():
        net, _ = backtest(m, regime=r)
        cols[name] = net
    return pd.DataFrame(cols).dropna(how="any")


def purged_walkforward(dates, n_splits=5, embargo=5):
    """Yield (train_idx, test_idx) with a purge+embargo gap to prevent leakage across the boundary."""
    n = len(dates); fold = n // (n_splits + 1)
    for k in range(1, n_splits + 1):
        tr_end = fold * k
        te_start = tr_end + embargo
        te_end = min(te_start + fold, n)
        if te_start >= n:
            break
        yield np.arange(0, tr_end), np.arange(te_start, te_end)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from india.arjuna_v2 import backtest
    print("=" * 64)
    print("  DEFLATED SHARPE — does v2's edge survive the number of trials?")
    print("=" * 64)
    N = 20                                          # ~variants explored across the project
    for name, kw in [("EW", dict(method="ew")),
                     ("INV_VOL+simple regime", dict(method="inv_vol", regime="simple")),
                     ("HRP+simple regime", dict(method="hrp", regime="simple")),
                     ("HRP+regime+voltarget", dict(method="hrp", regime="simple", vol_target=0.12))]:
        net, _ = backtest(**kw)
        d = deflated_sharpe(net.values, n_trials=N)
        verdict = "ROBUST" if d["dsr"] > 0.95 else ("borderline" if d["dsr"] > 0.8 else "likely overfit")
        print(f"  {name:<26} SR {d['sr_ann']:.2f}  (deflated thr {d['sr0_ann']:.2f})  "
              f"DSR {d['dsr']:.3f}  -> {verdict}")
    print(f"\n  (DSR = P(true Sharpe>0) after discounting for ~{N} trials. >0.95 = trust it.)")

    print("\n  PBO (Probability of Backtest Overfitting) across", end=" ")
    R = strategy_matrix()
    p = pbo(R)
    print(f"{R.shape[1]} configs: {p:.2f}")
    print(f"  -> {'LOW (config selection is robust, not overfit)' if p < 0.5 else 'HIGH (selection likely overfit!)'}")
