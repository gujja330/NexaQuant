"""Command Center Telegram sender · both markets · single message each.

Consumes the enriched recommendations.json produced by
backend.recommendation.ssot.run + backend.certification.institutional_optimization_run
(cycle 3-4). Sends ONE message per market · replaces the legacy multi-
message duplicate-message flow.

Usage:
    python scripts/telegram_command_center_send.py --market india
    python scripts/telegram_command_center_send.py --market usa
    python scripts/telegram_command_center_send.py --market both

Env:
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID   (single chat serves both markets · UX030 pattern)

Exit codes:
    0 = all requested markets delivered successfully
    1 = at least one market failed
    2 = missing tokens (skipped without failing CI)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
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

from backend.delivery.telegram.command_center import (  # noqa: E402
    load_and_render, render_research_platform_message,
    ENGINE_ID, SCHEMA_FINGERPRINT,
)


def _load_env() -> None:
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
            os.environ.setdefault(k, v)
    # Aliases (mirror UX030 sender)
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        for a in ("TOKEN", "BOT_TOKEN", "TELEGRAM_TOKEN"):
            if os.environ.get(a):
                os.environ["TELEGRAM_BOT_TOKEN"] = os.environ[a]; break
    if not os.environ.get("TELEGRAM_CHAT_ID"):
        for a in ("CHAT_ID", "CHAT", "TELEGRAM_CHAT"):
            if os.environ.get(a):
                os.environ["TELEGRAM_CHAT_ID"] = os.environ[a]; break
    m = re.search(r"\d{6,}:[A-Za-z0-9_-]{20,}", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    if m:
        os.environ["TELEGRAM_BOT_TOKEN"] = m.group(0)


def _send_markdown(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    if not text:
        return True, "empty"
    # Telegram hard cap 4096 · trim only if actually over
    if len(text) > 4096:
        text = text[:4080] + "\n\n...truncated"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":                  chat_id,
        "text":                     text,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="replace")
        return True, body[:120]
    except urllib.error.HTTPError as e:
        # Retry without Markdown parse if the parser trips (defense against
        # any accidental `_` / `*` in tickers or narrative).
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = str(e)
        if e.code == 400 and "parse" in err_body.lower():
            plain = urllib.parse.urlencode({
                "chat_id":                  chat_id,
                "text":                     text,
                "disable_web_page_preview": "true",
            }).encode("utf-8")
            try:
                req2 = urllib.request.Request(url, data=plain, method="POST")
                with urllib.request.urlopen(req2, timeout=30) as r:
                    body = r.read().decode("utf-8", errors="replace")
                return True, "markdown-failed-plain-delivered: " + body[:100]
            except Exception as e2:
                return False, f"plain-fallback failed: {e2}"
        return False, f"HTTP {e.code}: {err_body[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _market_reports(market: str) -> Path:
    return _ROOT / ("usa/reports" if market == "usa" else "reports")


def _append_delivery_ledger(record: dict) -> None:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = _ROOT / "reports" / f"telegram_command_center_{date}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _send_one_market(market: str, token: str, chat_id: str) -> tuple[bool, dict]:
    reports_dir = _market_reports(market)
    msg, meta = load_and_render(reports_dir, market)
    if meta.get("n_recs") == 0:
        print(f"[command_center:{market}] no recs · skipping")
        return True, {"market": market, "skipped": True, **meta}
    ok, detail = _send_markdown(token, chat_id, msg)
    print(f"[command_center:{market}] chars={meta['message_chars']} "
          f"recs={meta['n_recs']} rotations={meta['n_rotations']} "
          f"actionable={meta['n_actionable']} · sent={ok}")
    if not ok:
        print(f"  detail: {detail[:180]}")
    _append_delivery_ledger({
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "engine": ENGINE_ID,
        "schema_fingerprint": SCHEMA_FINGERPRINT,
        "market": market,
        "ok": ok,
        "detail_head": detail[:200],
        **meta,
    })

    # v3.1: Research Platform follow-up (own budget · full evidence panel)
    # Sent as a SEPARATE Telegram so it never competes with the daily
    # advisory for space. Delivery failure here does NOT fail the main send.
    research_ok = True
    try:
        research_msg = render_research_platform_message(market, budget=4000)
        if research_msg:
            research_ok, research_detail = _send_markdown(token, chat_id, research_msg)
            print(f"[research_platform:{market}] chars={len(research_msg)} · sent={research_ok}")
            if not research_ok:
                print(f"  detail: {research_detail[:180]}")
            _append_delivery_ledger({
                "ts_utc":  datetime.now(timezone.utc).isoformat(),
                "engine":  "aegis.research.telegram.v1",
                "market":  market,
                "kind":    "research_platform",
                "ok":      research_ok,
                "chars":   len(research_msg),
                "detail_head":  research_detail[:200] if not research_ok else "",
            })
    except Exception as e:
        print(f"[research_platform:{market}] render/send failed · {type(e).__name__}: {e}")
        research_ok = False

    return (ok and research_ok), {"market": market, "ok": ok,
                                        "research_ok": research_ok, **meta}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--dry-run", action="store_true",
                       help="Render + print message but do not send")
    args = ap.parse_args()

    _load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    markets = ["india", "usa"] if args.market == "both" else [args.market]

    if args.dry_run:
        for m in markets:
            msg, meta = load_and_render(_market_reports(m), m)
            print(f"===== DRY RUN · {m} · {meta['message_chars']} chars =====")
            print(msg)
            print()
        return 0

    if not token or not chat_id:
        print(f"[command_center] MISSING TELEGRAM tokens · skipping "
              f"(sender remains optional in CI). Requested markets: {markets}")
        return 2   # non-fatal · matches optional-step convention

    all_ok = True
    for m in markets:
        ok, _ = _send_one_market(m, token, chat_id)
        all_ok = all_ok and ok

    # Terminal marker for retry-wrapper compatibility (in case we ever
    # wrap this too): "sent (N messages)."
    print(f"sent ({len(markets)} messages).")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
