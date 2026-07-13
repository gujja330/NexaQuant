# india/ai_lab/LAB006_Exit_Strategy/score_path_collector.py
"""
PIT SCORE COLLECTOR — daily append of the "score" column for currently-held stocks.

Rule A (score-drop early exit) cannot be historically backtested because scores are computed live
each run (they would leak future info if reconstructed). We start collecting daily point-in-time
scores forward from today. Six months later, we'll have enough data to test Rule A properly.

Reads data/aegis_today.csv, extracts (recommended_date, Stock, Score /100), and appends to
data/aegis_score_paths.csv (idempotent per date+symbol). Nothing else. Non-fatal on any error.

Call from run_daily.bat or the GitHub workflow after recommendation_generator.py.

Run: python india/ai_lab/LAB006_Exit_Strategy/score_path_collector.py
"""
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
CANON = ROOT / "data" / "aegis_today.csv"
OUT = ROOT / "data" / "aegis_score_paths.csv"
COLS = ["date", "symbol", "sector", "score", "strength", "weight", "current_price"]


def main():
    if not CANON.exists():
        print("  no aegis_today.csv — nothing to collect."); return
    t = pd.read_csv(CANON)
    if t.empty or "Stock" not in t.columns:
        print("  aegis_today.csv empty or malformed."); return
    date = str(t["Generated"].iloc[0]) if "Generated" in t else pd.Timestamp.now().date().isoformat()

    rows = []
    for _, r in t.iterrows():
        try:
            score = float(r.get("Score /100")) if pd.notna(r.get("Score /100")) else None
        except Exception:
            score = None
        try:
            wt = float(r.get("Weight %")) if pd.notna(r.get("Weight %")) else None
        except Exception:
            wt = None
        try:
            cp = float(r.get("Current Price")) if pd.notna(r.get("Current Price")) else None
        except Exception:
            cp = None
        rows.append({"date": date, "symbol": r.get("Stock", ""), "sector": r.get("Sector", ""),
                     "score": score, "strength": r.get("Strength", ""), "weight": wt,
                     "current_price": cp})
    new = pd.DataFrame(rows, columns=COLS)

    if OUT.exists():
        old = pd.read_csv(OUT)
        # idempotent: drop any existing (date, symbol) that would collide, then append
        keep = old[~((old["date"].astype(str) == date) & (old["symbol"].isin(new["symbol"])))]
        combined = pd.concat([keep, new], ignore_index=True)
    else:
        combined = new
    combined.to_csv(OUT, index=False)
    print(f"  score_paths: appended {len(new)} rows for {date} -> {OUT.relative_to(ROOT)} "
          f"({len(combined)} total rows across {combined['date'].nunique()} dates)")


if __name__ == "__main__":
    main()
