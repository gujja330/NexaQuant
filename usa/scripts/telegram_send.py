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


def send_message(token: str, chat_id: str, text: str) -> tuple[bool, str]:
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
    load_env()
    token   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[usa telegram] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — skipping (optional).")
        return 0

    print("=" * 70)
    print("  AEGIS USA · Telegram send · USD · S&P 500 benchmark")
    print("=" * 70)

    messages = renderer.render_all()
    ok = 0; total_chars = 0
    ledger = []
    for label, text in messages:
        t0 = time.time()
        success, resp = send_message(token, chat_id, text)
        elapsed = time.time() - t0
        chars = len(text)
        if success:
            print(f"  [{label}] sent ({chars} chars, {elapsed:.2f}s)")
            ok += 1; total_chars += chars
        else:
            print(f"  [{label}] cannot send: {resp[:120]}")
        ledger.append({
            "label":     label,
            "chars":     chars,
            "ok":        success,
            "elapsed_s": round(elapsed, 3),
            "response":  resp[:200] if not success else "OK",
        })
        time.sleep(0.3)   # gentle rate-limit

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ledger_path = _USA / "reports" / f"telegram_delivery_{date}.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "run_utc":       datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
            "market":        "USA",
            "n_messages":    len(messages),
            "n_sent":        ok,
            "total_chars":   total_chars,
            "entries":       ledger,
        }, default=str) + "\n")

    if ok == len(messages):
        print(f"\n  sent ({total_chars} chars across {ok} messages)")
        return 0
    print(f"\n  cannot send: {len(messages) - ok} of {len(messages)} messages failed")
    return 1 if ok == 0 else 0    # partial delivery still exit 0


if __name__ == "__main__":
    sys.exit(main())
