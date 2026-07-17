"""DEV030 · Champion vs Challenger Strategy Framework · CLI."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from champion_challenger.compute import engine                                          # noqa: E402
from champion_challenger.publish import bundle as publish                                # noqa: E402


def _banner(msg: str) -> None:
    print(); print("=" * 70); print(f"  {msg}"); print("=" * 70)


def _now_ist() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")


def main() -> int:
    t0 = time.time()
    _banner("DEV030 - CHAMPION vs CHALLENGER STRATEGY FRAMEWORK")
    print(f"  time (IST): {_now_ist()}")

    _banner("STEP 1/2 - Rank strategies, evaluate promotion")
    result = engine.run(verbose=True)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    _banner("STEP 2/2 - Publish 7 outputs")
    published = publish.build_and_publish(result)
    for name in ["champion_strategy.json", "challenger_scoreboard.json",
                   "head_to_head_matrix.json", "regime_comparison.json",
                   "drift_report.json", "promotion_recommendation.json",
                   "strategy_leaderboard.parquet"]:
        print(f"  written: reports/{name}")

    _banner("LEADERBOARD")
    print(f"\n  {'#':>3} {'strategy':<20} {'score':>8} {'sharpe':>8} "
             f"{'cagr':>8} {'max_dd':>8} {'win_rate':>10}")
    print(f"  {'-' * 72}")
    for row in result["leaderboard"]:
        marker = "*" if row["strategy"] == result["champion"]["strategy"] else " "
        sh = row.get("sharpe"); cagr = row.get("cagr")
        dd = row.get("max_dd_pct"); wr = row.get("win_rate")
        print(f"  {marker}{row['rank']:>2} {row['strategy']:<20} "
                f"{row['composite_score']:>8.2f} "
                f"{sh if sh is not None else 0:>8.3f} "
                f"{(cagr or 0)*1:>8.3f} "
                f"{(dd or 0):>8.2f} "
                f"{(wr or 0):>10.2f}")

    _banner("PROMOTION DECISION")
    p = result["promotion"]
    print(f"  decision: {p['decision']}")
    print(f"  reason:   {p.get('reason')}")
    if "gates" in p and p["gates"]:
        for name, g in p["gates"].items():
            tag = "PASS" if g.get("passed") else "FAIL"
            print(f"    [{tag}] {name}: {g}")

    _banner("REGIME REPORT")
    rr = result["regime_comparison"]
    print(f"  current regime: {rr.get('current_regime')}")
    print(f"  regime windows: {rr.get('regime_windows', {})}")
    print(f"  regime champions:")
    for regime_label, champ in (rr.get("regime_champions") or {}).items():
        print(f"    - {regime_label}: {champ['strategy']}  (cagr={champ['cagr']})")

    _banner("DRIFT SUMMARY")
    for strat, m in (result["metric_drift"] or {}).items():
        print(f"  {strat:<20} 1st_half_sh={m['first_half_sharpe']:>7.3f} "
                f" 2nd_half_sh={m['second_half_sharpe']:>7.3f}  flag={m['stability_flag']}")

    _banner("DEV030 - DONE")
    print(f"  elapsed: {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
