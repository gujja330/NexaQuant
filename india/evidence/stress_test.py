# india/research/stress_test.py
"""
STRESS TESTS — how did Core v2.1 (HRP+regime+global, quarterly) behave in real corrections?
Measures period return, in-window max drawdown, and recovery vs Nifty. (COVID-2020 is pre-data:
our clean Angel history starts Dec-2020, so we test the stress windows we actually have.)

Run: python india/research/stress_test.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest

WINDOWS = [("2022 correction", "2022-01-01", "2022-06-30"),
           ("2023 dip", "2023-01-01", "2023-03-31"),
           ("2025 selloff", "2025-01-01", "2025-03-31"),
           ("2026 selloff", "2026-01-01", "2026-04-30")]


def dd(series):
    eq = (1 + series).cumprod(); return ((eq.cummax() - eq) / eq.cummax()).max()


def main():
    net, idx = backtest("hrp", regime="global", topn=15, sector_cap=3, rebal=63)
    nifty = idx.pct_change().reindex(net.index).fillna(0.0)
    print("=" * 70)
    print("  STRESS TESTS — Core v2.1 (15-stock quarterly) vs Nifty in real corrections")
    print("=" * 70)
    print(f"  {'window':<18}{'ARJUNA ret':>12}{'ARJUNA DD':>11}{'Nifty ret':>11}{'Nifty DD':>10}")
    for name, a, b in WINDOWS:
        s = net.loc[a:b]; n = nifty.loc[a:b]
        if len(s) < 5:
            continue
        sr = (1 + s).prod() - 1; nr = (1 + n).prod() - 1
        print(f"  {name:<18}{100*sr:>+11.1f}%{100*dd(s):>10.1f}%{100*nr:>+10.1f}%{100*dd(n):>9.1f}%")
    print("\n  COVID-2020: pre-data (clean history starts Dec-2020) -> cannot test; the regime + Global")
    print("  Risk overlay is the COVID-style defense (de-risks on VIX spike + S&P/USD stress).")


if __name__ == "__main__":
    main()
