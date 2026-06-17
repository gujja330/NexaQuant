# File: core/feature_engineering.py

import numpy as np
import pandas as pd
import ta

def add_return_and_zscore(df, price_col="close", zscore_window=20):
    df = df.copy()
    df["ret_1"] = df[price_col].pct_change(1)
    roll = df["ret_1"].rolling(zscore_window)
    df["ret_1_z"] = (df["ret_1"] - roll.mean()) / roll.std()
    return df

def add_multi_bar_returns(df, price_col="close", periods=[2,4,8,24]):
    df = df.copy()
    for p in periods:
        df[f"ret_{p}"] = df[price_col].pct_change(p)
    return df

def add_rolling_momentum(df, price_col="close", periods=[2,4,8,24]):
    df = df.copy()
    for p in periods:
        df[f"mom_{p}"] = df[price_col].diff(p)
    return df

def add_atr(df, high_col="high", low_col="low", close_col="close", period=14):
    df = df.copy()
    if not {high_col, low_col, close_col}.issubset(df.columns):
        return df
    tr1 = df[high_col] - df[low_col]
    tr2 = (df[high_col] - df[close_col].shift()).abs()
    tr3 = (df[low_col]  - df[close_col].shift()).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.rolling(period).mean()
    return df

def add_rolling_stats(df, cols, windows=[5,10,20,50]):
    df = df.copy()
    for col in cols:
        if col not in df.columns:
            continue
        for w in windows:
            df[f"{col}_ma_{w}"]  = df[col].rolling(w).mean()
            df[f"{col}_std_{w}"] = df[col].rolling(w).std()
            df[f"{col}_min_{w}"] = df[col].rolling(w).min()
            df[f"{col}_max_{w}"] = df[col].rolling(w).max()
    return df

