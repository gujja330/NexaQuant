"""Recommendation DNA v2.0 · Winner Genome CLI.

Mines historical trades for the Alpha Signatures that discriminate
top-decile winners from the rest. Emits `reports/winner_genome.json`.
"""
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

from recommendation_dna.lib import winner_genome                                        # noqa: E402


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  RECOMMENDATION DNA v2.0 · WINNER GENOME")
    print("=" * 70)

    result = winner_genome.run_winner_genome()
    result["run_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"

    if result["mode"] == "insufficient_data":
        print(f"\n  mode: insufficient_data · {result['note']}")
    else:
        print(f"\n  trades loaded:          {result['n_trades']}")
        print(f"  top-decile winners:     {result['n_top_decile']}")
        print(f"  top-decile threshold:   {result['top_decile_threshold'] * 100:+.2f}% return")
        print(f"  signatures mined:       {result['n_signatures']}")
        print(f"  current recs matched:   {result['n_current_matched']} / {len(result['matches'])}")
        print()
        # Print top-5 signatures for the operator
        print("  Top signatures (by lift):")
        for sig in result["signatures"][:5]:
            feats = " · ".join(f'{f["feature"]}={f["bucket"]}' for f in sig["features"])
            avg_ret = sig.get("avg_return")
            avg_ret_str = f'{avg_ret * 100:+.1f}%' if avg_ret is not None else '—'
            print(f"    #{sig['signature_id']:>2}  lift={sig['lift']:.2f}  n={sig['n']:>3}  "
                  f"win_rate={sig['winner_rate'] * 100:>4.1f}%  avg_ret={avg_ret_str}  "
                  f"→ {feats}")

    p = HERE.parents[1] / "reports" / "winner_genome.json"
    p.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    size_kb = p.stat().st_size / 1024
    print(f"\n  written: reports/winner_genome.json ({size_kb:.1f} KB)")
    print(f"  elapsed: {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
