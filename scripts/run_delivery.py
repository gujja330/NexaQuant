#!/usr/bin/env python3
"""AEGIS Layer 4 · Delivery · POST XLSX to Telegram (or BLOCK alert).

Reads the just-built XLSX + delivery-gate verdict from Layer 3.
- gate ALLOW → POST XLSX
- gate BLOCK → POST plain-text alert with reasons
Fast · pure HTTP.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                                    encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def _load_env_telegram() -> tuple:
    p = _ROOT / ".env.telegram"
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return (os.environ.get("TELEGRAM_BOT_TOKEN", ""),
                os.environ.get("TELEGRAM_CHAT_ID", ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=date.today().isoformat())
    args = ap.parse_args()

    token, chat_id = _load_env_telegram()
    if not token or not chat_id:
        print(f"[delivery:{args.market}] missing Telegram tokens · skipping")
        return 2   # non-fatal

    # Read delivery-gate verdict from Layer 3
    from backend.delivery.delivery_gate import decide, blocked_summary
    gd = decide(_ROOT, args.market)
    print(f"[delivery:{args.market}] gate verdict = {gd.verdict}")

    from scripts.telegram_command_center_send import (
        _send_document, _send_markdown,
    )
    xlsx = _ROOT / "reports" / "telegram" / f"aegis_history_{args.market}.xlsx"

    if gd.verdict == "BLOCK":
        alert = blocked_summary(gd)
        ok, msg = _send_markdown(token, chat_id, alert)
        print(f"[delivery:{args.market}] alert sent={ok}")
        return 0 if ok else 1

    # ALLOW · post XLSX
    if not xlsx.exists():
        print(f"[delivery:{args.market}] no XLSX at {xlsx}")
        return 1
    caption = f"📊 AEGIS {args.market.upper()} · {args.asof}"
    ok, msg = _send_document(token, chat_id, xlsx, caption=caption)
    print(f"[delivery:{args.market}] xlsx sent={ok} · {xlsx.name}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
