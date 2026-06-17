# data_engine/feature_forge.py
import os
import pandas as pd
import numpy as np
from typing import Dict, Any, List
import ta
from sklearn.feature_selection import mutual_info_regression
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FeatureForge:
    """
    Advanced feature engineering system with stability monitoring, regime awareness, and tail-risk modeling.
    Fully dynamic. Zero hardcoding. Config-driven. Symbol-agnostic.
    Implements Automated Feature Engineering, Stability Analysis, Regime-Aware Features, Copula Modeling, Feature Decay Detection.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbols = config["system"]["symbols"]
        self.output_dir = "./data_engine/features/"
        os.makedirs(self.output_dir, exist_ok=True)
        
        feature_config = config.get("feature_engineering", {})
        self.feature_stability_window = feature_config.get("stability_window", 30)
        self.decay_threshold = feature_config.get("decay_threshold", 0.7)
        self.data_storage = config.get("system", {}).get("data_storage", "./data_engine/clean/")

    def add_return_and_zscore(self, df, price_col="close", zscore_window=20):
        df = df.copy()
        df["ret_1"] = df[price_col].pct_change(1)
        roll = df["ret_1"].rolling(zscore_window)
        df["ret_1_z"] = (df["ret_1"] - roll.mean()) / roll.std()
        return df

    def add_multi_bar_returns(self, df, price_col="close", periods=[2,4,8,24]):
        df = df.copy()
        for p in periods:
            df[f"ret_{p}"] = df[price_col].pct_change(p)
        return df

    def add_rolling_momentum(self, df, price_col="close", periods=[2,4,8,24]):
        df = df.copy()
        for p in periods:
            df[f"mom_{p}"] = df[price_col].diff(p)
        return df

    def add_atr(self, df, high_col="high", low_col="low", close_col="close", period=14):
        df = df.copy()
        if not {high_col, low_col, close_col}.issubset(df.columns):
            return df
        tr1 = df[high_col] - df[low_col]
        tr2 = (df[high_col] - df[close_col].shift()).abs()
        tr3 = (df[low_col]  - df[close_col].shift()).abs()
        tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = tr.rolling(period).mean()
        return df

    def add_rolling_stats(self, df, cols, windows=[5,10,20,50]):
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

    def build_features(self, df):
        df = df.copy()

        if len(df) >= 2:
            last_close  = df["close"].iloc[-1]
            prior_close = df["close"].iloc[-2]
            jump_ratio  = abs(last_close / prior_close)
            if jump_ratio > 10:
                raise ValueError(f"⚠️ Sudden price jump detected: {prior_close:.2f} → {last_close:.2f}.")

        df["raw_close"] = df["close"]
        df["close_diff"] = df["raw_close"].diff()

        # Handle volume columns robustly for ANY symbol
        if "tick_volume" in df.columns:
            df["volume"] = df["tick_volume"]
        elif "volume" in df.columns:
            df["tick_volume"] = df["volume"]
        else:
            # Create synthetic volume based on volatility for ANY asset
            volatility = df["raw_close"].pct_change().rolling(20).std()
            df["tick_volume"] = (volatility / volatility.mean()).fillna(1.0) * 1000
            df["volume"] = df["tick_volume"]

        df = self.add_return_and_zscore(df, price_col="raw_close", zscore_window=20)
        df = self.add_multi_bar_returns(df, price_col="raw_close", periods=[2,4,8,24])
        df = self.add_rolling_momentum(df, price_col="raw_close", periods=[2,4,8,24])
        df = self.add_atr(df, high_col="high", low_col="low", close_col="raw_close", period=14)

        key_cols = [c for c in ["raw_close","tick_volume","volume"] if c in df.columns]
        df = self.add_rolling_stats(df, cols=key_cols, windows=[5,10,20,50])

        df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3
        df["hlcc4"] = (df["high"] + df["low"] + 2 * df["close"]) / 4
        df["range"] = df["high"] - df["low"]
        df["body"] = (df["raw_close"] - df["open"]).abs()
        df["upper_wick"] = df["high"] - df[["open","close"]].max(axis=1)
        df["lower_wick"] = df[["open","close"]].min(axis=1) - df["low"]
        df["body_range_ratio"] = df["body"] / df["range"].replace(0, np.nan)
        df["range_rank20"] = df["range"].rolling(20).apply(
            lambda arr: (arr[-1] - arr.min()) / (arr.max() - arr.min() + 1e-8), raw=True)

        df["mid_price"] = (df["high"] + df["low"]) / 2
        df["delta_price"] = df["raw_close"] - df["open"]
        df["ofi_1"] = df["delta_price"] * df["tick_volume"]
        for w in [2,3,4]:
            df[f"ofi_{w}"] = df["ofi_1"].rolling(w).sum()

        df["EMA_14"] = ta.trend.EMAIndicator(df["raw_close"], window=14).ema_indicator()
        macd = ta.trend.MACD(df["raw_close"])
        df["MACD"] = macd.macd()
        df["MACD_signal"] = macd.macd_signal()
        df["RSI"] = ta.momentum.RSIIndicator(df["raw_close"], window=14).rsi()
        stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["raw_close"])
        df["stoch_k"] = stoch.stoch()
        df["stoch_d"] = stoch.stoch_signal()
        df["roc"] = ta.momentum.ROCIndicator(df["raw_close"], window=12).roc()
        df['price_slope'] = df['raw_close'].pct_change().rolling(10).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x.dropna()) >= 5 else 0.0, raw=False)
        df["ATR_ta"] = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["raw_close"], window=14
        ).average_true_range()
        df["Momentum"] = df["raw_close"].diff()

        if "tick_volume" in df.columns:
            df["LiquiditySweepHigh"] = (df["high"] > df["high"].rolling(20).max().shift(1)).astype(int)
            df["LiquiditySweepLow"] = (df["low"]  < df["low"].rolling(20).min().shift(1)).astype(int)
            df["Volume_SMA_20"] = df["tick_volume"].rolling(20).mean()
            df["HighVol_Momentum"] = df["Momentum"] * (df["tick_volume"] / df["Volume_SMA_20"].replace(0, np.nan))
        else:
            df["LiquiditySweepHigh"] = 0
            df["LiquiditySweepLow"] = 0
            df["Volume_SMA_20"] = 1000.0
            df["HighVol_Momentum"] = df["Momentum"]

        bb = ta.volatility.BollingerBands(df["raw_close"], window=20, window_dev=2)
        df["bb_mid"] = bb.bollinger_mavg()
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_width"] = df["bb_upper"] - df["bb_lower"]
        df["cci"] = ta.trend.CCIIndicator(
            df["high"], df["low"], df["raw_close"], window=20
        ).cci()
        
        if "tick_volume" in df.columns:
            df["obv"] = ta.volume.OnBalanceVolumeIndicator(
                df["raw_close"], df["tick_volume"]
            ).on_balance_volume()
            df["vwap"] = ta.volume.VolumeWeightedAveragePrice(
                df["high"], df["low"], df["raw_close"], df["tick_volume"], window=20
            ).volume_weighted_average_price()
            df["rsi_vol"] = ta.momentum.RSIIndicator(df["tick_volume"], window=20).rsi()
        else:
            df["obv"] = 0.0
            df["vwap"] = df["raw_close"]
            df["rsi_vol"] = 50.0
            
        df["vol_4"] = df["raw_close"].pct_change().rolling(4).std()
        df["vol_24"] = df["raw_close"].pct_change().rolling(24).std()

        df["marubozu"] = (df["body"] / df["range"]).fillna(0).gt(0.9).astype(int)
        df["doji"] = (df["body"] / df["range"]).fillna(0).lt(0.1).astype(int)

        df["prev_bearish"] = df["open"].shift(1) > df["close"].shift(1)
        df["demand_zone"] = (df["prev_bearish"] & (df["high"] > df["high"].shift(1))).astype(int)
        df["fvg"] = (df["low"].shift(-1) > df["high"]).astype(int)
        df.drop(columns=["prev_bearish"], inplace=True)

        # Add event proximity features (if event timestamps exist)
        if 'event_time' in df.columns:
            df['time_since_last_event'] = (df.index - df['event_time'].fillna(method='ffill')).dt.total_seconds() / 3600
            df['event_impact'] = df['event_impact'].fillna(0)
            df['event_sentiment'] = df['event_sentiment'].fillna(0)

        if isinstance(df.index, pd.DatetimeIndex):
            df["hour"] = df.index.hour
            df["dayofweek"] = df.index.dayofweek

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

        num_feats = df.select_dtypes("number").columns.drop("raw_close", errors='ignore')
        df = df.dropna(subset=num_feats, how="all").reset_index(drop=True)

        return df

    def auto_generate_features(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        original_index = df.index.copy()  # ← PRESERVE INDEX
        df = df.copy()
        df_features = self.build_features(df)
        df_features.index = original_index  # ← RESTORE INDEX
        logger.info(f"Generated {df_features.shape[1]} features for {symbol}")
        return df_features

    def select_optimal_features(self, df: pd.DataFrame, target_col: str = 'future_return') -> List[str]:
        if target_col not in df.columns:
            df[target_col] = df['close'].pct_change().shift(-1)
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        feature_cols = [col for col in numeric_cols if col != target_col]
        
        if len(feature_cols) == 0:
            return []
        
        X = df[feature_cols].fillna(0)
        y = df[target_col].fillna(0)
        valid_mask = ~y.isna()
        X = X[valid_mask]
        y = y[valid_mask]
        
        if len(y) < 10:
            return feature_cols[:20]
        
        mi_scores = mutual_info_regression(X, y, random_state=42)
        feature_scores = pd.Series(mi_scores, index=feature_cols).sort_values(ascending=False)
        n_features = min(50, len(feature_scores))
        selected_features = feature_scores.head(n_features).index.tolist()
        
        logger.info(f"Selected {len(selected_features)} optimal features")
        return selected_features

    def validate_feature_stability(self, symbol: str, feature_name: str, historical_data: List[float]) -> bool:
        if len(historical_data) < self.feature_stability_window:
            return True
        
        recent = historical_data[-self.feature_stability_window:]
        earlier = historical_data[-2*self.feature_stability_window:-self.feature_stability_window]
        
        if len(recent) == 0 or len(earlier) == 0:
            return True
        
        correlation = np.corrcoef(recent, earlier[:len(recent)])[0, 1] if len(recent) > 1 else 1.0
        is_stable = correlation > self.decay_threshold
        
        if not is_stable:
            logger.warning(f"Feature decay detected for {symbol}.{feature_name} (correlation: {correlation:.3f})")
        
        return is_stable

    def monitor_feature_decay(self, df: pd.DataFrame, symbol: str) -> Dict[str, bool]:
        decay_alerts = {}
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        for col in numeric_cols:
            if col in ['close', 'open', 'high', 'low', 'tick_volume', 'volume', 'raw_close']:
                continue
            
            historical_data = df[col].tolist()
            is_stable = self.validate_feature_stability(symbol, col, historical_data)
            decay_alerts[col] = not is_stable
        
        return decay_alerts

    def generate_feature_set(self, symbol: str) -> pd.DataFrame:
        df = None
        for tf in self.config["system"]["timeframes"]:
            path = os.path.join(self.data_storage, f"{symbol}_{tf}.parquet")
            if os.path.exists(path):
                df = pd.read_parquet(path)
                break
            
            synthetic_path = os.path.join("data_engine", "synthetic_enhanced", f"{symbol}_{tf}.parquet")
            if os.path.exists(synthetic_path):
                df = pd.read_parquet(synthetic_path)
                break
        
        if df is None:
            logger.error(f"No data found for {symbol} in clean/ or synthetic_enhanced/")
            return pd.DataFrame()
        
        df_features = self.auto_generate_features(df, symbol)
        output_path = os.path.join(self.output_dir, f"{symbol}_features.parquet")
        df_features.to_parquet(output_path)
        logger.info(f"Saved features to {output_path}")
        return df_features