# india/ai_reopen.py
"""
ARJUNA AI REOPEN — the signboard, made live.

We are NOT abandoning AI. It is TEMPORARILY CLOSED until better DATA arrives (see
docs/ARJUNA_V4_ROADMAP.md). This script checks which data triggers exist on disk right now and
prints which AI model families are CLOSED vs ARMED to reopen. The day a dataset lands, this flips
to ARMED and tells you exactly which models to (carefully, gated) reopen in the Lab.

Run: python india/ai_reopen.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.config import MODELS_FROZEN_UNTIL_DATA_ARRIVES
RAW = ROOT / "data" / "raw" / "india"

# trigger: (name, expected data file(s), min usable history note, models to reopen)
TRIGGERS = [
    ("Point-in-time fundamentals", [RAW / "pit_fundamentals.parquet"],
     "must be AS-KNOWN-ON-DATE (current fundamentals are point-lagged = look-ahead)",
     ["XGBoost", "CatBoost", "TabNet", "FT-Transformer", "TabPFN", "DeepFM", "SAINT"]),
    ("Historical news archive", [RAW / "news_archive.parquet"],
     "years of timestamped articles (news_sentiment.parquet is forward-only / too short)",
     ["FinBERT", "DeBERTa", "FinGPT", "Llama", "Longformer"]),
    ("Analyst revisions", [RAW / "analyst_revisions.parquet"],
     "timestamped EPS/revenue estimate revisions (IBES/Zacks-style)",
     ["LightGBM", "CatBoost", "LambdaMART (ranking)"]),
    ("Options / derivatives flow", [RAW / "options_flow.parquet"],
     "intraday/EOD option order-flow or skew history",
     ["Temporal Fusion Transformer", "Chronos", "PatchTST", "TimesFM"]),
    ("Institutional-scale panel (for RL)", [RAW / "global_panel.parquet"],
     "multi-decade, ~20k stocks, multi-asset + macro + realistic costs",
     ["PPO / SAC at institutional scale"]),
]


def main():
    print("=" * 70)
    print("  ARJUNA — AI REOPEN STATUS  (signboard, not tombstone)")
    print("=" * 70)
    print(f"  MODELS_FROZEN_UNTIL_DATA_ARRIVES = {MODELS_FROZEN_UNTIL_DATA_ARRIVES}")
    print("  Doctrine: Data -> Features -> Targets -> Validation -> Models (sophistication LAST)\n")
    armed = 0
    for name, files, note, models in TRIGGERS:
        have = all(f.exists() for f in files)
        armed += have
        status = "ARMED  ->" if have else "CLOSED   "
        print(f"  [{status}] {name}")
        print(f"             needs: {note}")
        print(f"             reopens: {', '.join(models)}\n")
    print("-" * 70)
    if armed == 0:
        print("  All triggers CLOSED. No data unlock yet -> stay rule-based (Core v2.2 frozen).")
        print("  Highest-leverage move remains: acquire POINT-IN-TIME FUNDAMENTALS first.")
    else:
        print(f"  {armed} trigger(s) ARMED. Reopen the listed models IN A FRESH LAB (india/lab/),")
        print("  gated by walk-forward CV + deflated Sharpe + PBO + realistic costs, then the")
        print("  production gate (must beat Core's rolling Sharpe net of cost on forward data).")


if __name__ == "__main__":
    main()
