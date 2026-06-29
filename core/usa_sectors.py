# core/usa_sectors.py
"""
USA SECTOR CLASSIFICATION — real GICS-style sectors for the dynamic universe (no more "Other").

Fetches each universe symbol's sector from Yahoo (one-time, cached to markets/usa/sectors.csv) and maps
Yahoo's labels to the clean sector names the engine + Sector Intelligence use. Every stock gets exactly
one real sector. (Later this can be swapped for SEC SIC-based classification without changing callers.)

Run:  python -m core.usa_sectors --build
"""
import sys, warnings
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
OUT = ROOT / "markets" / "usa" / "sectors.csv"

GICS = {
    "Technology": "Tech", "Financial Services": "Financials", "Healthcare": "Healthcare",
    "Consumer Cyclical": "Consumer Disc", "Consumer Defensive": "Staples",
    "Communication Services": "Communication", "Industrials": "Industrials", "Energy": "Energy",
    "Utilities": "Utilities", "Real Estate": "Real Estate", "Basic Materials": "Materials",
}


def build():
    import yfinance as yf
    from core.usa_universe import load_universe
    from markets.usa.config import SECTORS as STARTER
    syms = load_universe() or sorted(STARTER)
    rows = []
    for s in syms:
        sec = None
        try:
            sec = yf.Ticker(s).get_info().get("sector")
        except Exception:
            pass
        rows.append({"symbol": s, "sector": GICS.get(sec, sec or STARTER.get(s, "Other"))})
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    return df


def load_sectors():
    if OUT.exists():
        d = pd.read_csv(OUT)
        return dict(zip(d["symbol"], d["sector"]))
    return {}


def main():
    if "--build" in sys.argv:
        df = build()
        n_other = int((df["sector"] == "Other").sum())
        print(f"  classified {len(df)} symbols -> {OUT.relative_to(ROOT)}  ({n_other} still Other)")
        print(df["sector"].value_counts().to_string())
    else:
        m = load_sectors()
        print(f"  cached sectors: {len(m)} symbols" if m else "  none yet — run with --build")


if __name__ == "__main__":
    main()
