"""DEV028 · v1.5 · DNA feedback CLI.

Reads reports/recommendation_dna.parquet + reports/learning.parquet +
reports/recommendations.json. Emits reports/recommendation_dna_feedback.json."""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from recommendation_dna.lib import feedback                                             # noqa: E402


def _banner(msg: str) -> None:
    print(); print("=" * 72); print(f"  {msg}"); print("=" * 72)


def main() -> int:
    t0 = time.time()
    _banner("DEV028 · v1.5 · DNA FEEDBACK LOOP")

    result = feedback.build_feedback()
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    result["run_utc"]  = datetime.now(timezone.utc).isoformat() + "Z"
    result["engine"]   = "Adaptive Recommendation Engine"
    result["version"]  = "v1.5 · DNA feedback"
    result["governance"] = ("Advisory. Pattern priors are historical context, not "
                              "predictions. Does not mutate immutable DNA store.")

    _banner("STEP 1/2 · Compute pattern statistics + per-rec priors")
    print(f"  DNA records:        {result['n_dna_records']}")
    print(f"  learning records:   {result['n_learning_records']}")
    print(f"  current recs:       {result['n_current_recs']}")
    print(f"  with evidence:      {result['n_with_evidence']}")
    print(f"  without evidence:   {result['n_without_evidence']}")
    print(f"  patterns discovered:{result['n_patterns']}")
    print(f"  high-prior recs:    {result['n_high_prior']} (win rate >= 0.65)")
    print(f"  low-prior recs:     {result['n_low_prior']} (win rate <= 0.35)")

    _banner("TOP PATTERNS (by historical win rate)")
    for p in result["pattern_leaderboard"][:8]:
        print(f"  {p['pattern']:<60} n_dna={p['n_dna']:>3} "
                f"wr={p['hist_win_rate']:>6.3f} avg_ret={p['hist_avg_return']:>7.4f}")

    _banner("BOTTOM PATTERNS")
    for p in result["pattern_bottom"][-5:]:
        print(f"  {p['pattern']:<60} n_dna={p['n_dna']:>3} "
                f"wr={p['hist_win_rate']:>6.3f} avg_ret={p['hist_avg_return']:>7.4f}")

    _banner("TOP-5 HIGH-PRIOR CURRENT RECS")
    for r in result["priors_high"][:5]:
        print(f"  {r['ticker']:<12} {r['recommendation']:<12} "
                f"wr={r['prior_win_rate']} exp={r['prior_expectancy']} "
                f"(n_hist={r['n_historical']})")

    _banner("STEP 2/2 · Publish")
    out_path = Path(__file__).resolve().parents[2] / "reports" / "recommendation_dna_feedback.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  written: reports/{out_path.name}")

    _banner(f"DEV028 v1.5 · DONE ({time.time() - t0:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
