"""Standalone intraday runner · ZERO coupling to daily pipeline.

Usage:
  python scripts/intraday_run.py --market india --step universe
  python scripts/intraday_run.py --market india --step fetch --limit 20
  python scripts/intraday_run.py --market india --step backtest
  python scripts/intraday_run.py --market india --step all

Runs all four steps in sequence when --step all:
  1. universe   · filter today's intraday-tradable universe
  2. fetch      · pull intraday bars for universe (Angel primary · yfinance fallback)
  3. backtest   · replay historical bars through signal → ensemble → sim stack
  4. platform   · emit reports/intraday/intraday_platform.json SSoT

Optionally sends a Telegram evidence message with --telegram.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.intraday.universe import filter_intraday_universe, load_intraday_universe   # noqa: E402
from backend.intraday.feed import get_intraday_bars                                       # noqa: E402
from backend.intraday.backtest import run_intraday_backtest                                # noqa: E402
from backend.intraday.platform import build_intraday_platform                              # noqa: E402
from backend.intraday.telegram import render_intraday_evidence                             # noqa: E402


def _load_telegram_env() -> tuple[str, str]:
    for name in (".env.telegram", ".env"):
        p = _ROOT / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for a in ("TOKEN", "BOT_TOKEN", "TELEGRAM_TOKEN"):
        if not os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get(a):
            os.environ["TELEGRAM_BOT_TOKEN"] = os.environ[a]
    for a in ("CHAT_ID", "CHAT", "TELEGRAM_CHAT"):
        if not os.environ.get("TELEGRAM_CHAT_ID") and os.environ.get(a):
            os.environ["TELEGRAM_CHAT_ID"] = os.environ[a]
    return os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")


def _send_telegram(text: str) -> bool:
    if not text:
        return True
    token, chat = _load_telegram_env()
    if not (token and chat):
        print("[intraday_run] no telegram tokens · skipping send")
        return False
    if len(text) > 4076:
        text = text[:4060] + "\n\n...truncated"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":                  chat,
        "text":                     text,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=30):
            return True
    except Exception as e:
        # Retry without markdown
        try:
            data2 = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode("utf-8")
            req2 = urllib.request.Request(url, data=data2, method="POST")
            with urllib.request.urlopen(req2, timeout=30):
                return True
        except Exception as e2:
            print(f"[intraday_run] telegram send failed: {e2}")
            return False


def step_universe(market: str) -> list[str]:
    payload = filter_intraday_universe(_ROOT, market)
    tickers = payload.get("tickers") or []
    print(f"[intraday_run:{market}] universe · {payload.get('n_passing', 0)} of "
          f"{payload.get('n_delivery', 0)} passing")
    return tickers


def step_fetch(market: str, tickers: list[str], interval: str = "5m",
                  limit: int = 20) -> dict:
    tickers = tickers[:limit]
    fetched = 0
    errors = 0
    for t in tickers:
        df = get_intraday_bars(_ROOT, t, market, interval=interval)
        if df is not None and len(df) > 0:
            fetched += 1
        else:
            errors += 1
    print(f"[intraday_run:{market}] fetch · {fetched}/{len(tickers)} fetched "
          f"({interval} · {errors} errors)")
    return {"fetched": fetched, "errors": errors, "attempted": len(tickers)}


def step_backtest(market: str, tickers: list[str], interval: str = "15m") -> dict:
    result = run_intraday_backtest(_ROOT, market, tickers, interval=interval)
    print(f"[intraday_run:{market}] backtest · sessions={result.n_sessions} "
          f"trades={result.n_trades} win_rate={result.win_rate*100:.0f}% "
          f"total_pnl={result.total_pnl:+.2f}%")
    return {"n_trades": result.n_trades, "win_rate": result.win_rate,
            "total_pnl": result.total_pnl}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa"], default="india")
    ap.add_argument("--step", choices=["universe", "fetch", "backtest", "platform", "all"],
                       default="all")
    ap.add_argument("--limit", type=int, default=20,
                       help="Cap number of tickers processed by fetch step")
    ap.add_argument("--interval", default="15m",
                       choices=["1m", "5m", "15m", "30m", "1h", "2h", "4h"])
    ap.add_argument("--telegram", action="store_true",
                       help="Send evidence panel to Telegram at the end")
    args = ap.parse_args()

    print(f"[intraday_run] market={args.market} step={args.step} "
          f"interval={args.interval}")

    tickers: list[str] = []
    if args.step in ("universe", "fetch", "backtest", "all"):
        tickers = step_universe(args.market)

    if args.step in ("fetch", "all"):
        if tickers:
            step_fetch(args.market, tickers, interval=args.interval, limit=args.limit)

    if args.step in ("backtest", "all"):
        if tickers:
            step_backtest(args.market, tickers[:args.limit], interval=args.interval)

    if args.step in ("platform", "all"):
        rp = build_intraday_platform(_ROOT, market=args.market)
        print(f"[intraday_run:{args.market}] platform · SSoT written to "
              f"reports/intraday/intraday_platform.json")

    if args.telegram:
        msg = render_intraday_evidence(_ROOT, market=args.market)
        ok = _send_telegram(msg)
        print(f"[intraday_run:{args.market}] telegram send: {ok}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
