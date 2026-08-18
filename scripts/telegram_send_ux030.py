"""UX030-based Telegram sender (opt-in).

Standalone alternative to `scripts/telegram_send_with_retry.py`'s
default `india/telegram_notify.py` path. Uses the UX030 renderer
(`ux/telegram/lib/renderer.py`) to build the message set from the
live `reports/*.json` context.

Emits the same success/failure markers the retry wrapper looks for
(`sent (N chars)` / `cannot send`) so it can be wrapped identically:

    python scripts/telegram_send_with_retry.py --sender ux030
      (would be trivial to add; not shipped yet to avoid
      modifying the sealed retry wrapper).

For now: invoke this script directly with the operator's opt-in.
Environment variables required:

    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import io
import json
import os
import re
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

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ux.telegram.lib import renderer, commands                                          # noqa: E402
from ux.telegram.lib.aggregator import load_context                                     # noqa: E402


# ─── Env loading ────────────────────────────────────────────────
def load_env() -> None:
    """Read `.env.telegram` and `.env` if present. Match the aliases the
    existing telegram_notify.py accepts."""
    for name in (".env.telegram", ".env"):
        p = _ROOT / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v

    # aliases -> canonical
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        for a in ("TOKEN", "BOT_TOKEN", "TELEGRAM_TOKEN"):
            if os.environ.get(a):
                os.environ["TELEGRAM_BOT_TOKEN"] = os.environ[a]; break
    if not os.environ.get("TELEGRAM_CHAT_ID"):
        for a in ("CHAT_ID", "CHAT", "TELEGRAM_CHAT"):
            if os.environ.get(a):
                os.environ["TELEGRAM_CHAT_ID"] = os.environ[a]; break

    # strip any human decoration around the token
    m = re.search(r"\d{6,}:[A-Za-z0-9_-]{20,}", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    if m:
        os.environ["TELEGRAM_BOT_TOKEN"] = m.group(0)


def send_markdown(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    """Post text to Telegram sendMessage. Returns (ok, detail)."""
    if not text:
        return True, "empty"
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Telegram limit: 4096 chars per message. Truncate softly at
    # section boundaries where possible.
    if len(text) > 4000:
        text = text[:3900] + "\n\n_...truncated for delivery_"

    data = urllib.parse.urlencode({
        "chat_id":     chat_id,
        "text":        text,
        "parse_mode":  "Markdown",
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = r.read().decode("utf-8", errors="replace")
        result = json.loads(payload)
        return bool(result.get("ok")), payload
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return False, f"HTTPError {e.code} · {body[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _consolidate(header: str, sections: list[tuple[str, str]], budget: int = 3900) -> str:
    """Merge N section bodies into ONE Telegram-safe message.

    Priority: sections are consumed in order; earlier ones get their full text,
    later ones get truncated / dropped if we run out of budget. A visible
    _..truncated_ tail is appended if anything was cut.
    """
    parts: list[str] = [f"*{header}*"]
    remaining = budget - len(parts[0])
    dropped: list[str] = []
    for name, body in sections:
        if not body:
            continue
        body = body.strip()
        # each section gets a divider + bold name + blank line
        divider = f"\n\n━━━━━━━━━━\n*{name}*\n"
        need = len(divider) + len(body)
        if need <= remaining:
            parts.append(divider + body)
            remaining -= need
            continue
        # partial fit: fit what we can, tail-truncate
        if remaining > 200:
            keep = remaining - len(divider) - 40    # room for the "..." marker
            if keep > 0:
                parts.append(divider + body[:keep].rstrip() + "\n_...truncated_")
                remaining = 0
                dropped.append(name + " (partial)")
                continue
        dropped.append(name)
    if dropped:
        parts.append(f"\n\n_(omitted for length: {', '.join(dropped)})_")
    return "".join(parts)


def _log_delivery(record: dict) -> None:
    reports = _ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = reports / f"telegram_delivery_ux030_{stamp}.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def main() -> int:
    # 2026-08-18 · DISABLED per operator hard rule:
    #   "dont send me history. send me india and usa aegis seperately
    #    nothing else on telegram . make a note"
    # This UX030 sender previously delivered a 5-section text brief for
    # India (Executive Summary + New Buys + Portfolio Health + Champion
    # Update + Morning Brief). That is exactly the "nothing else"
    # forbidden. Per-market XLSX delivery lives in
    # scripts/telegram_command_center_send.py · this sender is neutered
    # · exits 0 · no message sent.
    #
    # See memory: feedback_telegram_delivery_policy
    print("  AEGIS India · text brief · DISABLED (per operator policy 2026-08-18)")
    print("  Per-market XLSX delivery handled by telegram_command_center_send.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
