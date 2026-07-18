"""Adaptive Rec Engine v2.1 · Intelligence Fusion CLI."""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from adaptive_rec_v2.compute import fusion_engine                                       # noqa: E402
from adaptive_rec_v2.publish import fusion_bundle                                        # noqa: E402


def _banner(msg: str) -> None:
    print(); print("=" * 72); print(f"  {msg}"); print("=" * 72)


def main() -> int:
    t0 = time.time()
    _banner("ADAPTIVE REC ENGINE · v2.1 · INTELLIGENCE FUSION")

    _banner("STEP 1/2 · Score 10 dimensions per rec + fuse + detect conflicts")
    result = fusion_engine.run(verbose=True)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    _banner("STEP 2/2 · Publish 5 outputs")
    outcome = fusion_bundle.build_and_publish(result)
    for name in outcome["written"]:
        print(f"  written: reports/{name}")

    _banner("TOP-10 BY INTELLIGENCE SCORE")
    for r in result["summary"]["top_10"]:
        raw = r["raw_recommendation"] or "?"
        fus = r["fusion_decision"] or "?"
        marker = "!" if raw != fus and fus is not None else " "
        print(f"  {marker} {r['ticker']:<12} score={r['intelligence_score']:>5.1f} "
                f"raw={raw:<14} fusion={fus:<14} conflict={r['conflict_severity']}")

    _banner("DECISION DISTRIBUTION")
    for k, v in sorted(result["summary"]["by_decision"].items(),
                          key=lambda kv: -kv[1]):
        print(f"  {k:<20} {v}")

    _banner("CONFLICT REGISTER SUMMARY")
    cs = result["conflict_summary"]
    print(f"  total conflicts:            {cs['n_conflicts_total']}")
    print(f"  CRITICAL:                   {cs['n_critical']}")
    print(f"  MEDIUM:                     {cs['n_medium']}")
    print(f"  MINOR:                      {cs['n_minor']}")
    print(f"  tickers with CRITICAL:      {cs['n_tickers_with_critical']}")
    print()
    print(f"  Top firing rules:")
    for rule, n in list(cs["by_rule"].items())[:8]:
        print(f"    {rule:<40} {n}")

    _banner("SAMPLE CRITICALS")
    for c in cs["top_criticals"][:5]:
        print(f"  [{c['severity']}] {c.get('ticker'):<12} "
                f"{c['rule']:<32} {c['detail'][:100]}")

    _banner(f"ADAPTIVE REC v2.1 · DONE ({time.time() - t0:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
