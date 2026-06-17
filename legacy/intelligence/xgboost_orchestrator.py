# intelligence/xgboost_orchestrator.py
import os
import numpy as np
import pandas as pd
import xgboost as xgb
from typing import Dict, Any, List, Tuple
import logging

logger = logging.getLogger(__name__)

class XGBoostOrchestrator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.model = None
        self.feature_names = None
        self.model_path = "./models/xgb_orchestrator.json"
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

    def _generate_synthetic_labels(self, df: pd.DataFrame) -> np.ndarray:
        n = len(df)
        labels = np.zeros(n, dtype=int)
        
        # Create safe fallback series of same length
        zeros = pd.Series(0.0, index=df.index)
        fifties = pd.Series(50.0, index=df.index)

        for i in range(30, n):
            regime = df['regime'].iloc[i] if 'regime' in df.columns else 1
            rsi = df['RSI'].iloc[i] if 'RSI' in df.columns else fifties.iloc[i]
            roc = df['ROC'].iloc[i] if 'ROC' in df.columns else zeros.iloc[i]
            vol = df['vol_24'].iloc[i] if 'vol_24' in df.columns else zeros.iloc[i]
            fvg = df['fvg'].iloc[i] if 'fvg' in df.columns else zeros.iloc[i]
            liq = df['LiquiditySweepHigh'].iloc[i] if 'LiquiditySweepHigh' in df.columns else zeros.iloc[i]

            score = 0
            if regime in [1, 2]:
                if roc > 0: score += 1
                if rsi > 55: score += 1
                if fvg > 0: score += 1
            else:  # regime 0
                if rsi < 35: score += 1
                if liq > 0: score += 1

            if vol > np.percentile(df['vol_24'].dropna(), 75) if 'vol_24' in df.columns else 0.01:
                if abs(roc) > 0.01:
                    score += 1

            if score >= 2:
                labels[i] = 1
            elif score <= -2:
                labels[i] = -1
            else:
                labels[i] = 0
        return labels

    def train_or_load(self, df: pd.DataFrame):
        if os.path.exists(self.model_path):
            self.model = xgb.XGBClassifier()
            self.model.load_model(self.model_path)
            logger.info("Loaded pre-trained XGBoost orchestrator")
            return

        exclude_cols = {'symbol', 'time', 'raw_close', 'tick_volume', 'open', 'high', 'low', 'close', 'volume'}
        feature_cols = sorted([c for c in df.columns if c not in exclude_cols and np.issubdtype(df[c].dtype, np.number)])
        if not feature_cols:
            raise ValueError("No numeric features for XGBoost")

        X = df[feature_cols].iloc[30:].values
        y = self._generate_synthetic_labels(df)[30:]
        y = np.where(y == -1, 2, y)

        if len(np.unique(y)) < 2:
            logger.warning("Insufficient label diversity. Using fallback.")
            self.model = None
            self.feature_names = feature_cols
            return

        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            objective='multi:softmax',
            num_class=3,
            random_state=42
        )
        self.model.fit(X, y)
        self.model.save_model(self.model_path)
        self.feature_names = feature_cols
        logger.info(f"XGBoost orchestrator trained and saved to {self.model_path}")

    def predict_action(self, state: np.ndarray, feature_names: List[str]) -> Tuple[int, Dict[str, Any]]:
        if self.model is None:
            return self._fallback_action(state, feature_names)

        if self.feature_names:
            try:
                state_ordered = [state[feature_names.index(f)] for f in self.feature_names if f in feature_names]
                if len(state_ordered) != len(self.feature_names):
                    return self._fallback_action(state, feature_names)
                pred = self.model.predict([state_ordered])[0]
            except (ValueError, KeyError):
                return self._fallback_action(state, feature_names)
        else:
            pred = self.model.predict([state])[0]

        action_map = {0: 0, 1: 1, 2: -1}
        return action_map.get(int(pred), 0), {"model": "xgboost", "raw_pred": int(pred)}

    def _fallback_action(self, state: np.ndarray, feature_names: List[str]) -> Tuple[int, Dict[str, Any]]:
        feat_dict = dict(zip(feature_names, state))
        regime = feat_dict.get('regime', 1)
        rsi = feat_dict.get('RSI', 50)
        roc = feat_dict.get('ROC', 0)
        fvg = feat_dict.get('fvg', 0)
        liq = feat_dict.get('LiquiditySweepHigh', 0)

        if regime in [1, 2] and rsi > 55 and roc > 0 and fvg > 0:
            return 1, {"model": "fallback", "reason": "trend_entry"}
        elif regime == 0 and rsi < 35 and liq > 0:
            return 1, {"model": "fallback", "reason": "mean_rev_entry"}
        elif regime == 0 and rsi > 70:
            return -1, {"model": "fallback", "reason": "overbought_short"}
        return 0, {"model": "fallback", "reason": "hold"}