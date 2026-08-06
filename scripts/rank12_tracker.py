"""CLI runner for the Rank 1+2 paper portfolio tracker.

Usage:
    # Daily cycle · build or refresh · save · append P&L history
    python scripts/rank12_tracker.py

    # Force rebuild (reset portfolio to today's rank 1-2 picks · resets P&L)
    python scripts/rank12_tracker.py --rebuild

    # Show current snapshot as markdown
    python scripts/rank12_tracker.py --show

    # Send current snapshot to Telegram
    python scripts/rank12_tracker.py --send-telegram
"""
from __future__ import annotations
import argparse, io, os, sys
from datetime import date as _date
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.portfolio import rank12_tracker as _r  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=_date.today().isoformat())
    ap.add_argument("--rebuild", action="store_true",
                       help="reset portfolio to today's rank 1-2 picks")
    ap.add_argument("--show", action="store_true", help="print markdown snapshot")
    ap.add_argument("--send-telegram", action="store_true")
    args = ap.parse_args()

    if args.rebuild:
        p = _r._cfg_path(_ROOT)
        if p.exists():
            p.unlink()
            print(f"[rank12] deleted existing portfolio · rebuilding fresh")

    portfolio = _r.daily_cycle(_ROOT, args.asof)
    if not portfolio.get("holdings"):
        print(f"[rank12] no holdings · {portfolio.get('reason', 'unknown')}")
        return 1

    print(f"[rank12] {len(portfolio['holdings'])} holdings · "
          f"total value ₹{portfolio.get('total_value', 0):,.2f} · "
          f"return {portfolio.get('total_return_pct', 0):+.2f}%")

    if args.show:
        print("\n" + _r.render_md(portfolio))

    if args.send_telegram:
        md_path = _ROOT / "reports" / "research" / "rank12_current.md"
        md_path.write_text(_r.render_md(portfolio), encoding="utf-8")
        try:
            from scripts.telegram_command_center_send import _send_document, _load_env
            _load_env()
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
            if not token or not chat_id:
                print("[telegram] tokens missing"); return 2
            caption = (f"📊 Rank 1+2 Portfolio · {portfolio.get('asof')} · "
                          f"return {portfolio.get('total_return_pct', 0):+.2f}% · "
                          f"₹{portfolio.get('total_value', 0):,.2f}")
            ok, msg = _send_document(token, chat_id, md_path, caption=caption)
            print(f"[telegram] sent={ok}")
        except Exception as e:
            print(f"[telegram] failed · {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
