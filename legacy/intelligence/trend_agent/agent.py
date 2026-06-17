# intelligence/trend_agent/agent.py
```python
import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd
import yaml
from stable_baselines3 import SAC
from stable_baselines3.common.env_checker import check_env
from typing import Dict, Any

class TrendTradingEnv(gym.Env):
    def __init__(self, config_path: str = "config/base_config.yaml"):
        super(TrendTradingEnv, self).__init__()
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        self.symbols = self.config["system"]["symbols"]
        self.window_size = self.config["agents"]["trend"]["state_features"]
        self.risk_per_trade = self.config["system"]["risk_per_trade"]
        self.current_step = self.window_size
        self.action_space = spaces.Discrete(self.config["agents"]["trend"]["action_space"])
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(self.window_size,), dtype=np.float32
        )
        self.df = None

    def set_data(self, df: pd.DataFrame):
        self.df = df.copy()
        self.current_step = self.window_size

    def _get_observation(self):
        if self.df is None:
            raise ValueError("Data not set. Call set_data() first.")
        window = self.df.iloc[self.current_step - self.window_size:self.current_step]
        obs = np.concatenate([
            window['close'].pct_change().fillna(0).values,
            window['volume'].pct_change().fillna(0).values,
        ])
        if len(obs) < self.window_size:
            obs = np.pad(obs, (0, self.window_size - len(obs)), 'constant')
        elif len(obs) > self.window_size:
            obs = obs[-self.window_size:]
        return obs.astype(np.float32)

    def step(self, action):
        self.current_step += 1
        if self.current_step >= len(self.df):
            return self._get_observation(), 0, True, False, {}
        price = self.df['close'].iloc[self.current_step]
        reward = self._calculate_reward(action, price)
        done = self.current_step >= len(self.df) - 1
        return self._get_observation(), reward, done, False, {}

    def _calculate_reward(self, action, price):
        position = action - 2
        future_window = min(5, len(self.df) - self.current_step - 1)
        if future_window <= 0:
            return 0
        future_returns = self.df['close'].pct_change().iloc[self.current_step + 1:self.current_step + 1 + future_window].mean()
        slippage_penalty = 0.001 * abs(position)
        risk_adjusted_return = position * future_returns - slippage_penalty
        return risk_adjusted_return

    def reset(self, seed=None):
        super().reset(seed=seed)
        self.current_step = self.window_size
        return self._get_observation(), {}

class TrendAgent:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        self.config_path = config_path
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        self.model = None
        self.env = None

    def train(self, df: pd.DataFrame):
        self.env = TrendTradingEnv(self.config_path)
        self.env.set_data(df)
        check_env(self.env)
        self.model = SAC(
            "MlpPolicy",
            self.env,
            verbose=0,
            device="cpu",
            learning_rate=3e-4,
            buffer_size=100000,
            batch_size=64,
            gamma=0.99,
            tau=0.005
        )
        total_timesteps = self.config.get("training", {}).get("timesteps", 10000)
        self.model.learn(total_timesteps=total_timesteps)
        return self.model

    def predict(self, obs: np.ndarray):
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        action, _ = self.model.predict(obs, deterministic=True)
        confidence = 0.85
        return int(action), confidence
```