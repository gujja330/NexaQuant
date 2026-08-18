"""AEGIS USA · Telegram sender.

Delivers the 5-message USA daily brief. Same TELEGRAM_BOT_TOKEN /
TELEGRAM_CHAT_ID env vars as India (single bot serves both markets).
Distinct message content — USD, Dow, S&P 500 references.

Reads .env.telegram from repo root if env vars aren't set.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[2]
_USA  = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_USA.parent))

from usa.telegram.lib import renderer                                                    # noqa: E402


def load_env() -> None:
    for name in (".env.telegram", ".env"):
        p = _ROOT / name
        if not p.exists(): continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            k = k.strip(); v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)


def _consolidate(header: str, sections: list[tuple[str, str]], budget: int = 3900) -> str:
    """Merge N section bodies into ONE Telegram-safe message. Priority-ordered:
    earlier sections keep full text; later ones truncate/drop if we run out of budget."""
    parts: list[str] = [f"*{header}*"]
    remaining = budget - len(parts[0])
    dropped: list[str] = []
    for name, body in sections:
        if not body: continue
        body = body.strip()
        divider = f"\n\n━━━━━━━━━━\n*{name}*\n"
        need = len(divider) + len(body)
        if need <= remaining:
            parts.append(divider + body)
            remaining -= need
            continue
        if remaining > 200:
            keep = remaining - len(divider) - 40
            if keep > 0:
                parts.append(divider + body[:keep].rstrip() + "\n_...truncated_")
                remaining = 0
                dropped.append(name + " (partial)")
                continue
        dropped.append(name)
    if dropped:
        parts.append(f"\n\n_(omitted for length: {', '.join(dropped)})_")
    return "".join(parts)


def send_message(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    # Telegram hard cap is 4096 chars; keep a safety margin.
    if len(text) > 4000:
        text = text[:3900] + "\n\n_...truncated for delivery_"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":                  chat_id,
        "text":                     text,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        with urllib.request.urlopen(url, data=data, timeout=15) as r:
            body = r.read().decode("utf-8")
            j = json.loads(body)
            return (j.get("ok", False), body[:200])
    except urllib.error.HTTPError as e:
        return (False, f"HTTPError {e.code} · {e.read().decode('utf-8', errors='replace')[:200]}")
    except Exception as e:
        return (False, f"{type(e).__name__}: {e}")


def main() -> int:
    # 2026-08-18 · DISABLED per operator hard rule:
    #   "dont send me history. send me india and usa aegis seperately
    #    nothing else on telegram . make a note"
    # This script previously delivered a 5-section text daily brief
    # (Executive Summary + Top Opportunities + Portfolio Health +
    # Benchmark + Morning Brief). That is exactly the "nothing else"
    # the operator forbids. Per-market XLSX delivery lives in
    # scripts/telegram_command_center_send.py · this sender is
    # neutered · exits 0 · no message sent.
    #
    # See memory: feedback_telegram_delivery_policy
    print("=" * 70)
    print("  AEGIS USA · text brief · DISABLED (per operator policy 2026-08-18)")
    print("  Per-market XLSX delivery handled by telegram_command_center_send.py")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
