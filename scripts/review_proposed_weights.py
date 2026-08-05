"""Sprint B · Review the current adaptive-weight proposal.

Shows a diff of current live weights vs proposed weights + justification
so operator can decide whether to approve.

Usage:
    # Show diff · never modifies anything
    python scripts/review_proposed_weights.py

    # Regenerate the proposal from latest monthly rollup
    python scripts/review_proposed_weights.py --regenerate --month 2026-07

    # Print in machine-readable JSON
    python scripts/review_proposed_weights.py --format json

    # OPERATOR-ONLY: approve + copy to live config (with backup)
    python scripts/review_proposed_weights.py --approve

CEO rule: no auto-application. This script is the ONLY path from
proposal → live weights and it requires explicit --approve.
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
from datetime import date as _date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

LIVE_PATH = _ROOT / "configs" / "adaptive_ensemble_weights.json"
PROPOSED_PATH = _ROOT / "configs" / "proposed_ensemble_weights.json"


def _regenerate(month: str, market: str) -> Path:
    from backend.research.adaptive_weights import propose as _p
    payload = _p.compute(_ROOT, market, month)
    return _p.emit(_ROOT, payload)


def _pretty_diff(proposal: dict) -> str:
    lines = [f"# Adaptive Weight Proposal · {proposal.get('market')} · "
                f"{proposal.get('month')}",
                "",
                f"Status: **{proposal.get('status')}** · "
                f"n_models: **{proposal.get('n_models', 0)}** · "
                f"auto_applied: **{proposal.get('auto_applied')}**",
                "",
                f"> {proposal.get('operator_action', '')}",
                "",
                "| Model | Current | Proposed | Δ | n | Justification |",
                "|---|---:|---:|---:|---:|---|"]
    for p in proposal.get("proposals") or []:
        d = p.get("delta") or 0
        arrow = " ↑" if d > 0 else (" ↓" if d < 0 else " →")
        insufficient = " ⚠️" if p.get("insufficient_data") else ""
        lines.append(f"| {p.get('label') or p['model_id']} | "
                          f"{p.get('current_weight'):.3f} | "
                          f"{p.get('proposed_weight'):.3f} | "
                          f"{d:+.3f}{arrow}{insufficient} | "
                          f"{p.get('n_samples', 0)} | "
                          f"{p.get('justification', '')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regenerate", action="store_true",
                       help="regenerate proposal from latest rollup before diffing")
    ap.add_argument("--month", default=_date.today().strftime("%Y-%m"))
    ap.add_argument("--market", default="india", choices=["india", "usa"])
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--approve", action="store_true",
                       help="OPERATOR-ONLY · copy proposal to live weights "
                            "(with backup at configs/backups/)")
    args = ap.parse_args()

    if args.regenerate:
        path = _regenerate(args.month, args.market)
        print(f"[review_proposed_weights] regenerated · {path}")

    if not PROPOSED_PATH.exists():
        print(f"[review_proposed_weights] no proposal at {PROPOSED_PATH}")
        print(f"  run with --regenerate to create one")
        return 1

    proposal = json.loads(PROPOSED_PATH.read_text(encoding="utf-8"))

    if args.approve:
        if not LIVE_PATH.exists():
            print(f"[review_proposed_weights] no live weights at {LIVE_PATH}")
            print(f"  cannot approve · would create weights from nothing")
            return 1
        # Backup + copy
        from datetime import datetime, timezone
        backup_dir = _ROOT / "configs" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        backup = backup_dir / f"adaptive_ensemble_weights_{stamp}.json"
        shutil.copy2(LIVE_PATH, backup)
        # Extract proposed_weight map + write it as live weights
        new_weights = {p["model_id"]: p["proposed_weight"]
                            for p in (proposal.get("proposals") or [])}
        LIVE_PATH.write_text(json.dumps({"weights": new_weights,
                                                     "approved_from": str(PROPOSED_PATH.relative_to(_ROOT)),
                                                     "approved_utc": datetime.now(timezone.utc).isoformat(),
                                                     "backup":       str(backup.relative_to(_ROOT))},
                                                    indent=2, ensure_ascii=False),
                                    encoding="utf-8")
        print(f"[review_proposed_weights] APPROVED · new weights written to {LIVE_PATH}")
        print(f"  backup: {backup.relative_to(_ROOT)}")
        return 0

    if args.format == "json":
        print(json.dumps(proposal, indent=2, ensure_ascii=False))
    else:
        print(_pretty_diff(proposal))
    return 0


if __name__ == "__main__":
    sys.exit(main())
