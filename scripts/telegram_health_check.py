"""Telegram health check — validates bot connectivity + chat access WITHOUT
sending a user-visible message.

Runs BEFORE the daily notification step in aegis-daily.yml so a stale/rotated
token or missing chat_id fails the workflow immediately (RED status, GitHub
Actions email to the operator) instead of silently no-op'ing.

Exit codes:
  0  bot token valid AND chat_id reachable
  1  TELEGRAM_BOT_TOKEN missing
  2  TELEGRAM_CHAT_ID missing
  3  getMe HTTP or API failure (token bad)
  4  getChat HTTP or API failure (chat_id bad or bot removed from chat)

Does NOT modify india/telegram_notify.py. Does NOT send any message.

Read-only against Telegram's Bot API.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


TIMEOUT_S: float = 15.0
ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _api_get(url: str) -> dict:
    """GET a Telegram API endpoint and return the decoded JSON dict."""
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read())


def _write_health_report(record: dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    date = _iso_utc()[:10]
    path = REPORTS / f"telegram_health_{date}.json"
    prev = []
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(prev, list):
                prev = [prev]
        except json.JSONDecodeError:
            prev = []
    prev.append(record)
    path.write_text(json.dumps(prev, indent=2, ensure_ascii=False, default=str),
                     encoding="utf-8")
    return path


def _load_env_from_local_file() -> None:
    """Best-effort local .env.telegram loader for `--check` runs on the operator
    laptop. In CI the values come from the GitHub Actions env directly."""
    for name in (".env.telegram", ".env"):
        p = ROOT / name
        if not p.exists():
            continue
        for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    _load_env_from_local_file()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")

    result: dict = {
        "run_ts_utc": _iso_utc(),
        "checks": [],
    }

    print("=" * 60)
    print(f"  Telegram health check @ {result['run_ts_utc']}")
    print("=" * 60)

    if not token:
        print("  FAIL: TELEGRAM_BOT_TOKEN is not set in the environment.")
        result["checks"].append({"name": "TELEGRAM_BOT_TOKEN_present",
                                  "ok": False, "detail": "env var missing"})
        result["overall"] = "FAIL"
        _write_health_report(result)
        return 1
    result["checks"].append({"name": "TELEGRAM_BOT_TOKEN_present", "ok": True,
                              "detail": f"len={len(token)}"})

    if not chat:
        print("  FAIL: TELEGRAM_CHAT_ID is not set in the environment.")
        result["checks"].append({"name": "TELEGRAM_CHAT_ID_present",
                                  "ok": False, "detail": "env var missing"})
        result["overall"] = "FAIL"
        _write_health_report(result)
        return 2
    result["checks"].append({"name": "TELEGRAM_CHAT_ID_present", "ok": True,
                              "detail": f"value={chat!r}"})

    # 1. getMe: validate the bot token
    try:
        me = _api_get(f"https://api.telegram.org/bot{token}/getMe")
    except Exception as e:
        print(f"  FAIL: getMe network/HTTP error: {type(e).__name__}: {e}")
        result["checks"].append({"name": "getMe", "ok": False,
                                  "detail": f"{type(e).__name__}: {e}"})
        result["overall"] = "FAIL"
        _write_health_report(result)
        return 3
    if not me.get("ok"):
        print(f"  FAIL: getMe returned not-ok: {me}")
        result["checks"].append({"name": "getMe", "ok": False,
                                  "detail": json.dumps(me)})
        result["overall"] = "FAIL"
        _write_health_report(result)
        return 3
    bot_info = me.get("result", {})
    bot_username = bot_info.get("username", "<unknown>")
    bot_id = bot_info.get("id")
    print(f"  OK  : bot token valid — @{bot_username} (id={bot_id})")
    result["checks"].append({"name": "getMe", "ok": True,
                              "detail": f"@{bot_username} id={bot_id}"})

    # 2. getChat: validate the chat_id
    try:
        params = urllib.parse.urlencode({"chat_id": chat})
        chatinfo = _api_get(
            f"https://api.telegram.org/bot{token}/getChat?{params}")
    except urllib.error.HTTPError as e:
        # 400 Bad Request / 403 Forbidden are common when chat_id is wrong or
        # the bot was removed from the chat.
        detail = f"HTTP {e.code} {e.reason}"
        try:
            body = e.read().decode("utf-8", errors="ignore")
            j = json.loads(body)
            detail = f"HTTP {e.code}: {j.get('description', body[:200])}"
        except Exception:
            pass
        print(f"  FAIL: getChat error: {detail}")
        result["checks"].append({"name": "getChat", "ok": False, "detail": detail})
        result["overall"] = "FAIL"
        _write_health_report(result)
        return 4
    except Exception as e:
        print(f"  FAIL: getChat error: {type(e).__name__}: {e}")
        result["checks"].append({"name": "getChat", "ok": False,
                                  "detail": f"{type(e).__name__}: {e}"})
        result["overall"] = "FAIL"
        _write_health_report(result)
        return 4
    if not chatinfo.get("ok"):
        print(f"  FAIL: getChat returned not-ok: {chatinfo}")
        result["checks"].append({"name": "getChat", "ok": False,
                                  "detail": json.dumps(chatinfo)})
        result["overall"] = "FAIL"
        _write_health_report(result)
        return 4

    ch = chatinfo.get("result", {})
    label = (ch.get("title") or ch.get("username") or ch.get("first_name")
              or "<unnamed>")
    kind = ch.get("type", "?")
    print(f"  OK  : chat reachable — {kind} '{label}' (id={ch.get('id')})")
    result["checks"].append({"name": "getChat", "ok": True,
                              "detail": f"{kind} '{label}' id={ch.get('id')}"})

    result["overall"] = "OK"
    path = _write_health_report(result)
    print(f"  report written to {path.relative_to(ROOT)}")
    print("  All Telegram health checks PASS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
