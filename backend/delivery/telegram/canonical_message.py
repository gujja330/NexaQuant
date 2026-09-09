"""CANONICAL DAILY MESSAGE · one truth for Telegram and the workbook.

WHY THIS EXISTS
---------------
On 2026-09-08 the Telegram text told the operator to BUY SBIN and
TATAPOWER. Both had stop-breached that same morning. It also said "Continue
HOLD" on DABUR, NTPC and SUNPHARMA - all three already closed. None of the
five was in CURRENT.

The text was rendered from `data/aegis_today.csv`, the retired R1 legacy
generator, which never consults the canonical lifecycle or the breach
ledger. The workbook was rendered from the lifecycle. Two surfaces, two
engines, one chat - and the one with the authoritative-looking integrity
footer was the wrong one.

Even where the two agreed on a name they disagreed on its numbers:
ICICIBANK read entry 1426 / -0.7% in the text and 1449.50 / -2.29% in the
lifecycle.

So this module renders the message from `reports/context/
canonical_lifecycle_{market}.json` - the exact dataset behind the CURRENT
sheet. It computes nothing. If a position is not in CURRENT it cannot
appear here as a holding, and a stop-breached name cannot be advertised as
a buy, because the same upstream stage decided both.

WHAT IT WILL NOT DO
-------------------
It does not generate recommendations, rank, score, or re-price. It has no
opinion of its own. R1 rows are labelled ADVISORY on every line they
appear, because R1 is retired and excluded from production P&L. R3 columns
exist in the workbook but are deliberately NOT rendered here: every one
reads ABSTAIN today, and a shadow layer with no opinion adds nothing to a
message an operator reads on a phone.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.delivery.canonical_message.v1"

ENGINE_R1 = "R1"
ADVISORY_NOTE = "R1 = RETIRED ADVISORY · not production · excluded from P&L"


def _load(root: Path, market: str) -> Optional[dict]:
    p = (root / "reports" / "context"
         / f"canonical_lifecycle_{market.lower()}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _cur(v, market: str) -> str:
    if not isinstance(v, (int, float)):
        return "—"
    sym = "₹" if market.lower() == "india" else "$"
    return f"{sym}{v:,.2f}"


def _pct(v) -> str:
    return "—" if not isinstance(v, (int, float)) else f"{v:+.2f}%"


def _tick(t) -> str:
    return str(t or "").replace(".NS", "").replace(".BO", "")


def render(root: Path, market: str) -> Optional[str]:
    d = _load(root, market)
    if d is None:
        return None
    m = market.lower()
    asof = d.get("asof")
    cur = d.get("current") or []
    exits = d.get("exits") or []
    c = d.get("counts") or {}

    new = [r for r in cur if r.get("action") == "NEW"]
    aplus = [r for r in cur if r.get("action") == "ACTIVE+"]
    active = [r for r in cur if r.get("action") == "ACTIVE"]
    today_exits = [e for e in exits if str(e.get("exit_date"))[:10] == str(asof)[:10]]

    L = []
    L.append(f"🏢 NEXAQUANT · AEGIS {m.upper()}")
    L.append(f"📅 As of {asof} · canonical lifecycle")
    L.append("")
    L.append("━━━━━━━━━━━━━━━━━━━━━━━")
    L.append(f"🎯 TODAY · {len(new)} NEW · {len(aplus)} ACTIVE+ · "
             f"{len(active)} ACTIVE · {len(today_exits)} EXIT")
    L.append(f"   R2 {c.get('r2_investable', 0)} · MOMENTUM "
             f"{c.get('momentum_investable', 0)} · R1 {c.get('r1_investable', 0)} (advisory)")

    # A breach is the one thing an operator must not miss.
    n_bx = c.get("breach_exits_new_today", 0) or 0
    if n_bx:
        L.append("")
        L.append(f"🔴 {n_bx} position(s) BREACHED their stop today and left "
                 f"CURRENT · they are in EXIT HISTORY, not here")

    def block(title, rows, closed=False):
        if not rows:
            return
        L.append("")
        L.append("━━━━━━━━━━━━━━━━━━━━━━━")
        L.append(title)
        for r in rows:
            eng = str(r.get("engine") or "")
            tag = " · ADVISORY" if eng == ENGINE_R1 else ""
            t = _tick(r.get("ticker"))
            if closed:
                L.append(f"  {t} · {eng}{tag}")
                L.append(f"    {_cur(r.get('entry_price'), m)} → "
                         f"{_cur(r.get('exit_price'), m)}  "
                         f"{_pct(r.get('realized_pnl_pct'))}")
                L.append(f"    ✋ {r.get('exit_reason') or '—'}")
            else:
                L.append(f"  {t} · {eng}{tag} · held "
                         f"{r.get('holding_days', '—')}d")
                L.append(f"    {_cur(r.get('entry_price'), m)} → "
                         f"{_cur(r.get('current_price'), m)}  "
                         f"{_pct(r.get('pnl_pct'))}")
                # "dist +7.48%" reads as upside. It is the DOWNSIDE from
                # the current price to the stop, and a leading + on that
                # number invites exactly the wrong reading. Spelled out,
                # signed as the loss it is, and never called a target.
                _s = r.get("stop")
                _d = r.get("dist_to_stop_pct")
                _dtxt = ("—" if not isinstance(_d, (int, float))
                         else f"-{abs(_d):.2f}% below")
                L.append(f"    ⛔ Stop {_cur(_s, m)} "
                         f"({r.get('stop_state') or '—'})")
                L.append(f"       Stop distance {_dtxt} current price")

    block(f"🟢 NEW ({len(new)})", new)
    block(f"🔵 ACTIVE+ ({len(aplus)})", aplus)
    block(f"🟡 ACTIVE ({len(active)})", active)
    block(f"🔴 EXITED TODAY ({len(today_exits)})", today_exits, closed=True)

    if not cur:
        L.append("")
        L.append("Nothing investable today.")

    fn = d.get("_funnel") or {}
    if not new and fn.get("headline"):
        L.append("")
        L.append(f"🔎 Why no NEW: {fn['headline']}")

    st = d.get("stale_inputs") or []
    if st:
        L.append("")
        L.append("⛔ STALE INPUT · " + " · ".join(
            f"{x['input']} {x['verdict']} ({x['age_days']}d old)" for x in st))

    L.append("")
    L.append("━━━━━━━━━━━━━━━━━━━━━━━")
    L.append("🔐 Source")
    L.append(f"  canonical_lifecycle_{m}.json · the SAME dataset behind the")
    L.append("  CURRENT sheet · this message cannot disagree with the XLSX")
    L.append(f"  {ADVISORY_NOTE}")
    L.append("  Stop distance = downside from the current price to the")
    L.append("  stop. It is NOT a profit target · no target is implied.")
    L.append("  Advisory only · PAPER_ONLY · Not investment advice")
    return "\n".join(L)


def emit(root: Path, market: str, text: str) -> Path:
    p = (root / "reports" / "telegram"
         / f"canonical_message_{market.lower()}.txt")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def send(root: Path, market: str) -> tuple:
    """Render and send · returns (ok, detail)."""
    import os
    import urllib.parse
    import urllib.request
    text = render(root, market)
    if text is None:
        return False, f"no canonical lifecycle dataset for {market}"
    emit(root, market, text)
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not tok or not chat:
        return False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    # Plain text · no parse_mode. HTML parsing failed on this chat before
    # ("Unsupported start tag") and silently degraded; there is nothing in
    # this message that needs markup.
    for chunk in [text[i:i + 3900] for i in range(0, len(text), 3900)]:
        data = urllib.parse.urlencode(
            {"chat_id": chat, "text": chunk,
             "disable_web_page_preview": "true"}).encode()
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, data=data), timeout=60) as r:
                body = r.read().decode("utf-8", "replace")
            if '"ok":true' not in body:
                return False, body[:200]
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
    return True, "sent (%d chars)" % len(text)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="canonical daily message")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--send", action="store_true", help="actually send")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    rc = 0
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        if a.send:
            ok, detail = send(root, m)
            print(f"canonical_message:{m} · sent={ok} · {detail[:120]}")
            if not ok:
                rc = 1
        else:
            t = render(root, m)
            if t is None:
                print(f"canonical_message:{m} · no dataset")
                rc = 1
                continue
            p = emit(root, m, t)
            print(f"canonical_message:{m} · rendered {len(t)} chars -> {p}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
