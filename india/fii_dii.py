# india/fii_dii.py
"""
FII/DII FLOW ENGINE (Layer 1, live) — foreign (FII) & domestic-institutional (DII) cash flows
strongly drive the Indian market. NSE publishes the LATEST day only (no free history), so — like
news — this is a FORWARD-collected signal: run daily, it accumulates into a usable flow regime.

  python india/fii_dii.py            # fetch latest, append to data/raw/india/fii_dii.parquet
  from india.fii_dii import flow_signal   # -> risk-on/off tilt from accumulated history

Flow regime: persistent heavy NET SELLING (FII+DII) = risk-off (cut exposure); heavy buying = risk-on.
Backtest note: NOT backtestable (no free history) -> validated forward only.
"""
import sys, json, urllib.request, warnings
from datetime import datetime
from pathlib import Path
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "india" / "fii_dii.parquet"
URL = "https://www.nseindia.com/api/fiidiiTradeReact"


def fetch_latest():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0",
                                "Accept": "application/json", "Referer": "https://www.nseindia.com/"})
    data = json.loads(urllib.request.urlopen(req, timeout=20).read())
    row = {"ts": datetime.now().isoformat(timespec="seconds")}
    for r in data:
        cat = r.get("category", "").strip().upper().split()[0]   # FII / DII
        row[f"{cat}_net"] = float(r.get("netValue", 0))
        row["date"] = r.get("date")
    return row


def flow_signal(window=5):
    """Exposure tilt in (0,1] from accumulated flow history (forward). 1.0 if no data yet."""
    if not OUT.exists():
        return 1.0
    df = pd.read_parquet(OUT)
    if len(df) < window:
        return 1.0
    net = (df.get("FII_net", 0) + df.get("DII_net", 0)).tail(window)
    z = (net.mean() - df.get("FII_net", 0).add(df.get("DII_net", 0)).mean()) / \
        (df.get("FII_net", 0).add(df.get("DII_net", 0)).std() + 1e-9)
    # persistent heavy net selling -> de-risk
    return 0.7 if z < -1.0 else (0.85 if z < -0.3 else 1.0)


def main():
    try:
        row = fetch_latest()
    except Exception as e:
        print(f"  ! NSE fetch failed ({type(e).__name__}); skip. {str(e)[:80]}"); return
    df = pd.DataFrame([row])
    if OUT.exists():
        prev = pd.read_parquet(OUT)
        if "date" in prev and row.get("date") in set(prev.get("date", [])):
            print(f"  {row.get('date')} already recorded."); return
        df = pd.concat([prev, df], ignore_index=True)
    df.to_parquet(OUT)
    print(f"  {row.get('date')}  FII net Rs{row.get('FII_net', 0):,.0f} Cr   DII net Rs{row.get('DII_net', 0):,.0f} Cr")
    print(f"  saved -> {OUT} ({len(df)} days)   current flow tilt: {flow_signal():.2f}")


if __name__ == "__main__":
    main()
