"""Sprint D · Per-Ticker Timeline view.

Operator ask from CEO decision doc: replay every event that happened to
one ticker · OPEN → all events → current state · with prices and P&L.

Aggregates from existing ledgers (no new data · zero writes to R1/R2):
    · portfolio_ledger.jsonl   · OPEN/HOLD/ROTATE_*/EXIT_* events
    · rank_history.jsonl       · daily rank + confidence snapshots
    · position_store           · entry/high-water/low-water prices
    · recommendations_history/ · daily archived rec state

Usage:
    python scripts/ticker_timeline.py --ticker TCS
    python scripts/ticker_timeline.py --ticker AAPL --market usa
    python scripts/ticker_timeline.py --ticker LUPIN --send-telegram
    python scripts/ticker_timeline.py --ticker HCLTECH --format json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def _reports(market: str) -> Path:
    return _ROOT / ("usa/reports" if market == "usa" else "reports")


def _load_ledger_events(market: str, ticker: str) -> list[dict]:
    p = _ROOT / "reports" / "research" / "portfolio_ledger.jsonl"
    if not p.exists(): return []
    events = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try: d = json.loads(line)
        except json.JSONDecodeError: continue
        if d.get("market") != market: continue
        t = (d.get("ticker") or "").replace(".NS", "").replace(".BO", "")
        if t.upper() != ticker.upper(): continue
        events.append(d)
    events.sort(key=lambda e: (e.get("asof") or "", e.get("ts_utc") or ""))
    return events


def _load_rank_history(market: str, ticker: str) -> list[dict]:
    p = _ROOT / "reports" / "research" / "rank_history.jsonl"
    if not p.exists(): return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try: d = json.loads(line)
        except json.JSONDecodeError: continue
        if d.get("market") != market: continue
        t = (d.get("ticker") or "").replace(".NS", "").replace(".BO", "")
        if t.upper() != ticker.upper(): continue
        rows.append(d)
    rows.sort(key=lambda r: r.get("asof") or "")
    return rows


def _load_position(market: str, ticker: str) -> dict | None:
    p = _reports(market) / "position_store" / market / "positions.json"
    if not p.exists(): return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        for k, v in (d.get("positions") or {}).items():
            short = k.replace(".NS", "").replace(".BO", "")
            if short.upper() == ticker.upper() or k.upper() == ticker.upper():
                return {"raw_ticker": k, **v}
    except Exception:
        return None
    return None


def build_timeline(market: str, ticker: str) -> dict:
    events = _load_ledger_events(market, ticker)
    ranks = _load_rank_history(market, ticker)
    pos = _load_position(market, ticker)

    # Compute realised P&L if position exists
    entry = pos.get("first_seen_price") if pos else None
    last = pos.get("last_seen_price") if pos else None
    high = pos.get("high_water_price") if pos else None
    low = pos.get("low_water_price") if pos else None
    ret_pct = ((last - entry) / entry * 100.0) if entry and last else None
    max_gain = ((high - entry) / entry * 100.0) if entry and high else None
    max_dd = ((low - entry) / entry * 100.0) if entry and low else None

    return {
        "ticker":     ticker.upper(),
        "market":     market,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "position": {
            "opened_on":         pos.get("first_seen_date") if pos else None,
            "entry_price":       entry,
            "last_seen_price":   last,
            "high_water_price":  high,
            "low_water_price":   low,
            "current_return_pct": round(ret_pct, 2) if ret_pct is not None else None,
            "max_gain_pct":      round(max_gain, 2) if max_gain is not None else None,
            "max_drawdown_pct":  round(max_dd, 2) if max_dd is not None else None,
            "is_active":         pos.get("is_active") if pos else False,
        },
        "n_events":       len(events),
        "n_rank_days":    len(ranks),
        "events":         events,
        "rank_history":   ranks,
    }


def render_md(t: dict) -> str:
    p = t["position"] or {}
    lines = [f"# Timeline · {t['ticker']} · {t['market'].upper()}",
                "",
                "## Position",
                f"- Opened: **{p.get('opened_on') or '—'}**",
                f"- Entry: **{p.get('entry_price') or '—'}**",
                f"- Current: **{p.get('last_seen_price') or '—'}** · "
                f"**{p.get('current_return_pct') or '—'}%**",
                f"- Max gain: **{p.get('max_gain_pct') or '—'}%** · "
                f"Max DD: **{p.get('max_drawdown_pct') or '—'}%**",
                f"- Active: **{p.get('is_active')}**",
                "",
                f"## Events ({t['n_events']})",
                ""]
    for e in t["events"] or []:
        price = e.get("price")
        reason = e.get("reason") or ""
        lines.append(f"- **{e.get('asof')}** · {e.get('event')} · "
                          f"@ {price!s} · _{reason[:80]}_")
    if not t["events"]:
        lines.append("_(no portfolio ledger events for this ticker yet)_")
    lines += ["", f"## Rank history ({t['n_rank_days']} days)", ""]
    if t["rank_history"]:
        lines += ["| Date | Rank | Confidence | Status |",
                     "|---|---|---|---|"]
        for r in t["rank_history"][-20:]:
            c = r.get("confidence")
            c_pct = f"{c*100:.0f}%" if isinstance(c, (int, float)) and c <= 1 else str(c)
            lines.append(f"| {r.get('asof')} | {r.get('rank')} | {c_pct} | {r.get('status') or '—'} |")
    else:
        lines.append("_(no rank_history entries yet · needs daily runs to accumulate)_")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True, help="short ticker · e.g. TCS · AAPL")
    ap.add_argument("--market", choices=["india", "usa"], default="india")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--send-telegram", action="store_true",
                       help="attach the MD file to Telegram as a document")
    args = ap.parse_args()

    t = build_timeline(args.market, args.ticker)
    out_dir = _ROOT / "reports" / "research" / "timelines"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"timeline_{args.market}_{args.ticker.upper()}"
    if args.format == "md":
        md_path = out_dir / f"{stem}.md"
        md_path.write_text(render_md(t), encoding="utf-8")
        print(f"[timeline] wrote {md_path}")
        if args.send_telegram:
            try:
                from scripts.telegram_command_center_send import _send_document, _load_env
                _load_env()
                token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
                chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
                if token and chat_id:
                    ok, msg = _send_document(token, chat_id, md_path,
                                                     caption=f"📊 Timeline · {args.ticker.upper()}")
                    print(f"[telegram] sent={ok}")
                else:
                    print("[telegram] missing tokens · skip")
            except Exception as e:
                print(f"[telegram] failed · {type(e).__name__}: {e}")
    else:
        j_path = out_dir / f"{stem}.json"
        j_path.write_text(json.dumps(t, indent=2, default=str, ensure_ascii=False),
                                encoding="utf-8")
        print(f"[timeline] wrote {j_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
