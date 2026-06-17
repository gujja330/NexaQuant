# intelligence/rl_position_sizer.py
import os
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import SAC
from stable_baselines3.common.vec_env import DummyVecEnv
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class PositionSizingEnv(gym.Env):
    def __init__(self, df: np.ndarray, pip_value: float, max_risk: float = 0.02):
        super().__init__()
        self.df = df
        self.pip_value = pip_value
        self.max_risk = max_risk
        self.current_step = 0
        self.max_steps = len(df) - 1
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(df.shape[1],), dtype=np.float32)

    def reset(self, *, seed: Optional[int] = None, options: Optional[Dict] = None):
        super().reset(seed=seed)
        self.current_step = 0
        return self.df[0], {}

    def step(self, action):
        position_ratio = action[0]
        if self.current_step >= self.max_steps:
            return self.df[-1], 0.0, True, False, {}

        next_step = min(self.current_step + 1, self.max_steps)
        current_close = self.df[self.current_step][-1]
        next_close = self.df[next_step][-1]

        pips = (next_close - current_close) / self.pip_value
        position_size = position_ratio * 10
        pnl = pips * position_size
        risk_penalty = 0.1 * (position_ratio - 0.5) ** 2
        reward = pnl - risk_penalty

        self.current_step = next_step
        done = self.current_step >= self.max_steps
        return self.df[self.current_step], reward, done, False, {}

class RLPositionSizer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.model = None
        self.model_path = "./models/rl_position_sizer.zip"
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

    def train(self, df: np.ndarray, pip_value: float):
        env = DummyVecEnv([lambda: PositionSizingEnv(df, pip_value)])
        self.model = SAC("MlpPolicy", env, verbose=0, learning_rate=3e-4)
        self.model.learn(total_timesteps=50000)
        self.model.save(self.model_path)
        logger.info("RL position sizer trained and saved")

    def load_or_train(self, df: np.ndarray, pip_value: float):
        if os.path.exists(self.model_path):
            self.model = SAC.load(self.model_path)
            logger.info("Loaded pre-trained RL position sizer")
        else:
            self.train(df, pip_value)

    def get_position_ratio(self, state: np.ndarray) -> float:
        if self.model is None:
            return 0.5
        action, _ = self.model.predict(state, deterministic=True)
        return float(np.clip(action[0], 0.0, 1.0))