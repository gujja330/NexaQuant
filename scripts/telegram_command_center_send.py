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
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.delivery.telegram.command_center import (  # noqa: E402
    load_and_render, render_research_platform_message,
    render_intraday_platform_message,
    ENGINE_ID, SCHEMA_FINGERPRINT,
)
from backend.delivery.telegram.detail_xlsx import (  # noqa: E402
    build_unified_history, build_and_stamp_all,
    maybe_sync_google_sheet,
)
from backend.portfolio.position_store.mark_to_market import (  # noqa: E402
    mark_to_market as _mark_to_market,
    validate_position_freshness as _validate_freshness,
    validate_payload_asof_matches_today as _validate_payload_asof,
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


def _send_document(token: str, chat_id: str, file_path: Path,
                       caption: str = "") -> tuple[bool, str]:
    """Upload a file to Telegram via sendDocument · used for detail reports."""
    if not file_path.exists():
        return False, f"file missing: {file_path}"
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    boundary = "----AEGISFormBoundary" + os.urandom(8).hex()
    body = []
    def _p(field, value):
        body.append(f"--{boundary}\r\n"
                       f'Content-Disposition: form-data; name="{field}"\r\n\r\n'
                       f"{value}\r\n")
    _p("chat_id", chat_id)
    if caption:
        _p("caption", caption[:1024])
        # No parse_mode · plain text · avoids Markdown-parse errors from
        # underscores in field names (Run_Type) or dashes in tickers.
    file_bytes = file_path.read_bytes()
    body.append(f"--{boundary}\r\n"
                   f'Content-Disposition: form-data; name="document"; '
                   f'filename="{file_path.name}"\r\n'
                   f"Content-Type: text/markdown\r\n\r\n")
    # Build multipart payload as bytes
    prefix = "".join(body).encode("utf-8")
    suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
    payload = prefix + file_bytes + suffix
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = r.read().decode("utf-8", errors="replace")
        return True, resp[:120]
    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8", errors="replace")
        except Exception:
            err = str(e)
        return False, f"HTTP {e.code}: {err[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


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

    # ── GUARD 6 · payload asof-freshness (post-mortem 2026-08-01) ──
    # Refuse to send if recommendations.json's asof is NOT today.
    # This closes the "restored-from-git stale payload got sent" gap.
    try:
        vpa = _validate_payload_asof(_ROOT, market)
        if vpa["verdict"] == "STALE_PAYLOAD":
            print(f"[payload_asof:{market}] REFUSED · asof={vpa['asof']} "
                    f"today={vpa['today']} ({vpa['days_stale']}d stale)")
            print(f"  · Fix: run daily pipeline "
                    f"'python -m backend.recommendation.ssot.run --market {market}' "
                    f"(may need --force if snapshot exists)")
            print(f"  · Or override with SEND_FORCE_STALE=1 env var (destructive).")
            if not os.environ.get("SEND_FORCE_STALE"):
                return False, {"market": market, "refused": "stale_payload_asof", **vpa}
        elif vpa["verdict"] == "OK":
            print(f"[payload_asof:{market}] OK · asof={vpa['asof']} (today)")
        else:
            print(f"[payload_asof:{market}] {vpa['verdict']} · continuing anyway")
    except Exception as e:
        print(f"[payload_asof:{market}] check failed · {type(e).__name__}: {e} · continuing")

    # ── PRECAUTION 1 · mark-to-market before render (post-mortem 2026-07-31) ──
    # Ensures every active position has today's actual close price · so
    # Max Gain / Max DD reflect reality (not stale 0.00% from entry-price)
    try:
        mtm = _mark_to_market(_ROOT, market)
        print(f"[mtm:{market}] repriced={mtm['n_repriced']}/{mtm['n_positions']} "
                f"missing={mtm['n_missing_price']}")
    except Exception as e:
        print(f"[mtm:{market}] failed · {type(e).__name__}: {e} · continuing anyway")

    # ── PRECAUTION 2 · freshness check · REFUSE to send if positions stale ──
    # Prevents the "0.00% Max Gain everywhere" incident from ever recurring
    try:
        v = _validate_freshness(_ROOT, market, max_stale_days=2)
        if v["verdict"] == "STALE" and v["n_stale"] > 0:
            print(f"[freshness:{market}] REFUSED · {v['n_stale']} stale positions "
                    f"(last_seen > 2 days behind asof)")
            for s in v["stale_tickers"][:5]:
                print(f"  · {s['ticker']}: last_seen={s['last_seen']} "
                        f"({s['days_behind']}d behind)")
            print(f"  · Fix: run 'python scripts/mark_to_market.py --market {market}' "
                    f"or wait for tomorrow's daily pipeline.")
            print(f"  · Or override with SEND_FORCE_STALE=1 env var (destructive).")
            if not os.environ.get("SEND_FORCE_STALE"):
                return False, {"market": market, "refused": "stale_positions", **v}
        else:
            print(f"[freshness:{market}] OK · {v['n_active']} active positions all fresh")
    except Exception as e:
        print(f"[freshness:{market}] check failed · {type(e).__name__}: {e} · continuing")

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

    # Research Platform second message DISABLED 2026-07-30 per operator:
    # "ensure single message for india and single message for usa."
    research_ok = True

    # Detail MD per-market REMOVED 2026-08-01 · replaced by ONE unified
    # XLSX file attached once at end of main() with Date + Country + Run_Type
    # columns · appended daily to reports/telegram/aegis_history.xlsx.

    return (ok and research_ok), {
        "market":        market,
        "ok":            ok,
        "research_ok":   research_ok,
        **meta,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--dry-run", action="store_true",
                       help="Render + print message but do not send")
    # Operator directive 2026-08-04: "i should get on xlsx output plz, no
    # need of messages again". XLSX-only mode suppresses the compact per-
    # market Command Center message · daily delivery is the XLSX attachment
    # (+ optional caption) alone. Default ON to match new operator preference.
    ap.add_argument("--with-message", action="store_true",
                       help="Also send the compact Command Center message "
                            "(default: OFF · XLSX attachment only)")
    args = ap.parse_args()

    _load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    markets = ["india", "usa"] if args.market == "both" else [args.market]

    if args.dry_run:
        if args.with_message:
            for m in markets:
                msg, meta = load_and_render(_market_reports(m), m)
                print(f"===== DRY RUN · {m} · {meta['message_chars']} chars =====")
                print(msg)
                print()
        else:
            print(f"===== DRY RUN · XLSX-only mode · markets={markets} =====")
            print("(compact message suppressed · pass --with-message to render)")
        return 0

    if not token or not chat_id:
        print(f"[command_center] MISSING TELEGRAM tokens · skipping "
              f"(sender remains optional in CI). Requested markets: {markets}")
        return 2   # non-fatal · matches optional-step convention

    all_ok = True
    if args.with_message:
        for m in markets:
            ok, _ = _send_one_market(m, token, chat_id)
            all_ok = all_ok and ok
    else:
        print(f"[command_center] XLSX-only mode · compact message skipped · "
              f"markets={markets} (pass --with-message to re-enable)")

    # ── UNIFIED XLSX · one file across all markets · attached ONCE ──
    # Operator directive 2026-08-01: "better send me that xlsx into telegram
    # daily thats it. simple format of xlsx" · "runner 1, runner 2 u can mix
    # into a column called Run_type" · "add country too" · "everyday we
    # can update same sheet".
    xlsx_ok = True
    try:
        from datetime import date as _date
        asof = _date.today().isoformat()
        # v5 · stamp regime + rank + profit-protection · then build XLSX
        xlsx_path = build_and_stamp_all(_ROOT, asof, markets=markets)
        # Sprint H · attach operator guide to Monday caption (weekly refresher)
        try:
            from backend.delivery.telegram.operator_guide import append_to_caption as _guide
            from datetime import date as _dt
            _dow = _dt.today().isoweekday()   # 1=Mon .. 7=Sun
            _CAPTION_APPEND_GUIDE = _guide
        except Exception:
            _CAPTION_APPEND_GUIDE = None
        # Guard 7 · Context Health Monitor · every report is a guard
        # (operator directive 2026-08-05)
        try:
            from backend.context.health_monitor import (
                run_health_check as _hc, emit as _hc_emit, render_summary as _hc_render)
            health = _hc(_ROOT)
            _hc_emit(_ROOT, health)
            print(f"[guard7:health] {_hc_render(health)}")
            if health.get("overall_verdict") == "RED" \
               and os.environ.get("SEND_FORCE_STALE") != "1":
                print(f"[guard7:health] BLOCKING send · {health['n_critical_fails']} "
                      f"critical engines failed. Override with SEND_FORCE_STALE=1")
                for r in health.get("critical_fails", [])[:5]:
                    print(f"    ✗ {r['path']}: {r['verdict']} · {r['reason']}")
                return 2
        except Exception as e:
            print(f"[guard7:health] check failed · {type(e).__name__}: {e} · proceeding")
        # Guard 8 · Price Integrity · verifies data pull is CORRECT before send
        # (operator directive 2026-08-06 · "pipeline should be very strong in
        # pulling right data with guard")
        try:
            from backend.context.price_integrity_guard import (
                check_all as _pig, emit as _pig_emit, render_summary as _pig_render)
            pig = _pig(_ROOT, asof)
            _pig_emit(_ROOT, pig)
            print(f"[guard8:price] {_pig_render(pig)}")
            if pig.get("verdict") == "RED" \
               and os.environ.get("PRICE_GUARD_OVERRIDE") != "1":
                print(f"[guard8:price] BLOCKING send · {pig['n_critical']} CRITICAL "
                      f"price mismatches. Override with PRICE_GUARD_OVERRIDE=1")
                for r in pig.get("critical_issues", [])[:5]:
                    print(f"    ✗ {r['market']} {r['ticker']} · {r['check']}: {r['detail']}")
                return 2
        except Exception as e:
            print(f"[guard8:price] check failed · {type(e).__name__}: {e} · proceeding")
        # 2026-08-08 · Guard 9 · Pipeline heartbeat (operator directive after
        # silent Aug-3 pipeline miss: "pages you if a trading day passes with
        # no pipeline execution"). Emit gap alert prepended to caption so
        # operator sees it BEFORE the XLSX arrives.
        heartbeat_banner = ""
        try:
            from backend.context.pipeline_heartbeat import (
                check as _hb_check, render as _hb_render)
            for _m in markets:
                _hb = _hb_check(_ROOT, _m, asof)
                print(f"[guard9:heartbeat:{_m}] {_hb_render(_hb)}")
                if _hb["status"] in ("CRITICAL", "WARNING"):
                    heartbeat_banner += _hb["message"] + "\n"
        except Exception as e:
            print(f"[guard9:heartbeat] check failed · {type(e).__name__}: {e} · proceeding")
        # 2026-08-08 · Caption clarified · operator confused why XLSX dated
        # 2026-08-07 arrived at 03:22 IST on 2026-08-08 (cron 20:30 UTC Fri
        # = 02:00 IST Sat · US Fri close = last trading data). Now shows
        # both the trading-day the data reflects AND the IST delivery time
        # so there's no ambiguity.
        _now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        _delivered_ist = _now_ist.strftime("%Y-%m-%d %H:%M IST")
        _mkt_label = ("US session" if "usa" in markets
                                else "NSE session" if "india" in markets
                                else "session")
        # Heartbeat banner (if any gap) prepended so operator sees it FIRST
        _hb_prefix = f"{heartbeat_banner}\n" if heartbeat_banner else ""
        caption = (f"{_hb_prefix}"
                       f"📊 AEGIS Daily · {_mkt_label} {asof} (last trading day)\n"
                       f"delivered {_delivered_ist}\n"
                       f"One row per stock · columns: Date · Country · Run Type · Ticker + "
                       f"45+ more fields · daily appended · sortable in Excel")
        # Sprint H · Monday XLSX carries the operator guide as reminder
        if _CAPTION_APPEND_GUIDE is not None:
            caption = _CAPTION_APPEND_GUIDE(caption, _dow)
        xlsx_ok, xlsx_msg = _send_document(token, chat_id, xlsx_path,
                                                  caption=caption)
        # Sprint J-final REVERTED · single-file delivery ONLY (operator directive:
        # "one sheet · one history · no separate Fresh Buys"). Fresh opportunities
        # are visible via Run_Type=R1_NEW/R2_NEW filter in the same sheet.
        print(f"[xlsx:{','.join(markets)}] file={xlsx_path.name} · sent={xlsx_ok}")
        if not xlsx_ok:
            print(f"  detail: {xlsx_msg[:180]}")
        # Record successful heartbeat (only if send actually worked)
        if xlsx_ok:
            try:
                from backend.context.pipeline_heartbeat import record_run as _hb_record
                for _m in markets:
                    _hb_record(_ROOT, _m, asof)
            except Exception as e:
                print(f"[heartbeat] record failed · {type(e).__name__}: {e}")
        # Optional · Google Sheets mirror (silent no-op if creds absent)
        gs_ok, gs_msg = maybe_sync_google_sheet(xlsx_path)
        if gs_ok:
            print(f"[gsheets] {gs_msg}")
        _append_delivery_ledger({
            "ts_utc":  datetime.now(timezone.utc).isoformat(),
            "engine":  "aegis.delivery.telegram.xlsx.v1",
            "kind":    "unified_xlsx",
            "file":    str(xlsx_path.relative_to(_ROOT)),
            "ok":      xlsx_ok,
            "gsheets": gs_ok,
        })
    except Exception as e:
        print(f"[xlsx] render/send failed · {type(e).__name__}: {e}")
        xlsx_ok = False

    # Terminal marker for retry-wrapper compatibility
    print(f"sent ({len(markets)} messages + 1 xlsx).")
    return 0 if (all_ok and xlsx_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