def build_features(df):
    df = df.copy()

    # 🚧 Diagnostic spike‐check remains, but we no longer auto‐rescale prices:
    if len(df) >= 2:
        last_close  = df["close"].iloc[-1]
        prior_close = df["close"].iloc[-2]
        jump_ratio  = abs(last_close / prior_close)
        if jump_ratio > 10:
            raise ValueError(
                f"⚠️ Sudden price jump detected: {prior_close:.2f} → {last_close:.2f}."
            )

    # 0️⃣ Assign raw_close directly from close
    df["raw_close"] = df["close"]
    df["close_diff"] = df["raw_close"].diff()

    # 1) GENERIC FEATURES
    df = add_return_and_zscore(df, price_col="raw_close", zscore_window=20)
    df = add_multi_bar_returns(df, price_col="raw_close", periods=[2,4,8,24])
    df = add_rolling_momentum(df, price_col="raw_close", periods=[2,4,8,24])
    df = add_atr(df, high_col="high", low_col="low", close_col="raw_close", period=14)

    # 2) ROLLING STATS
    key_cols = [c for c in ["raw_close","volume"] if c in df.columns]
    df = add_rolling_stats(df, cols=key_cols, windows=[5,10,20,50])

    # 3) PRICE STRUCTURE FEATURES
    df["typical_price"]    = (df["high"] + df["low"] + df["close"]) / 3
    df["hlcc4"]            = (df["high"] + df["low"] + 2 * df["close"]) / 4
    df["range"]            = df["high"] - df["low"]
    df["body"]             = (df["raw_close"] - df["open"]).abs()
    df["upper_wick"]       = df["high"] - df[["open","close"]].max(axis=1)
    df["lower_wick"]       = df[["open","close"]].min(axis=1) - df["low"]
    df["body_range_ratio"] = df["body"] / df["range"].replace(0, np.nan)
    df["range_rank20"]     = df["range"].rolling(20).apply(
        lambda arr: (arr[-1] - arr.min()) / (arr.max() - arr.min() + 1e-8), raw=True)

    # 4) TA INDICATORS
    df["mid_price"]   = (df["high"] + df["low"]) / 2
    df["delta_price"] = df["raw_close"] - df["open"]
    df["ofi_1"]       = df["delta_price"] * df["volume"]
    for w in [2,3,4]:
        df[f"ofi_{w}"] = df["ofi_1"].rolling(w).sum()

    df["EMA_14"]      = ta.trend.EMAIndicator(df["raw_close"], window=14).ema_indicator()
    macd              = ta.trend.MACD(df["raw_close"])
    df["MACD"]        = macd.macd()
    df["MACD_signal"] = macd.macd_signal()
    df["RSI"]         = ta.momentum.RSIIndicator(df["raw_close"], window=14).rsi()
    stoch             = ta.momentum.StochasticOscillator(df["high"], df["low"], df["raw_close"])
    df["stoch_k"]     = stoch.stoch()
    df["stoch_d"]     = stoch.stoch_signal()
    df["roc"]         = ta.momentum.ROCIndicator(df["raw_close"], window=12).roc()
    df["ATR_ta"]      = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["raw_close"], window=14
    ).average_true_range()
    df["Momentum"]    = df["raw_close"].diff()

    # 5) Volume‐profile & sweep logic
    df["LiquiditySweepHigh"] = (df["high"] > df["high"].rolling(20).max().shift(1)).astype(int)
    df["LiquiditySweepLow"]  = (df["low"]  < df["low"].rolling(20).min().shift(1)).astype(int)
    df["Volume_SMA_20"]      = df["volume"].rolling(20).mean()
    df["HighVol_Momentum"]   = df["Momentum"] * (df["volume"] / df["Volume_SMA_20"])

    # 6) MT5‐Compatible Features
    bb = ta.volatility.BollingerBands(df["raw_close"], window=20, window_dev=2)
    df["bb_mid"]   = bb.bollinger_mavg()
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = df["bb_upper"] - df["bb_lower"]
    df["cci"]      = ta.trend.CCIIndicator(
        df["high"], df["low"], df["raw_close"], window=20
    ).cci()
    df["obv"]      = ta.volume.OnBalanceVolumeIndicator(
        df["raw_close"], df["volume"]
    ).on_balance_volume()
    df["vwap"]     = ta.volume.VolumeWeightedAveragePrice(
        df["high"], df["low"], df["raw_close"], df["volume"], window=20
    ).volume_weighted_average_price()
    df["rsi_vol"]  = ta.momentum.RSIIndicator(df["volume"], window=20).rsi()
    df["vol_4"]    = df["raw_close"].pct_change().rolling(4).std()
    df["vol_24"]   = df["raw_close"].pct_change().rolling(24).std()

    # 7) Pattern detection flags
    df["marubozu"] = (df["body"] / df["range"]).fillna(0).gt(0.9).astype(int)
    df["doji"]     = (df["body"] / df["range"]).fillna(0).lt(0.1).astype(int)

    # 8) OB & FVG zone flags
    df["prev_bearish"] = df["open"].shift(1) > df["close"].shift(1)
    df["demand_zone"]  = (df["prev_bearish"] & (df["high"] > df["high"].shift(1))).astype(int)
    df["fvg"]          = (df["low"].shift(-1) > df["high"]).astype(int)
    df.drop(columns=["prev_bearish"], inplace=True)

    # 9) Temporal features
    df["hour"]      = df["datetime"].dt.hour
    df["dayofweek"] = df["datetime"].dt.dayofweek

    # 10) Clip outliers
    clip_cols = [
        "typical_price","hlcc4","range","body","upper_wick","lower_wick",
        "body_range_ratio","range_rank20","mid_price","ofi_1","ofi_2",
        "ofi_3","ofi_4","EMA_14","MACD","MACD_signal","RSI","stoch_k",
        "stoch_d","roc","ATR_ta","Momentum","LiquiditySweepHigh",
        "LiquiditySweepLow","HighVol_Momentum","bb_mid","bb_upper",
        "bb_lower","bb_width","cci","obv","vwap","rsi_vol","vol_4",
        "vol_24","marubozu","doji","demand_zone","fvg"
    ]
    for c in clip_cols:
        if c in df:
            lo, hi = df[c].quantile(0.01), df[c].quantile(0.99)
            df[c] = df[c].clip(lo, hi)

    # 11) Drop rows missing real features
    num_feats = df.select_dtypes("number").columns.drop("raw_close")
    df = df.dropna(subset=num_feats, how="all").reset_index(drop=True)

    return df
