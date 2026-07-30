"""Non-destructive canonical + display-field stamper for recommendations.json.

Post-mortem 2026-07-30: full ssot pipeline reruns destroyed the morning
good state (LUPIN/HEROMOTOCO/CHAMBLFERT → HOLD, rotations → 0). This
script exists so display-layer refreshes (canonical stamp, Research
Platform pointer updates, Telegram-visible field tweaks) NEVER touch the
engine, enricher, snapshot archiver, or v3 producer.

Usage:
    python scripts/stamp_only.py --market india
    python scripts/stamp_only.py --market usa
    python scripts/stamp_only.py --market both

What it does (in order · all non-destructive):
    1. Read reports/recommendations.json (or usa/reports/…)
    2. Read reports/research/delivery_platform.json (canonical source)
    3. Apply _stamp_canonical() to the payload in-place
    4. Write back to the same file (formatting preserved)

What it does NOT do:
    · Never touches recommendations_v3.json
    · Never calls enrich_batch, build_ceo_summary, run_scorecard, etc.
    · Never writes to reports/recommendations_history/ (snapshot archive)
    · Never invokes the position store or lifecycle ledger
    · Never runs the research platform builder
    · Zero risk of overwriting picks or rotations
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.ssot.run import _stamp_canonical   # noqa: E402


def _reports_dir(market: str) -> Path:
    if market == "usa":
        return _ROOT / "usa" / "reports"
    return _ROOT / "reports"


def stamp_one(market: str) -> tuple[bool, dict]:
    reports = _reports_dir(market)
    p = reports / "recommendations.json"
    if not p.exists():
        print(f"[stamp_only:{market}] SKIP · {p.relative_to(_ROOT)} missing")
        return False, {"market": market, "error": "missing_recommendations"}
    try:
        pub = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        print(f"[stamp_only:{market}] READ FAILED · {type(e).__name__}: {e}")
        return False, {"market": market, "error": str(e)}

    n_recs = len(pub.get("recommendations") or [])
    buys_before = sum(1 for r in pub.get("recommendations") or []
                          if (r.get("investor_action") or {}).get("entry") == "BUY")

    _stamp_canonical(pub, market, _ROOT)

    # Sanity: buys count must be unchanged (we never touched investor_action)
    buys_after = sum(1 for r in pub.get("recommendations") or []
                         if (r.get("investor_action") or {}).get("entry") == "BUY")
    if buys_before != buys_after:
        print(f"[stamp_only:{market}] ABORTED · buys count changed "
                f"({buys_before} → {buys_after}). Stamp helper bug. No file write.")
        return False, {"market": market, "error": "buys_mutation_detected"}

    # Record the stamp event (audit trail · never breaks pipeline)
    pub["stamp_only_last_run_utc"] = datetime.now(timezone.utc).isoformat()

    p.write_text(json.dumps(pub, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")

    ceo = pub.get("ceo_summary") or {}
    print(f"[stamp_only:{market}] OK · n_recs={n_recs} buys={buys_after} "
             f"canonical={ceo.get('canonical_status')} "
             f"proposed_by={ceo.get('proposed_by')}")
    return True, {"market": market, "n_recs": n_recs, "buys": buys_after,
                    "canonical": ceo.get("canonical_status")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    markets = ["india", "usa"] if args.market == "both" else [args.market]
    all_ok = True
    for m in markets:
        ok, _ = stamp_one(m)
        all_ok = all_ok and ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
