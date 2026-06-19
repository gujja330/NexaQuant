# india/rl_test.py
"""
REINFORCEMENT LEARNING test (PPO) — a market-TIMING agent on the equal-weight basket.

RL is suited to sequential decisions, so we give it the job it can actually do: learn WHEN to be
invested. State = market regime (VIX z, Nifty momentum, Nifty>200DMA, breadth, last basket return).
Actions = {cash, half, full}. Reward = exposure * next-month basket return - turnover cost.
Train 2021-2023, test 2024-2026. Compare vs always-invested basket and Nifty.

If PPO can't beat buy-and-hold of the basket OOS, RL adds nothing here either.

Run: python india/rl_test.py
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

import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO


def market_series():
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    rets = closes.pct_change()
    dates = closes.index[::21]                       # monthly grid
    basket = rets.mean(axis=1)                        # equal-weight basket daily return
    basket_m = (1 + basket).groupby((np.arange(len(basket)) // 21)).prod() - 1  # ~monthly
    # build monthly state table
    rows = []
    ma200 = idx.rolling(200).mean()
    above = (closes > closes.rolling(200).mean())
    for i, dt in enumerate(dates):
        if dt not in idx.index:
            continue
        v = (vix.loc[dt] - vix.loc[:dt].rolling(252).mean().loc[dt]) / (vix.loc[:dt].rolling(252).std().loc[dt] + 1e-9) if vix is not None else 0.0
        nm = idx.loc[dt] / idx.loc[:dt].iloc[-126] - 1 if i >= 6 else 0.0
        ab = float(idx.loc[dt] > ma200.loc[dt]) if dt in ma200.index and np.isfinite(ma200.loc[dt]) else 1.0
        breadth = float(above.loc[dt].mean()) if dt in above.index else 0.5
        rows.append([dt, np.nan_to_num(v), np.nan_to_num(nm), ab, breadth])
    st = pd.DataFrame(rows, columns=["date", "vix_z", "nifty_mom", "above200", "breadth"]).set_index("date")
    # next-month basket return aligned to each monthly date
    bm = pd.Series((1 + basket).groupby(np.arange(len(basket)) // 21).prod().values - 1)
    bm.index = dates[:len(bm)]
    st["fwd"] = bm.reindex(st.index).shift(-1)
    st["last_ret"] = bm.reindex(st.index).shift(1).fillna(0)
    return st.dropna(subset=["fwd"])


EXPO = {0: 0.0, 1: 0.5, 2: 1.0}


class TimingEnv(gym.Env):
    def __init__(self, tbl):
        super().__init__()
        self.tbl = tbl.reset_index(drop=True)
        self.observation_space = spaces.Box(-5, 5, (5,), np.float32)
        self.action_space = spaces.Discrete(3)
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed); self.i = 0; self.prev = 1.0
        return self._obs(), {}
    def _obs(self):
        r = self.tbl.iloc[self.i]
        return np.array([r.vix_z, r.nifty_mom, r.above200, r.breadth, self.prev], np.float32)
    def step(self, a):
        r = self.tbl.iloc[self.i]; expo = EXPO[int(a)]
        reward = expo * r.fwd - abs(expo - self.prev) * (COST_BPS / 1e4)
        self.prev = expo; self.i += 1
        done = self.i >= len(self.tbl)
        obs = self._obs() if not done else np.zeros(5, np.float32)
        return obs, float(reward), done, False, {}


def equity(tbl, exposures):
    r = (exposures * tbl["fwd"].values)
    return float((1 + pd.Series(r)).prod())


if __name__ == "__main__":
    print("=" * 64)
    print("  RL (PPO) market-timing agent on the equal-weight basket")
    print("=" * 64)
    st = market_series()
    split = st.index[int(len(st) * 0.55)]
    tr, te = st[st.index < split], st[st.index >= split]
    print(f"  train {tr.index.min().date()}->{tr.index.max().date()} ({len(tr)})   "
          f"test {te.index.min().date()}->{te.index.max().date()} ({len(te)})")

    env = TimingEnv(tr)
    model = PPO("MlpPolicy", env, verbose=0, seed=0, n_steps=128, batch_size=64, gae_lambda=0.95)
    model.learn(total_timesteps=20000)

    # evaluate deterministic policy OOS
    expos = []
    e = TimingEnv(te); obs, _ = e.reset()
    for _ in range(len(te)):
        a, _ = model.predict(obs, deterministic=True)
        expos.append(EXPO[int(a)]); obs, _, done, _, _ = e.step(a)
        if done: break
    expos = np.array(expos[:len(te)])
    yrs = len(te) * 21 / 252
    rl_eq = equity(te, expos); hold_eq = equity(te, np.ones(len(te)))
    rl_c = 100 * (rl_eq ** (1 / yrs) - 1); hold_c = 100 * (hold_eq ** (1 / yrs) - 1)
    print(f"\n  OOS ({yrs:.1f}y):")
    print(f"  RL-timed basket     CAGR {rl_c:>6.1f}%   Rs1L -> Rs{rl_eq*1e5:>10,.0f}   (avg exposure {expos.mean():.2f})")
    print(f"  always-in basket    CAGR {hold_c:>6.1f}%   Rs1L -> Rs{hold_eq*1e5:>10,.0f}")
    print(f"\n  RL beat buy-and-hold? {'YES' if rl_eq > hold_eq else 'NO'}  "
          f"(if NO, RL adds nothing on this data)")
