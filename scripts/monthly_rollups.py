"""AEGIS · run the 3 monthly rollup reports for a given month.

Usage:
    # Default: current month · both markets · JSON + Markdown outputs
    python scripts/monthly_rollups.py

    # Specific month
    python scripts/monthly_rollups.py --month 2026-07

    # Single market
    python scripts/monthly_rollups.py --market india
    python scripts/monthly_rollups.py --market usa

    # Send Markdown files to Telegram (optional)
    python scripts/monthly_rollups.py --send-telegram

Outputs in reports/research/monthly/:
    confidence_calibration_{market}_{YYYY-MM}.json + .md
    rotation_accuracy_{market}_{YYYY-MM}.json + .md
    feature_attribution_{market}_{YYYY-MM}.json + .md

Every report degrades gracefully on sparse data (emits insufficient_data: true).
Safe to run daily · idempotent per (report, market, month).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date as _date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.research.monthly_rollups import (  # noqa: E402
    confidence_calibration, rotation_accuracy, feature_attribution,
    sector_performance, regime_performance, model_winrate,
)

REPORTS = [
    ("confidence_calibration", confidence_calibration),
    ("rotation_accuracy",      rotation_accuracy),
    ("feature_attribution",    feature_attribution),
    # Sprint E · 3 new slices (2026-08-05)
    ("sector_performance",     sector_performance),
    ("regime_performance",     regime_performance),
    ("model_winrate",          model_winrate),
]


def _out_dir() -> Path:
    p = _ROOT / "reports" / "research" / "monthly"
    p.mkdir(parents=True, exist_ok=True)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=_date.today().strftime("%Y-%m"),
                       help="YYYY-MM (default: current month)")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--send-telegram", action="store_true",
                       help="Attach .md files as Telegram documents")
    args = ap.parse_args()

    markets = ["india", "usa"] if args.market == "both" else [args.market]
    out_dir = _out_dir()

    summary = {"month": args.month, "reports": []}
    md_paths: list[Path] = []
    for m in markets:
        for name, mod in REPORTS:
            try:
                rep = mod.compute(_ROOT, m, args.month)
            except Exception as e:
                print(f"[{name}:{m}] failed · {type(e).__name__}: {e}")
                summary["reports"].append({
                    "report": name, "market": m, "status": "failed",
                    "error": f"{type(e).__name__}: {e}"})
                continue
            j_path = out_dir / f"{name}_{m}_{args.month}.json"
            m_path = out_dir / f"{name}_{m}_{args.month}.md"
            j_path.write_text(json.dumps(rep, indent=2, default=str, ensure_ascii=False),
                                    encoding="utf-8")
            m_path.write_text(mod.render_md(rep), encoding="utf-8")
            md_paths.append(m_path)
            n = rep.get("n_positions") or rep.get("n_rotations") or rep.get("total_samples") or 0
            flag = " ⚠️ insufficient" if rep.get("insufficient_data") else " ok"
            print(f"[{name}:{m}] n={n}{flag} · wrote {j_path.name}")
            summary["reports"].append({
                "report": name, "market": m, "n": n,
                "insufficient_data": bool(rep.get("insufficient_data")),
                "json": str(j_path.relative_to(_ROOT)),
                "md":   str(m_path.relative_to(_ROOT)),
            })

    summary_path = out_dir / f"summary_{args.month}.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                encoding="utf-8")
    print(f"[summary] {summary_path}")

    if args.send_telegram:
        try:
            from scripts.telegram_command_center_send import _send_document, _load_env
            import os
            _load_env()
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
            if not token or not chat_id:
                print("[telegram] tokens missing · skipping send")
            else:
                for mp in md_paths:
                    ok, msg = _send_document(token, chat_id, mp,
                                                     caption=f"📊 Monthly rollup · {mp.stem}")
                    print(f"[telegram] {mp.name} · sent={ok}")
        except Exception as e:
            print(f"[telegram] send failed · {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
