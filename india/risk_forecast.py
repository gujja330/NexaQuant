# india/risk_forecast.py
"""
RISK FORECASTING (Layer 2) — does GARCH/EWMA forecast next-month volatility BETTER than simple
trailing vol? (Only worth adding complexity if it does.) We compare, per stock per month, the
rank-correlation (IC) between each forecast and the ACTUAL next-month realized vol.

  trailing_vol : 120-day realized vol (what the portfolio uses now)
  ewma_vol     : RiskMetrics EWMA (lambda 0.94) — fast, no fitting
  garch_vol    : GARCH(1,1) 1-step-ahead forecast (arch)

Run: python india/risk_forecast.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.feature_engine import load_panels
from india.data_nse import NIFTY200

H = 21
ANN = np.sqrt(252)


def ewma_vol(r, lam=0.94):
    return np.sqrt(r.pow(2).ewm(alpha=1 - lam).mean().iloc[-1]) * ANN


def garch_vol(r):
    from arch import arch_model
    x = r.dropna() * 100
    if len(x) < 60:
        return np.nan
    res = arch_model(x, p=1, q=1, mean="Zero", vol="GARCH").fit(disp="off")
    f = res.forecast(horizon=H, reindex=False)
    return np.sqrt(f.variance.values[-1].mean()) / 100 * ANN


if __name__ == "__main__":
    print("=" * 60)
    print("  RISK FORECASTING — vol forecast accuracy (IC vs realized)")
    print("=" * 60)
    closes = load_panels()[0]
    cols = [c for c in closes.columns if c in set(NIFTY200)][:30]   # sample for the GARCH speed
    rets = closes[cols].pct_change()
    didx = closes.index
    months = didx[252::H]                                          # skip warm-up
    rows = []
    for d in months[:-1]:
        i = didx.get_loc(d)
        hist = rets.iloc[max(0, i - 250):i + 1]
        fut = rets.iloc[i + 1:i + 1 + H]
        if len(fut) < 10:
            continue
        actual = fut.std() * ANN
        trail = hist.tail(120).std() * ANN
        ewma = hist.apply(ewma_vol)
        garch = hist.apply(lambda c: garch_vol(c))
        for s in cols:
            if np.isfinite(actual.get(s, np.nan)):
                rows.append({"trail": trail.get(s), "ewma": ewma.get(s),
                             "garch": garch.get(s), "actual": actual.get(s)})
    df = pd.DataFrame(rows).dropna()
    print(f"  samples: {len(df)} (stock-months)\n")
    print(f"  {'forecast':<12}{'corr vs actual vol':>20}")
    for m in ["trail", "ewma", "garch"]:
        print(f"  {m:<12}{df[m].corr(df['actual']):>20.3f}")
    print("\n  Higher corr = better next-month vol forecast. If GARCH/EWMA ~= trailing,")
    print("  the simple trailing vol the portfolio already uses is good enough (keep it simple).")
