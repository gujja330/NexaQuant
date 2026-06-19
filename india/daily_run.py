# india/daily_run.py
"""
ARJUNA daily forward run (paper). Orchestrates the live experiment:
  1. score news sentiment for the basket  -> appends to news_sentiment.parquet (forward history)
  2. generate the news-FILTERED equal-weight basket (run_arjuna)
  3. append today's basket snapshot to output/paper_log.csv (so we can measure forward P&L later)

No real orders (cash stays out by design). Meant to be run daily by a scheduler.
Optional: --pull to refresh prices from Angel first (heavier; do weekly, not every day).

  python india/daily_run.py
  python india/daily_run.py --pull --capital 100000
"""
import argparse, subprocess, sys
from datetime import datetime
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"; OUT.mkdir(exist_ok=True)
PY = sys.executable


def step(label, args):
    print(f"\n===== {label} =====", flush=True)
    r = subprocess.run([PY, str(ROOT / "india" / args[0])] + args[1:], cwd=str(ROOT))
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", default="100000")
    ap.add_argument("--pull", action="store_true", help="refresh Angel prices first (weekly)")
    a = ap.parse_args()
    print(f"######## ARJUNA DAILY RUN {datetime.now().isoformat(timespec='seconds')} ########", flush=True)

    if a.pull:
        step("1. refresh prices (Angel, incremental)", ["broker_angelone.py", "--pull"])
    step("2. FII/DII flows (NSE, forward)", ["fii_dii.py"])
    step("3. news sentiment (FinBERT + Google News)", ["news_sentiment.py"])
    step("4. risk-weighted basket (+regime +global +news filter)", ["run_arjuna.py", "--capital", a.capital])

    # append today's basket to the forward paper log
    blot = OUT / "arjuna_paper_orders.csv"
    if blot.exists():
        snap = pd.read_csv(blot)
        snap["run_date"] = datetime.now().date().isoformat()
        log = OUT / "paper_log.csv"
        if log.exists():
            snap = pd.concat([pd.read_csv(log), snap], ignore_index=True)
        snap.to_csv(log, index=False)
        print(f"\n  forward paper snapshot appended -> {log}  ({len(snap)} total rows)")
    print("\n######## DONE ########", flush=True)


if __name__ == "__main__":
    main()
