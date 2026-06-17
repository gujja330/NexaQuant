# strategy/meta_label.py
"""
AI meta-labeling layer (López de Prado style).

The model does NOT generate trade signals. It takes the rules-based signal's entries
and learns P(this trade wins) from a BROAD feature set, so we only take / up-size the
high-probability ones. Edge comes from the rules; the AI sharpens selection & sizing.

Design principle (the user's point, and the correct one): AI gets strong as the
FEATURE SET widens. So features are grouped and EXTENSIBLE:
  * technical   : returns, RSI, ADX, ATR ratio, EMA distance/slope, time-of-day
  * structure   : SMC market-structure dir, premium/discount ratio, FVG context
  * regime      : volatility ratio, regime one-hot
  * FUNDAMENTAL : real-yield trend, DXY trend, COT positioning, event proximity
                  -> currently NaN placeholders; HistGradientBoosting handles NaN
                  natively, so the model runs today and gets STRONGER the moment
                  data/fundamentals.py fills these columns. No code change needed.

Labels use the triple-barrier method (target / stop / timeout). Train/test split is
temporal WITH an embargo equal to the barrier horizon, so overlapping label windows
cannot leak future info into the test set.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

from pathlib import Path
from strategy.smc import ema, atr, market_structure, fair_value_gaps, premium_discount
from strategy.regime import adx, detect_regime

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
# higher timeframes used as CONTEXT FEATURES for each base timeframe (top-down)
HTF_FOR = {"M5": ["M15", "H1", "H4", "D1"], "M15": ["H1", "H4", "D1"],
           "H1": ["H4", "D1"], "H4": ["D1"], "D1": []}


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


FUNDAMENTAL_COLS = ["f_real_yield_trend", "f_dxy_trend", "f_cot_net_long",
                    "f_event_within_24h", "f_news_sentiment"]


def _htf_context(df_index, htf):
    """Leakage-safe higher-timeframe context features, shifted to last CLOSED bar
    and as-of joined onto the base index. Returns prefixed feature columns."""
    feats = pd.DataFrame(index=htf.index)
    feats[f"trend"] = (ema(htf["close"], 20) > ema(htf["close"], 50)).astype(float)
    feats[f"adx"] = adx(htf, 14)
    feats[f"rsi"] = rsi(htf["close"], 14)
    feats[f"ret5"] = htf["close"].pct_change(5)
    feats = feats.shift(1)                       # only last CLOSED HTF bar
    left = pd.DataFrame(index=df_index).reset_index()
    left = left.rename(columns={left.columns[0]: "time"})
    right = feats.reset_index().rename(columns={feats.index.name or "index": "time"})
    merged = pd.merge_asof(left.sort_values("time"), right.sort_values("time"),
                           on="time", direction="backward")
    return merged.set_index("time")


def build_features(df, symbol=None, tf=None):
    """All causal (computed at/through bar t). Returns a feature DataFrame.
    If symbol/tf given, adds higher-timeframe context + fundamental macro features."""
    c = df["close"]
    a = atr(df, 14)
    f = fair_value_gaps(df)
    pdz = premium_discount(df)
    feats = pd.DataFrame(index=df.index)
    # technical
    feats["ret_1"] = c.pct_change(1)
    feats["ret_5"] = c.pct_change(5)
    feats["ret_20"] = c.pct_change(20)
    feats["rsi_14"] = rsi(c, 14)
    feats["adx_14"] = adx(df, 14)
    feats["atr_ratio"] = a / atr(df, 100).replace(0, np.nan)
    feats["ema_dist"] = (c - ema(c, 50)) / a.replace(0, np.nan)
    feats["ema_slope"] = (ema(c, 20) - ema(c, 20).shift(5)) / a.replace(0, np.nan)
    feats["hour"] = df.index.hour
    feats["dow"] = df.index.dayofweek
    # structure / SMC
    feats["struct_dir"] = market_structure(df)
    feats["pd_ratio"] = pdz["ratio"]
    feats["in_bull_fvg"] = (c > f["bull_bottom"]).astype(float)
    # regime
    reg, _, vol_ratio = detect_regime(df)
    feats["vol_ratio"] = vol_ratio
    feats["reg_trend"] = (reg == "trend").astype(float)
    feats["reg_range"] = (reg == "range").astype(float)
    # MULTI-TIMEFRAME context features (top-down): D1/H4 (and M15/H1) feed the model
    if symbol and tf:
        for htf_name in HTF_FOR.get(tf, []):
            p = RAW / f"{symbol}_{htf_name}.parquet"
            if p.exists():
                ctx = _htf_context(df.index, pd.read_parquet(p).sort_index())
                for col in ctx.columns:
                    feats[f"{htf_name}_{col}"] = ctx[col].values

    # FUNDAMENTAL macro features. Fill from data/raw/FUNDAMENTALS.parquet if present,
    # else NaN placeholders (HistGBM handles NaN; columns activate once populated).
    for col in FUNDAMENTAL_COLS:
        feats[col] = np.nan
    try:
        from data.fundamentals import load_fundamentals
        fund = load_fundamentals(df.index)
        for col in fund.columns:
            if col in feats.columns:
                feats[col] = fund[col].values
    except Exception:
        pass
    return feats


def triple_barrier_labels(df, entries, horizon, stop_mult=1.5, rr=2.0, side=1):
    """For each entry bar (signal True), simulate a long with ATR stop/target over
    `horizon` bars starting at NEXT open. Returns per-entry (label, pnl_$) where
    label=1 if target hit before stop. PnL is net of nothing here (cost added later)."""
    o, h, l = df["open"].values, df["high"].values, df["low"].values
    a = atr(df, 14).values
    idx = np.where(entries.values)[0]
    out = {}
    n = len(df)
    for i in idx:
        if i + 1 >= n or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        entry = o[i + 1]
        risk = stop_mult * a[i]
        target, stop = entry + side * rr * risk, entry - side * risk
        label, pnl, hit = 0, 0.0, False
        end = min(i + 1 + horizon, n)
        for j in range(i + 1, end):
            if side * (h[j] - target) >= 0:      # target reached
                label, pnl, hit = 1, rr * risk, True; break
            if side * (l[j] - stop) <= 0:        # stop reached
                label, pnl, hit = 0, -risk, True; break
        if not hit:                               # timeout: mark-to-market at last close
            pnl = side * (df["close"].values[end - 1] - entry)
            label = int(pnl > 0)
        out[df.index[i]] = (label, pnl)
    return pd.DataFrame(out, index=["label", "pnl"]).T


def make_model(kind="hist", calibrate=False):
    """Model factory.
      'hist'     : HistGradientBoosting (handles NaN natively) — the default single model.
      'ensemble' : soft-voting HistGBM + RandomForest + LogisticRegression. RF and Logistic
                   can't take NaN, so they're wrapped in imputing pipelines; this lets the
                   ensemble use the SAME feature matrix (incl. NaN fundamental slots).
    calibrate=True wraps the model in isotonic CalibratedClassifierCV so P(win) is
    TRUSTWORTHY — required before using proba for Kelly position sizing (strategy.risk
    .proba_to_size). Diversifying the family reduces variance once data is rich enough."""
    hist = HistGradientBoostingClassifier(max_iter=200, max_depth=4, learning_rate=0.05,
                                          l2_regularization=1.0, min_samples_leaf=20, random_state=0)
    if kind == "hist":
        model = hist
    else:
        rf = Pipeline([("imp", SimpleImputer(strategy="median")),
                       ("rf", RandomForestClassifier(n_estimators=300, max_depth=6,
                                                     min_samples_leaf=20, random_state=0, n_jobs=-1))])
        logit = Pipeline([("imp", SimpleImputer(strategy="median")),
                          ("sc", StandardScaler()),
                          ("lr", LogisticRegression(max_iter=1000, C=0.5))])
        model = VotingClassifier([("hist", hist), ("rf", rf), ("logit", logit)],
                                 voting="soft", n_jobs=-1)
    if calibrate:
        from sklearn.calibration import CalibratedClassifierCV
        return CalibratedClassifierCV(model, method="isotonic", cv=3)
    return model


def train_eval(feats, labels, split_ts, embargo, kind="hist"):
    """Temporal split with embargo. Train model (single or ensemble), return
    (model, test_df_with_proba, auc)."""
    lab = labels.join(feats, how="left").dropna(subset=["label"])
    embargo_end = split_ts + embargo
    train = lab[lab.index < split_ts]
    test = lab[lab.index >= embargo_end]
    if len(train) < 40 or len(test) < 10 or train["label"].nunique() < 2:
        return None, test, float("nan")
    # use only features with >=2 distinct non-NaN values in TRAIN (skips empty
    # fundamental placeholders automatically; they activate once populated)
    X_cols = [c for c in feats.columns if train[c].nunique(dropna=True) >= 2]
    model = make_model(kind)
    model.fit(train[X_cols], train["label"])
    proba = model.predict_proba(test[X_cols])[:, 1]
    test = test.copy(); test["proba"] = proba
    try:
        auc = roc_auc_score(test["label"], proba) if test["label"].nunique() > 1 else float("nan")
    except ValueError:
        auc = float("nan")
    return model, test, auc
