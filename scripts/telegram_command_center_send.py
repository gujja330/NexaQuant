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
            # 2026-08-12 CEO CI fix · scope guard to the market we're actually
            # sending. India CI has no USA parquets (they're .gitignored and
            # only refreshed by aegis-usa.yml) so evaluating USA on India CI
            # produced 500+ fake CRITICALS and blocked India send for 2 days.
            pig = _pig(_ROOT, asof, markets=tuple(markets))
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
        # 2026-08-08 · Two-file delivery per operator directive: "send me both
        # xlsx in different timezones · usa separate, india separate."
        # Split unified aegis_history.xlsx into two market-specific files,
        # each attached as its own Telegram message with market-specific
        # timezone caption (India: IST · USA: CST + IST).
        from openpyxl import load_workbook as _lwb
        from openpyxl.styles import PatternFill as _PF
        _now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        _now_cst = datetime.now(timezone(timedelta(hours=-6)))
        _delivered_ist = _now_ist.strftime("%Y-%m-%d %H:%M IST")
        _delivered_cst = _now_cst.strftime("%Y-%m-%d %H:%M CST")
        _STATUS_FILLS_LOCAL = {
            "STRONG BUY":       _PF(start_color="70AD47", end_color="70AD47", fill_type="solid"),
            "BUY":              _PF(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
            "HOLD":             _PF(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid"),
            "EXIT":             _PF(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid"),
            "ROTATED_SAMEDAY":  _PF(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid"),
        }

        # 2026-08-08 · Config-driven largecap seed (was hardcoded)
        _INDIA_LARGECAP = set()
        try:
            import yaml as _yaml
            _tiers_path = _ROOT / "configs" / "india_universe_tiers.yaml"
            if _tiers_path.exists():
                _tiers = _yaml.safe_load(_tiers_path.read_text(encoding="utf-8")) or {}
                _INDIA_LARGECAP = set(_tiers.get("largecap_tickers") or [])
        except Exception as _e:
            print(f"[config:india_universe_tiers] load failed · {_e}")

        def _cap_size(ticker: str, market: str) -> str:
            """Return LargeCap / MidCap tag for the ticker."""
            short = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
            if market.upper() == "USA":
                return "LargeCap (S&P 500)"
            # India: NIFTY 50 = LargeCap · anything else in NIFTY 200 = MidCap
            return "LargeCap" if short in _INDIA_LARGECAP else "MidCap"

        # Sector cache (operator directive: "sector in output xlsx mandatory")
        # Populated from yfinance · persisted at reports/sector_cache.json
        _sector_cache_path = _ROOT / "reports" / "sector_cache.json"
        _sector_cache = json.loads(_sector_cache_path.read_text(encoding="utf-8")) \
                                if _sector_cache_path.exists() else {"india": {}, "usa": {}}

        def _sector_for(ticker: str, market: str) -> str:
            """Look up sector · cached · fallback to '—'."""
            short = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
            bucket = _sector_cache.get(market.lower(), {})
            return bucket.get(short) or bucket.get(str(ticker).upper()) or "—"

        # Action explanations for the Action column (operator: "actions needed
        # short explanation · enter buy zone means to buy on that days?")
        _ACTIONS = {
            "STRONG BUY":      "Enter today · top pick · high conviction",
            "BUY":             "Enter or add · in buy zone",
            "HOLD":            "Hold · no action needed today",
            "EXIT":            "Sell/rotate today · closed position",
            "ROTATED_SAMEDAY": "Not held · same-day rotation artifact",
        }

        def _parquet_close(ticker: str, market: str, target_date: str) -> float | None:
            """Latest parquet close on or before target_date · source of truth."""
            import pandas as _pd
            short = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
            base = "usa/data/raw/us" if market.upper() == "USA" else "data/raw/india"
            p = _ROOT / base / f"{short}_D1.parquet"
            if not p.exists(): return None
            try:
                d = _pd.read_parquet(p)
                col = "close" if "close" in d.columns else "Close"
                d.index = _pd.to_datetime(d.index).strftime("%Y-%m-%d")
                if target_date in d.index: return float(d.loc[target_date, col])
                earlier = [dt for dt in d.index if dt <= target_date]
                return float(d.loc[earlier[-1], col]) if earlier else None
            except Exception:
                return None

        def _parquet_prev_close(ticker: str, market: str, target_date: str) -> float | None:
            """Trading day close STRICTLY BEFORE target_date · fixes Today Move
            lag bug where Prev Close was stamped when row was written and
            never re-derived for the observation date. CEO audit fix 2026-08-10."""
            import pandas as _pd
            short = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
            base = "usa/data/raw/us" if market.upper() == "USA" else "data/raw/india"
            p = _ROOT / base / f"{short}_D1.parquet"
            if not p.exists(): return None
            try:
                d = _pd.read_parquet(p)
                col = "close" if "close" in d.columns else "Close"
                d.index = _pd.to_datetime(d.index).strftime("%Y-%m-%d")
                strictly_before = [dt for dt in d.index if dt < target_date]
                return float(d.loc[strictly_before[-1], col]) if strictly_before else None
            except Exception:
                return None

        def _split_and_send(mkt_label: str, mkt_key: str, caption_body: str):
            src_wb = _lwb(xlsx_path)
            src_ws = src_wb["AEGIS Daily"] if "AEGIS Daily" in src_wb.sheetnames else src_wb.active
            h = [c.value for c in src_ws[1]]
            c_ctry = h.index("Country") + 1
            c_st = h.index("Status") + 1
            c_tk = h.index("Ticker") + 1
            c_date = h.index("Date") + 1
            c_recommended = h.index("Recommended") + 1 if "Recommended" in h else None
            c_entry = h.index("Entry Price") + 1 if "Entry Price" in h else None
            c_current = h.index("Current Price") + 1 if "Current Price" in h else None
            c_perf = h.index("Current Perf %") + 1 if "Current Perf %" in h else None
            c_exit_pnl = h.index("Exit P&L %") + 1 if "Exit P&L %" in h else None
            c_conf = h.index("Confidence %") + 1 if "Confidence %" in h else None
            c_stop = h.index("Stop Loss") + 1 if "Stop Loss" in h else None
            c_t1 = h.index("Target 1") + 1 if "Target 1" in h else None
            c_t2 = h.index("Target 2") + 1 if "Target 2" in h else None
            c_alerts = h.index("Alerts") + 1 if "Alerts" in h else None
            c_sector_existing = h.index("Sector") + 1 if "Sector" in h else None
            c_prev_close = h.index("Prev Close") + 1 if "Prev Close" in h else None
            c_today_move = h.index("Today Move %") + 1 if "Today Move %" in h else None

            # Load PRIORITY_MATRIX + DECISION vocab BEFORE row iteration
            # so History-sheet row loop can resolve decisions
            PRIORITY_MATRIX = {}
            # 2026-08-14 · Sprint K Part 28 · binding risk signals list.
            # If any of these strings appear in the Alerts column, priority
            # is forced to bucket R (Risk Controller veto · highest priority).
            BINDING_RISK_SIGNALS: list[str] = []
            try:
                import yaml as _yaml
                _pm_path = _ROOT / "configs" / "priority_matrix.yaml"
                if _pm_path.exists():
                    _pm = _yaml.safe_load(_pm_path.read_text(encoding="utf-8")) or {}
                    for bucket, d in (_pm.get("buckets") or {}).items():
                        PRIORITY_MATRIX[bucket] = (
                            d.get("urgency", ""), d.get("reason", ""),
                            d.get("action", ""), d.get("review", ""),
                            d.get("color", "F2F2F2"),
                        )
                    BINDING_RISK_SIGNALS = [str(s).upper()
                                                    for s in (_pm.get("binding_risk_signals") or [])]
            except Exception as _e:
                print(f"[config:priority_matrix] load failed · {_e}")
            PRIORITY_FILLS = {k: _PF(start_color=v[4], end_color=v[4], fill_type="solid")
                                     for k, v in PRIORITY_MATRIX.items()}

            DECISION_RULES = []
            DECISION_COLORS = {}
            try:
                import yaml as _yaml
                _dv_path = _ROOT / "configs" / "decision_vocabulary.yaml"
                if _dv_path.exists():
                    _dv = _yaml.safe_load(_dv_path.read_text(encoding="utf-8")) or {}
                    DECISION_RULES = _dv.get("rules") or []
                    DECISION_COLORS = _dv.get("colors") or {}
            except Exception as _e:
                print(f"[config:decision_vocabulary] load failed · {_e}")

            # 2026-08-14 · operator-approved 6-tier color scheme (msg 380)
            # Load configs/decision_colors.yaml · classify each row by DECISION
            # family · row color + sort by tier_rank. Config-driven per no-hardcode rule.
            DECISION_TIERS: dict = {}     # tier_key -> full tier dict
            TIER_MATCH_ORDER: list = []   # ordered list of tier_keys to walk
            TIER_LEGEND_HEADING = "COLOR LEGEND · row color = actionable priority"
            try:
                import yaml as _yaml
                _dc_path = _ROOT / "configs" / "decision_colors.yaml"
                if _dc_path.exists():
                    _dc = _yaml.safe_load(_dc_path.read_text(encoding="utf-8")) or {}
                    DECISION_TIERS = _dc.get("tiers") or {}
                    TIER_MATCH_ORDER = _dc.get("match_order") or list(DECISION_TIERS.keys())
                    TIER_LEGEND_HEADING = _dc.get("legend_heading") or TIER_LEGEND_HEADING
            except Exception as _e:
                print(f"[config:decision_colors] load failed · {_e}")

            def _decision_tier(decision_text: str, is_new_position: bool) -> str:
                """Return one of the tier keys (strong_buy/buy/new/hold/exit/closed)
                by walking match_order and matching Decision keywords (uppercase)
                or the trigger_on_new_position flag."""
                dt_up = str(decision_text or "").upper()
                for tier_key in TIER_MATCH_ORDER:
                    tier = DECISION_TIERS.get(tier_key) or {}
                    if tier.get("trigger_on_new_position") and is_new_position:
                        return tier_key
                    for kw in (tier.get("keywords_any") or []):
                        if kw.upper() in dt_up:
                            return tier_key
                # Ultimate fallback: hold (yellow)
                return "hold" if "hold" in DECISION_TIERS else next(iter(DECISION_TIERS.keys()), "hold")

            def _resolve_decision(action, inv_quality, status):
                a = str(action or "").strip()
                iq = str(inv_quality or "").strip()
                for rule in DECISION_RULES:
                    m = rule.get("match") or {}
                    if not m:
                        return rule.get("decision", "—"), rule.get("color", "gray")
                    if "action" in m and m["action"] != a:
                        continue
                    if "inv_quality_in" in m and iq not in m["inv_quality_in"]:
                        continue
                    return rule.get("decision", "—"), rule.get("color", "gray")
                return "— UNKNOWN", "gray"

            # Execution Decision Layer config (2026-08-09)
            EXEC_CFG = {}
            try:
                import yaml as _yaml
                _ex_path = _ROOT / "configs" / "execution_windows.yaml"
                if _ex_path.exists():
                    EXEC_CFG = _yaml.safe_load(_ex_path.read_text(encoding="utf-8")) or {}
            except Exception as _e:
                print(f"[config:execution_windows] load failed · {_e}")

            def _next_review_date(review_str, from_date_iso):
                offsets = (EXEC_CFG.get("review_offsets") or {})
                key = str(review_str or "").strip().upper()
                offset = offsets.get(key)
                if offset is None or offset == "null": return ""
                if offset == 0: return from_date_iso
                try:
                    from datetime import date as _dtc, timedelta as _tdc
                    d = _dtc.fromisoformat(from_date_iso[:10])
                    added = 0
                    while added < offset:
                        d += _tdc(days=1)
                        if d.weekday() < 5: added += 1
                    return d.isoformat()
                except Exception:
                    return ""

            def _execution_window(action):
                a = str(action or "").strip()
                for rule in (EXEC_CFG.get("execution_windows") or []):
                    m = rule.get("match") or {}
                    if not m: return rule.get("window", "—")
                    if "action" in m and m["action"] != a: continue
                    return rule.get("window", "—")
                return "—"

            def _price_trigger(action, stop_v, t1_v, curr_v):
                triggers = (EXEC_CFG.get("price_triggers") or {})
                cfg = triggers.get(str(action or "").strip())
                if not cfg: return ""
                source = cfg.get("source")
                label = cfg.get("label", "")
                price = {"stop": stop_v, "target_1": t1_v, "current": curr_v}.get(source)
                if not isinstance(price, (int, float)) or price <= 0: return ""
                return f"{label} {price:.2f}"

            # Filter rows by market
            keep_rows = [row for row in src_ws.iter_rows(min_row=2, values_only=False)
                                    if str(row[c_ctry-1].value or "").upper() == mkt_key.upper()]

            # 2026-08-14 · operator directives:
            #   1. "usa list is very big still in xlsx"
            #   2. "we switched to s&P 500 large cap, why we need still old
            #       stocks like trv and all"
            #
            # Root cause: source workbook keeps ALL 507 USA universe-scan rows
            # daily. Also historical position_store carries pre-S&P-500-switch
            # tickers (TRV · V · etc. from earlier universe) that are no longer
            # in the active universe.
            #
            # Filter = CANONICAL_SET  INTERSECT  CURRENT_UNIVERSE_SET
            #   canonical  = v3-selected ∪ position_store (active + exited + history)
            #   universe   = today's active tickers from usa/reports/universe.json
            #                (currently S&P 500 large cap · 500-ish tickers)
            # Historical tickers no longer in the S&P 500 = dropped.
            # India already has ~15 selected only · this filter is a no-op there.
            if mkt_key.upper() == "USA":
                import json as _json
                _canonical: set = set()
                # a. Currently selected candidates (v3)
                _v3 = _ROOT / "usa" / "reports" / "recommendations_v3.json"
                if _v3.exists():
                    try:
                        _d = _json.loads(_v3.read_text(encoding="utf-8"))
                        for _r in (_d.get("recommendations") or []):
                            _tk = str(_r.get("ticker") or "").upper()
                            if _tk: _canonical.add(_tk)
                    except Exception:
                        pass
                # b. Any ticker ever in position_store (active + exited)
                _pos = _ROOT / "usa" / "reports" / "position_store" / "usa" / "positions.json"
                if _pos.exists():
                    try:
                        _pd = _json.loads(_pos.read_text(encoding="utf-8"))
                        for _tk in (_pd.get("positions") or {}).keys():
                            _canonical.add(str(_tk).upper())
                        for _e in (_pd.get("exited") or []):
                            _tk = str(_e.get("ticker") or "").upper()
                            if _tk: _canonical.add(_tk)
                    except Exception:
                        pass
                # c. (removed 2026-08-14 · operator: "we switched to S&P 500
                #     large cap, why we need still old stocks like TRV")
                # history.jsonl is a raw event log · contains pre-switch
                # position openings (Jul 29 TRV, V, HON etc. from earlier
                # universe experiments). Using it re-surfaces stale tickers
                # the operator no longer wants to see. Only positions.json
                # (managed by portfolio_manager · reflects current era) is
                # the authoritative "what am I holding" source.

                # d. Current active universe (S&P 500) · intersect to drop
                # historical tickers no longer in the universe.
                _current_universe: set = set()
                _uni = _ROOT / "usa" / "reports" / "universe.json"
                if _uni.exists():
                    try:
                        _ud = _json.loads(_uni.read_text(encoding="utf-8"))
                        for _t in (_ud.get("tickers") or []):
                            _sym = _t.get("symbol") if isinstance(_t, dict) else str(_t)
                            if _sym:
                                _current_universe.add(str(_sym).upper())
                    except Exception:
                        pass
                # Also add v3 selected as guaranteed-present · even if universe
                # file happens to be stale · today's selections are authoritative.
                _v3_set: set = set()
                if _v3.exists():
                    try:
                        _d = _json.loads(_v3.read_text(encoding="utf-8"))
                        for _r in (_d.get("recommendations") or []):
                            _tk = str(_r.get("ticker") or "").upper()
                            if _tk: _v3_set.add(_tk)
                    except Exception:
                        pass
                _effective_universe = (_current_universe | _v3_set) if _current_universe else _canonical
                _final_set = _canonical & _effective_universe
                _before = len(keep_rows)
                _dropped_stale = _canonical - _effective_universe   # observability
                keep_rows = [row for row in keep_rows
                                    if str(row[c_tk-1].value or "").upper() in _final_set]
                print(f"[xlsx:USA] canonical∩universe filter · {_before} -> {len(keep_rows)} rows "
                      f"(canonical={len(_canonical)} · universe={len(_current_universe)} · "
                      f"final={len(_final_set)} · dropped-as-out-of-universe={len(_dropped_stale)})")
                if _dropped_stale:
                    _sample = sorted(_dropped_stale)[:10]
                    print(f"[xlsx:USA]   dropped historical (not in current universe): "
                          f"{_sample}{'...' if len(_dropped_stale) > 10 else ''}")

            # 2026-08-15 · Section 5 · SKIP rows NEVER appear in the primary
            # portfolio table. SKIP means "not an investment" · showing it as
            # a decision would corrupt portfolio P&L + confuse the operator.
            # SKIP candidates go to a separate research dataset (see
            # reports/research/skip_candidates_{market}.jsonl) so opportunity-
            # cost analysis stays possible without polluting portfolio counts.
            _skipped_rows = [row for row in keep_rows
                                       if str(row[c_st-1].value or "").upper() == "SKIP"]
            _before_skip = len(keep_rows)
            keep_rows = [row for row in keep_rows
                                if str(row[c_st-1].value or "").upper() != "SKIP"]
            if _skipped_rows:
                _skip_out = (_ROOT / "reports" / "research" /
                                    f"skip_candidates_{mkt_key.lower()}.jsonl")
                _skip_out.parent.mkdir(parents=True, exist_ok=True)
                try:
                    import json as _jj
                    with _skip_out.open("a", encoding="utf-8") as _sf:
                        for _sr in _skipped_rows:
                            _sf.write(_jj.dumps({
                                "asof":   str(_sr[c_date-1].value or "")[:10],
                                "ticker": str(_sr[c_tk-1].value or ""),
                                "runner": str(_sr[3].value or "") if len(_sr) > 3 else "",
                                "status": "SKIP",
                                "current_price": _sr[c_current-1].value if c_current else None,
                                "note":   "Filtered from portfolio table · opportunity-cost tracking only",
                            }, default=str) + "\n")
                    print(f"[xlsx:{mkt_key}] SKIP filter · {_before_skip} -> {len(keep_rows)} rows "
                          f"({len(_skipped_rows)} SKIP moved to {_skip_out.relative_to(_ROOT)})")
                except Exception as _e:
                    print(f"[xlsx:{mkt_key}] SKIP research write failed · {_e}")

            # Write market-specific XLSX file · adds "Cap Size" column at end
            from openpyxl import Workbook as _WB
            out_path = xlsx_path.parent / f"aegis_history_{mkt_key.lower()}.xlsx"
            wb2 = _WB()
            ws2 = wb2.active
            ws2.title = f"AEGIS {mkt_key.upper()}"
            # Header + new columns (Cap Size + Opp Age)
            # Opp Age: NEW = row_date == Recommended date · OLD = held from prior day
            # (operator: "if I open sheet on monday, I might see new buy options
            # to invest if I missed old opportunities")
            new_h = list(h) + [
                "Cap Size", "Opp Age",
                "Investability", "Inv Verdict",
                "🎯 DECISION", "Urgency", "Reason", "Action", "Review",
                "Price Trigger", "Next Review", "Execution Window",
            ]
            for c, name in enumerate(new_h, start=1):
                cell = ws2.cell(1, c, name)
                cell.fill = HEADER_FILL if 'HEADER_FILL' in globals() else _PF(
                    start_color="1F4E78", end_color="1F4E78", fill_type="solid")
                cell.font = _Font(bold=True, color="FFFFFF", size=11)
            # Column widths from source
            from openpyxl.utils import get_column_letter as _gcl_src
            for i in range(1, len(h)+1):
                c_letter = _gcl_src(i)
                if c_letter in src_ws.column_dimensions:
                    ws2.column_dimensions[c_letter].width = src_ws.column_dimensions[c_letter].width
            # New Cap Size column width
            from openpyxl.utils import get_column_letter as _gcl
            ws2.column_dimensions[_gcl(len(new_h))].width = 18
            # Data rows · backfill Sector + repair stale Current Price
            latest_date = max((str(r[c_date-1].value or "")[:10] for r in keep_rows), default="")
            for r_idx, row in enumerate(keep_rows, start=2):
                tk = row[c_tk-1].value
                status = row[c_st-1].value
                # CEO audit fix 2026-08-10 · unconditional Current/Prev/Perf/TodayMove
                # recompute from PARQUET at row's Date · applies to ALL statuses
                # (was previously skipped for EXIT rows · leaving stale carry-forward)
                row_dt_str = str(row[c_date-1].value or "")[:10]
                entry_v = row[c_entry-1].value if c_entry else None
                # Current price at row's date
                live_curr = _parquet_close(tk, mkt_key, row_dt_str) if row_dt_str else None
                repaired_current = round(live_curr, 2) if live_curr else None
                # Perf = (Current - Entry) / Entry · always recomputed
                repaired_perf = None
                if repaired_current and isinstance(entry_v, (int, float)) and entry_v > 0:
                    repaired_perf = round((repaired_current - entry_v) / entry_v * 100, 2)
                # Prev Close = strictly-before close of row's date
                live_prev = _parquet_prev_close(tk, mkt_key, row_dt_str) if row_dt_str else None
                repaired_prev_close = round(live_prev, 2) if live_prev else None
                # Today Move = (Current - Prev) / Prev · always recomputed
                repaired_today_move = None
                if repaired_current is not None and repaired_prev_close is not None \
                        and repaired_prev_close > 0:
                    repaired_today_move = round(
                        (repaired_current - repaired_prev_close) / repaired_prev_close * 100, 2)

                for c_idx, cell in enumerate(row, start=1):
                    val = cell.value
                    if c_sector_existing and c_idx == c_sector_existing and not val:
                        val = _sector_for(tk, mkt_key)
                    if repaired_current is not None and c_idx == c_current:
                        val = repaired_current
                    if repaired_perf is not None and c_idx == c_perf:
                        val = repaired_perf
                    if repaired_prev_close is not None and c_prev_close and c_idx == c_prev_close:
                        val = round(repaired_prev_close, 2)
                    if repaired_today_move is not None and c_today_move and c_idx == c_today_move:
                        val = repaired_today_move
                    ws2.cell(r_idx, c_idx, val)
                # 9 appended columns · positions counted from END
                if not hasattr(_split_and_send, "_inv_loaded"):
                    _split_and_send._inv_map_for_sheet2 = {}
                    try:
                        _inv_path = _ROOT / "reports" / f"investability_{mkt_key.lower()}.json"
                        if _inv_path.exists():
                            _inv_data = json.loads(_inv_path.read_text(encoding="utf-8"))
                            for r in (_inv_data.get("results") or []):
                                _split_and_send._inv_map_for_sheet2[r["ticker"]] = {
                                    "score": r["score"], "verdict": r["verdict"]
                                }
                    except Exception:
                        pass
                    _split_and_send._inv_loaded = True
                _inv_s2 = _split_and_send._inv_map_for_sheet2.get(tk, {})
                inv_v_score = _inv_s2.get("score")
                inv_v_verdict = _inv_s2.get("verdict", "")

                # Classify Priority + derive decision fields for History too
                _row_status = row[c_st-1].value
                _row_entry = row[c_entry-1].value if c_entry else None
                _row_current = row[c_current-1].value if c_current else None
                _pnl_pct_hist = None
                if isinstance(_row_entry, (int, float)) and _row_entry > 0 \
                        and isinstance(_row_current, (int, float)):
                    _pnl_pct_hist = (_row_current - _row_entry) / _row_entry * 100

                def _hist_classify(st, iv, pnl, is_same_day=False, alerts=""):
                    q_high = iv in ("🏆 QUALITY", "✓ OK")
                    q_mid = iv == "⚠ MARGINAL"
                    q_low = iv == "✗ AVOID"
                    pnl_neg = isinstance(pnl, (int, float)) and pnl < 0
                    if st == "ROTATED_SAMEDAY": return "J"
                    if st == "EXIT" and is_same_day: return "J"
                    # 2026-08-14 Sprint K Part 28 · Risk Controller veto for History
                    # rows too · same rule as _classify_priority.
                    _alerts_up = str(alerts or "").upper()
                    for _sig in BINDING_RISK_SIGNALS:
                        if _sig in _alerts_up:
                            return "R"
                    if st == "EXIT":
                        return "H" if q_high else "I"
                    if st == "STRONG BUY" and iv == "🏆 QUALITY": return "A"
                    if st in ("BUY", "STRONG BUY") and q_high: return "B"
                    if st in ("BUY", "STRONG BUY") and q_low: return "F"
                    if st == "HOLD" and q_high and pnl_neg: return "C"
                    if st == "HOLD" and q_high: return "D"
                    if q_mid: return "E"
                    if q_low and pnl_neg: return "G"
                    if q_low: return "F"
                    return "E"

                # 2026-08-14 · same-day detection · source has NO "Exit Date"
                # column · derive from row Date when Status==EXIT (matches
                # main-loop convention). Fixes the same phantom-column bug
                # as the KPI aggregator hotfix.
                _hist_ed = str(row[c_date-1].value or "")[:10] if (_row_status == "EXIT" and c_date) else ""
                _hist_same_day = bool(_hist_ed and entry_dt and _hist_ed == entry_dt[:10])
                # Read alerts for History rows so Risk Controller veto also
                # fires here (Sprint K Part 28).
                _hist_alerts = row[c_alerts-1].value if c_alerts else ""
                hist_bucket = _hist_classify(_row_status, inv_v_verdict, _pnl_pct_hist,
                                                                 is_same_day=_hist_same_day,
                                                                 alerts=_hist_alerts)
                _matrix_h = PRIORITY_MATRIX.get(hist_bucket,
                                                                ("—", "—", "—", "—", "F2F2F2"))
                h_urg, h_rea, h_act, h_rev, _ = _matrix_h
                h_decision, _ = _resolve_decision(h_act, inv_v_verdict, _row_status)
                # 2026-08-14 · Sprint K Part 28 · apply same Decision overrides
                # as the Portfolio-sheet path so both sheets tell the same story.
                if hist_bucket == "R":
                    _au = str(_hist_alerts or "").upper()
                    _sig = next((s for s in BINDING_RISK_SIGNALS if s in _au), "HARD STOP")
                    h_decision = f"🔴 EXIT · {_sig.replace('_',' ').title()} · IMMEDIATE"
                elif hist_bucket == "J":
                    h_decision = "⚪ ARTIFACT · not held"
                elif hist_bucket in ("I", "H"):
                    h_decision = "🔴 EXIT"      # 2026-08-20 · one-word · CLOSED collapsed

                # Write 12 appended columns (positions from END)
                # Compute Execution Layer for History rows too
                h_stop = row[c_stop-1].value if c_stop else None
                h_t1 = row[c_t1-1].value if c_t1 else None
                h_price_trig = _price_trigger(h_act, h_stop, h_t1, _row_current)
                h_next_rev = _next_review_date(h_rev, str(row[c_date-1].value or "")[:10]) \
                                     if h_act not in ("CLOSED", "IGNORE") else ""
                h_exec_win = _execution_window(h_act)

                ws2.cell(r_idx, len(new_h) - 11, _cap_size(tk, mkt_key))
                row_dt = str(row[c_date-1].value or "")[:10]
                entry_dt = str(row[c_recommended-1].value or "")[:10] if c_recommended else ""
                # 2026-08-15 · Section 12 · Opportunity Status vocabulary
                # NEW      · row_dt == entry_dt (genuine first appearance)
                # EXISTING · row_dt > entry_dt (position rolled forward)
                # RE-ENTRY · derived from position_store exited history
                # (RE-ENTRY detection deferred to next wave · needs exit-set
                # cross-check per row · current NEW/EXISTING is the P0 fix.)
                if row_dt and entry_dt and row_dt == entry_dt:
                    opp_age = "🆕 NEW"
                elif row_dt and entry_dt and row_dt > entry_dt:
                    opp_age = "EXISTING"
                else:
                    opp_age = "EXISTING"   # fallback · no first-day distinction
                ws2.cell(r_idx, len(new_h) - 10, opp_age)
                ws2.cell(r_idx, len(new_h) - 9, inv_v_score)
                ws2.cell(r_idx, len(new_h) - 8, inv_v_verdict)
                ws2.cell(r_idx, len(new_h) - 7, h_decision)
                ws2.cell(r_idx, len(new_h) - 6, h_urg)
                ws2.cell(r_idx, len(new_h) - 5, h_rea)
                ws2.cell(r_idx, len(new_h) - 4, h_act)
                ws2.cell(r_idx, len(new_h) - 3, h_rev)
                ws2.cell(r_idx, len(new_h) - 2, h_price_trig)
                ws2.cell(r_idx, len(new_h) - 1, h_next_rev)
                ws2.cell(r_idx, len(new_h), h_exec_win)
                if status in _STATUS_FILLS_LOCAL:
                    fill = _STATUS_FILLS_LOCAL[status]
                    for c in range(1, len(new_h)+1):
                        ws2.cell(r_idx, c).fill = fill
            ws2.freeze_panes = "D2"

            # ═══════════════════════════════════════════════════════════════
            # SHEET 1 · PORTFOLIO GLANCE · operator directive: current XLSX is
            # a transaction log · unusable for P&L glance. Add a top sheet
            # with aggregates + one row per CURRENT position.
            # ═══════════════════════════════════════════════════════════════
            portfolio_ws = wb2.create_sheet("Portfolio", 0)
            # Build one row per unique (Ticker, Run_Type) using LATEST date state
            c_run = 4    # Run_Type is column 4 in the source
            latest_by_ticker = {}
            for r in keep_rows:
                key = (r[c_tk-1].value, str(r[c_run-1].value or ""))
                dt = str(r[c_date-1].value or "")[:10]
                if key not in latest_by_ticker or dt > latest_by_ticker[key][0]:
                    latest_by_ticker[key] = (dt, r)
            positions = [(dt, r) for (dt, r) in latest_by_ticker.values()]

            # 2026-08-12 CEO fix · P0-3 exclude ARTIFACTS from open/closed
            # counts + P1-5 formal P&L / win-rate definitions.
            #
            # Formal definitions (this is the SSoT for the caption + KPI band):
            #   Position P&L (%)         = per-position price change (unweighted)
            #   Realized P&L (sum)       = SUM of Exit P&L across CLOSED trades
            #                              (excludes ARTIFACT · excludes ROTATED_SAMEDAY)
            #   Unrealized P&L (sum)     = SUM of live P&L across ACTIVE positions
            #                              (excludes ARTIFACT · excludes ROTATED_SAMEDAY)
            #   Combined                 = Realized + Unrealized (sum of position %s,
            #                              NOT portfolio-weighted return · see caveat)
            #   Win rate                 = WINS / (WINS + LOSSES)
            #     where WIN = pnl > +0.01% · LOSS = pnl < -0.01% · FLAT = else
            #     ARTIFACT + ROTATED_SAMEDAY are EXCLUDED from all counters.
            # NOTE · a portfolio-weighted return would need per-position sizing
            # which we do not yet emit into the sheet. TODO after Sprint L.
            realized_sum = 0.0; n_realized = 0
            unrealized_sum = 0.0; n_unrealized = 0
            n_win = 0; n_loss = 0; n_flat = 0
            n_artifact = 0
            best_pos = ("", 0.0); worst_pos = ("", 0.0)
            # 2026-08-13 CEO bug fix · previous code used h.index("Recommended Date")
            # and h.index("Exit Date") which don't exist in source header
            # (real column is "Recommended" · there is no "Exit Date" column
            # at all · exit_date is derived on the fly from Date+Status).
            # Result: _row_is_artifact was always False · KPI showed
            # "0 same-day rotations" even when ~23 rows had ARTIFACT decisions.
            _c_rec_date = h.index("Recommended") + 1 if h and "Recommended" in h else None
            _c_date     = c_date   # row date · used as exit_date when status==EXIT
            for dt, r in positions:
                status = r[c_st-1].value
                # ARTIFACT detection · same rule as Priority J:
                #   status == ROTATED_SAMEDAY
                #   OR (status == EXIT AND row Date == Recommended date) · same-day rotation
                _entry_dt = r[_c_rec_date-1].value if _c_rec_date else None
                _exit_dt  = r[_c_date-1].value if (status == "EXIT" and _c_date) else None
                _row_is_artifact = (
                    status == "ROTATED_SAMEDAY"
                    or (_entry_dt and _exit_dt and str(_entry_dt)[:10] == str(_exit_dt)[:10])
                )
                if _row_is_artifact:
                    n_artifact += 1
                    continue   # do NOT contribute to open/closed/win-rate stats

                pnl = None
                if status == "EXIT" and c_exit_pnl:
                    v = r[c_exit_pnl-1].value
                    if isinstance(v, (int, float)):
                        pnl = v; realized_sum += v; n_realized += 1
                elif status != "EXIT":
                    entry_v = r[c_entry-1].value if c_entry else None
                    tk = r[c_tk-1].value
                    live = _parquet_close(tk, mkt_key, dt)
                    if live and isinstance(entry_v, (int, float)) and entry_v > 0:
                        pnl = round((live - entry_v) / entry_v * 100, 2)
                        unrealized_sum += pnl; n_unrealized += 1
                if pnl is not None:
                    if pnl > 0.01: n_win += 1
                    elif pnl < -0.01: n_loss += 1
                    else: n_flat += 1
                    if pnl > best_pos[1]: best_pos = (r[c_tk-1].value, pnl)
                    if pnl < worst_pos[1]: worst_pos = (r[c_tk-1].value, pnl)
            combined = realized_sum + unrealized_sum
            n_total = n_realized + n_unrealized
            # Win rate denominator excludes flats (per formal definition above)
            _win_denom = max(1, n_win + n_loss)
            win_rate = round(n_win / _win_denom * 100, 1)

            # Portfolio header + KPI banner
            portfolio_ws.merge_cells("A1:L1")
            portfolio_ws["A1"] = f"AEGIS {mkt_key} PORTFOLIO · as of {latest_date or 'today'}"
            portfolio_ws["A1"].font = _Font(bold=True, size=14, color="FFFFFF")
            portfolio_ws["A1"].fill = HEADER_FILL if 'HEADER_FILL' in globals() else _PF(
                start_color="1F4E78", end_color="1F4E78", fill_type="solid")
            portfolio_ws["A1"].alignment = _Align(horizontal="center", vertical="center")
            portfolio_ws.row_dimensions[1].height = 28

            # 2026-08-12 P0-3 · KPI banner now shows ARTIFACTS on their own row.
            # 2026-08-15 Section 6 · P&L 3-way separation:
            #   A. Realized P&L    · closed positions · entry → exit price
            #   B. Unrealized P&L  · active positions · entry → latest price
            #   C. Opportunity P&L · SKIP candidates  · TRACKED SEPARATELY in
            #      reports/research/skip_candidates_{market}.jsonl · NEVER
            #      included in portfolio P&L (would corrupt actual returns).
            # 'closed'/'open' counts EXCLUDE artifacts + SKIP by definition.
            _skip_dataset = _ROOT / "reports" / "research" / f"skip_candidates_{mkt_key.lower()}.jsonl"
            _n_skip_tracked = 0
            if _skip_dataset.exists():
                try:
                    _n_skip_tracked = sum(1 for l in _skip_dataset.read_text(encoding="utf-8").splitlines() if l.strip())
                except Exception:
                    pass
            kpi_rows = [
                ["Realized P&L (closed)", realized_sum / 100.0, f"{n_realized} closed",
                 "Best position", f"{best_pos[0]} {best_pos[1]:+.2f}%"],
                ["Unrealized P&L (open)", unrealized_sum / 100.0, f"{n_unrealized} open",
                 "Worst position", f"{worst_pos[0]} {worst_pos[1]:+.2f}%"],
                ["COMBINED PORTFOLIO",    combined / 100.0,      f"{n_total} real positions",
                 "Win rate", f"{win_rate}% ({n_win}W / {n_loss}L · {n_flat} flat excluded)"],
                ["Artifacts (excluded)",  "",                    f"{n_artifact} same-day rotations",
                 "Note", "not counted in P&L / win rate"],
                ["Opportunity dataset",   "",                    f"{_n_skip_tracked} SKIP candidates tracked",
                 "Location", "reports/research/skip_candidates_*.jsonl · never in portfolio"],
            ]
            for r_off, kpi_row in enumerate(kpi_rows, start=3):
                for c_off, val in enumerate(kpi_row, start=1):
                    cell = portfolio_ws.cell(r_off, c_off, val)
                    cell.font = _Font(bold=(c_off in (1, 4)), size=11)
                    # Column 2 = numeric P&L · display as %
                    if c_off == 2:
                        cell.number_format = "+0.00%;-0.00%;0.00%"
                    if r_off == 5 and c_off <= 3:   # combined row highlighted
                        cell.fill = _PF(start_color="FFE699", end_color="FFE699", fill_type="solid")

            # 2026-08-14 · operator-approved 6-tier color legend rows.
            # Placed between KPI banner (rows 3-6) and position table.
            # Legend heading at row 8 · one row per tier at rows 9-14.
            _LEGEND_HEADING_ROW = 8
            portfolio_ws.merge_cells(f"A{_LEGEND_HEADING_ROW}:L{_LEGEND_HEADING_ROW}")
            _lh = portfolio_ws.cell(_LEGEND_HEADING_ROW, 1, TIER_LEGEND_HEADING)
            _lh.font = _Font(bold=True, size=11, color="1F4E78")
            _lh.alignment = _Align(horizontal="left", vertical="center")
            _legend_start = _LEGEND_HEADING_ROW + 1
            # Iterate tiers in tier_rank order (1..N)
            _legend_ordered = sorted(
                [(k, v) for k, v in DECISION_TIERS.items()],
                key=lambda kv: int(kv[1].get("tier_rank") or 99))
            for _leg_idx, (_tier_key, _tier_def) in enumerate(_legend_ordered):
                _lr = _legend_start + _leg_idx
                _label = str(_tier_def.get("label") or _tier_key)
                _desc  = str(_tier_def.get("description") or "")
                _hf    = str(_tier_def.get("hex_fill") or "F2F2F2")
                _ht    = str(_tier_def.get("hex_text") or "000000")
                _bold  = bool(_tier_def.get("bold"))
                # Left cell = colored label swatch
                _swatch = portfolio_ws.cell(_lr, 1, _label)
                _swatch.fill = _PF(start_color=_hf, end_color=_hf, fill_type="solid")
                _swatch.font = _Font(bold=True, color=_ht, size=10)
                _swatch.alignment = _Align(horizontal="center", vertical="center")
                # Right cells (merged) = description
                portfolio_ws.merge_cells(start_row=_lr, start_column=2,
                                                       end_row=_lr, end_column=6)
                _dc = portfolio_ws.cell(_lr, 2, _desc)
                _dc.font = _Font(size=10)
                _dc.alignment = _Align(horizontal="left", vertical="center", wrap_text=True)
            # Track where the position header goes (row after legend + 1 blank)
            _pos_header_row = _legend_start + len(_legend_ordered) + 1

            # 2026-08-10 · CEO review fixes (semantic separation):
            #   1. Lifecycle column · NEW/ACTIVE/CLOSED (separate from Runner Status)
            #      Rule: EXITED only when Runner=EXIT AND Portfolio agrees (Priority I)
            #      If Priority=H (Premature Exit?) · Lifecycle=ACTIVE (portfolio challenging)
            #   2. R1/R2 Consensus column · AGREE/SPLIT/R1-only/R2-only
            #   3. Next Review = Recommended Date + horizon (stable · not sliding)
            pos_hdr = [
                # IDENTITY (3) · Lifecycle sits with identity now
                "Ticker", "🎯 DECISION", "Lifecycle",
                # EXECUTION LAYER (3)
                "Price Trigger", "Next Review", "Execution Window",
                # META (7)
                "Runner", "R1/R2 Consensus", "Sector", "Cap", "Entry Date", "Exit Date", "Days",
                # SUPPORTING DECISION FIELDS (7)
                "Urgency", "Reason", "Action", "Review",
                "Status", "Inv Quality", "Investability",
                # PRICE + P&L (4)
                "Entry", "Current", "Exit Price", "P&L %",
                # RISK/TARGET (3)
                "Stop Loss", "Target 1", "Target 2",
                # CONTEXT (3)
                "Action Note", "Alerts", "Exit Reason",
                # 2026-08-14 Sprint K Part 28 · Wave 4 · Post-Exit Assessment
                # is analytical / research-only · NEVER a live trading
                # instruction. Live Decision column stays clean (BUY/HOLD/
                # PROTECT/EXIT/CLOSED).
                "Post-Exit Assessment",
                # 2026-08-15 · Section 13 · Decision Basis · one short reason
                # explaining WHY the Decision was reached. Deterministic ·
                # derived from lifecycle + risk + status.
                "Decision Basis",
            ]
            widths_pos = [12, 24, 12,
                              22, 12, 30,
                              8, 14, 22, 20, 12, 12, 8,
                              12, 20, 16, 14, 12, 14, 12,
                              12, 12, 12, 10,
                              12, 12, 12,
                              40, 40, 30,
                              32,
                              22]   # Decision Basis

            # R1/R2 consensus map · build from all keep_rows (before ticker loop)
            # (populated after keep_rows filter · so put function here · use later)
            _by_ticker_runners = {}
            for _r in keep_rows:
                _tk = _r[c_tk-1].value
                _rn = _r[3].value if len(_r) > 3 else None
                if _tk and _rn:
                    _by_ticker_runners.setdefault(_tk, set()).add(str(_rn))
            def _consensus(tk, this_runner):
                runners = _by_ticker_runners.get(tk, set())
                if len(runners) == 1:
                    return f"🔹 {this_runner} ONLY"
                return "✅ AGREE"  # both present · could compare actions later

            # PRIORITY_MATRIX + DECISION vocab + EXEC layer already loaded at top of _split_and_send

            # Load Investability scores (advisory · from reports/investability_{market}.json)
            _inv_map = {}
            try:
                _inv_path = _ROOT / "reports" / f"investability_{mkt_key.lower()}.json"
                if _inv_path.exists():
                    import json as _json
                    _inv_data = _json.loads(_inv_path.read_text(encoding="utf-8"))
                    for r in (_inv_data.get("results") or []):
                        _inv_map[r["ticker"]] = {"score": r["score"], "verdict": r["verdict"]}
            except Exception as _e:
                print(f"[investability] load failed: {_e}")
            # 2026-08-14 · position header row anchored to _pos_header_row
            # (was hardcoded row 7 · now shifts down to accommodate legend).
            for c, name in enumerate(pos_hdr, start=1):
                cell = portfolio_ws.cell(_pos_header_row, c, name)
                cell.font = _Font(bold=True, color="FFFFFF", size=11)
                cell.fill = HEADER_FILL if 'HEADER_FILL' in globals() else _PF(
                    start_color="1F4E78", end_color="1F4E78", fill_type="solid")
                cell.alignment = _Align(horizontal="center", vertical="center")
                portfolio_ws.column_dimensions[_gcl_src(c)].width = widths_pos[c-1]

            # 2026-08-18 · Wave 3 · Section 15 · slim client-facing view.
            # Operator wants ~15 essential columns visible · not 32.
            # Hide internal-audit columns in Excel (preserved in file for
            # research/audit consumers · just not shown by default). Excel
            # 'Unhide' reveals them if operator ever needs the full view.
            _HIDDEN_COL_NAMES = {
                "Price Trigger",        # 4  · redundant with Stop Loss + Target
                "Execution Window",     # 6
                "R1/R2 Consensus",      # 8
                "Exit Date",            # 12 · only meaningful for closed rows
                "Action",               # 16 · Decision (col 2) is operator-facing
                "Review",               # 17
                "Inv Quality",          # 19 · internal
                "Investability",        # 20 · internal score
                "Exit Price",           # 23 · only for closed
                "Action Note",          # 28
                "Alerts",               # 29 · internal (Risk Controller reads this)
                "Exit Reason",          # 30 · only for closed
                "Post-Exit Assessment", # 31 · analytical / research only
                "Decision Basis",       # 32 · analytical / research only
            }
            for c, name in enumerate(pos_hdr, start=1):
                if name in _HIDDEN_COL_NAMES:
                    portfolio_ws.column_dimensions[_gcl_src(c)].hidden = True

            # 2026-08-14 operator-approved · sort by decision-TIER (not
            # priority bucket). Same tier logic used for row color · classifier
            # walks match_order in configs/decision_colors.yaml.
            #
            # Tier ordering (top → bottom):
            #   1 strong_buy  Deep Green
            #   2 buy         Light Green
            #   3 new         Purple  (is_new_position=True)
            #   4 hold        Yellow
            #   5 exit        Light Red
            #   6 closed      Dark Red
            def _sort_key(item):
                dt, r = item
                status = r[c_st-1].value
                # Same-day rotation detection (matches KPI aggregator)
                _e_dt = r[_c_rec_date-1].value if _c_rec_date else None
                _x_dt = r[_c_date-1].value if (status == "EXIT" and _c_date) else None
                is_artifact = (
                    status == "ROTATED_SAMEDAY"
                    or (_e_dt and _x_dt and str(_e_dt)[:10] == str(_x_dt)[:10])
                )
                # P&L for within-tier sorting (best first)
                pnl = 0
                if status == "EXIT" and c_exit_pnl:
                    v = r[c_exit_pnl-1].value
                    if isinstance(v, (int, float)): pnl = v
                else:
                    entry_v = r[c_entry-1].value if c_entry else None
                    tk = r[c_tk-1].value
                    live = _parquet_close(tk, mkt_key, dt)
                    if live and isinstance(entry_v, (int, float)) and entry_v > 0:
                        pnl = round((live - entry_v) / entry_v * 100, 2)
                # ── Reproduce decision-tier from row data (mirrors write-loop) ──
                # Alerts col for risk-veto detection
                alerts_here = str(r[c_alerts-1].value if c_alerts else "").upper()
                # is_new_position · rec_dt == asof AND not an artifact/exit
                is_new = bool(_e_dt) and str(_e_dt)[:10] == str(asof)[:10] \
                             and status != "EXIT" and not is_artifact
                # Pre-classify tier without needing full decision_text · use
                # the same precedence rules as the write loop.
                if is_artifact:
                    tier = "closed"
                elif any(sig in alerts_here for sig in BINDING_RISK_SIGNALS):
                    tier = "exit"
                elif status == "EXIT":
                    tier = "closed"
                elif is_new:
                    tier = "new"
                elif status == "STRONG BUY":
                    tier = "strong_buy"
                elif status in ("BUY", "ACCUMULATE"):
                    tier = "buy"
                elif status in ("SELL", "REDUCE"):
                    tier = "exit"
                else:
                    tier = "hold"
                tier_rank = int((DECISION_TIERS.get(tier) or {}).get("tier_rank") or 99)
                # Within tier: best P&L first (descending)
                return (tier_rank, -pnl)

            positions_sorted = sorted(positions, key=_sort_key)

            # 2026-08-18 · Wave 3 · Section 17 · INDIGO filter.
            # Drop rows whose (mkt, runner, ticker) has a REJECTED opportunity
            # in the registry with created_date == this row's row_date. Those
            # are same-day close/rotation artifacts · must never appear in the
            # active Portfolio (would confuse operator with 'NEW + CLOSED').
            _rejected_row_keys: set = set()
            try:
                from backend.research import opportunity_registry as _oreg
                _reg = _oreg.load_all(_ROOT)
                for _opps in _reg.values():
                    for _o in _opps:
                        if _o.status == "REJECTED":
                            _rejected_row_keys.add(
                                (_o.market.lower(), _o.runner.upper(),
                                  _o.ticker.upper(), _o.created_date[:10]))
            except Exception:
                pass
            if _rejected_row_keys:
                _before_flt = len(positions_sorted)
                _kept = []
                for _item in positions_sorted:
                    _dt, _r = _item
                    _tk = str(_r[c_tk-1].value or "").upper().replace(".NS","").replace(".BO","")
                    _rn = str(_r[3].value or "").upper().replace("_NEW","")
                    _rd = str(_r[c_recommended-1].value or "")[:10] if c_recommended else ""
                    if (mkt_key.lower(), _rn, _tk, _rd) in _rejected_row_keys:
                        continue    # drop INDIGO-style rejected same-day row
                    _kept.append(_item)
                positions_sorted = _kept
                if len(positions_sorted) < _before_flt:
                    print(f"[xlsx:{mkt_key}] INDIGO filter · dropped "
                          f"{_before_flt - len(positions_sorted)} REJECTED same-day rows")

            # 2026-08-18 · Wave 3 · Section 17 · 3-section banner rows.
            # Group positions by section · order them as a flat list where
            # section transitions inject a banner-row placeholder. The write
            # loop below emits banners inline when it encounters one.
            _SECTION_ORDER = [
                ("new_opps",  "🆕 NEW OPPORTUNITIES TODAY",     "B4C7E7", "000000"),
                ("existing",  "📊 EXISTING POSITIONS",         "E2EFDA", "000000"),
                ("action",    "⚠️  ACTION REQUIRED · EXITS",   "FCE4D6", "9C0006"),
                ("closed",    "🔴 EXIT · REFERENCE ONLY",    "D9D9D9", "9C0006"),
            ]
            def _row_section(_item):
                _dt, _r = _item
                _st = str(_r[c_st-1].value or "").upper()
                _al = str(_r[c_alerts-1].value if c_alerts else "").upper()
                _rd = str(_r[c_recommended-1].value or "")[:10] if c_recommended else ""
                _same_day = _rd == asof[:10] and _st != "EXIT"
                if any(sig in _al for sig in BINDING_RISK_SIGNALS): return "action"
                if _st == "EXIT": return "closed"
                if _same_day: return "new_opps"
                return "existing"

            # Reorder positions_sorted by (section, existing sort) so
            # rows for each section are contiguous. Keeps within-section
            # ordering (P&L desc within tier).
            _by_section: dict = {k: [] for k, *_ in _SECTION_ORDER}
            for _item in positions_sorted:
                _by_section.setdefault(_row_section(_item), []).append(_item)
            positions_sorted = []
            _banner_row_indexes: dict = {}   # {row_index: (banner_text, fill_hex, text_hex)}
            _cursor = _pos_header_row + 1
            for _sect_key, _banner_text, _fill_hex, _text_hex in _SECTION_ORDER:
                _rr = _by_section.get(_sect_key) or []
                if not _rr: continue
                _banner_row_indexes[_cursor] = (_banner_text, _fill_hex, _text_hex)
                _cursor += 1               # reserve banner row
                for _r in _rr:
                    positions_sorted.append(_r)
                    _cursor += 1

            # Emit banners now (write loop uses assigned row indexes).
            for _br, (_txt, _fill, _tc) in _banner_row_indexes.items():
                portfolio_ws.merge_cells(start_row=_br, start_column=1,
                                                          end_row=_br, end_column=len(pos_hdr))
                _bc = portfolio_ws.cell(_br, 1, _txt)
                _bc.font = _Font(bold=True, size=12, color=_tc)
                _bc.fill = _PF(start_color=_fill, end_color=_fill, fill_type="solid")
                _bc.alignment = _Align(horizontal="center", vertical="center")
                portfolio_ws.row_dimensions[_br].height = 20

            # Build (target_row_index, item) pairs so the write loop uses
            # row indices that skip past banner rows.
            _row_indexes = [r for r in range(_pos_header_row + 1, _cursor)
                                    if r not in _banner_row_indexes]
            for i, (dt, r) in zip(_row_indexes, positions_sorted):
                # (loop body below is the original write logic)
                # First iteration variable unpacking · pass through
                tk = r[c_tk-1].value
                status = r[c_st-1].value
                entry_v = r[c_entry-1].value if c_entry else None
                rec_dt = str(r[c_recommended-1].value or "")[:10] if c_recommended else ""
                # Compute P&L
                if status == "EXIT":
                    pnl = r[c_exit_pnl-1].value if c_exit_pnl else None
                    curr = r[c_current-1].value if c_current else None
                else:
                    live = _parquet_close(tk, mkt_key, dt)
                    curr = round(live, 2) if live else (r[c_current-1].value if c_current else None)
                    pnl = round((live - entry_v) / entry_v * 100, 2) \
                            if live and isinstance(entry_v, (int, float)) and entry_v > 0 else None
                # Days held
                try:
                    from datetime import date as _dtc
                    d1 = _dtc.fromisoformat(rec_dt); d2 = _dtc.fromisoformat(dt)
                    days = max(0, (d2 - d1).days)
                except Exception:
                    days = ""
                alerts = r[c_alerts-1].value if c_alerts else ""
                exit_reason = ""
                # Row values · P&L stored as decimal (0.0384) so Excel SUM works
                pnl_decimal = pnl / 100.0 if isinstance(pnl, (int, float)) else None
                runner_val = r[c_run - 1].value if c_run else ""
                # Exit Price / Exit Date only for EXIT rows · Stop/T1/T2 only for open
                exit_price = curr if status == "EXIT" else None
                exit_date  = dt if status == "EXIT" else None
                stop_v = r[c_stop - 1].value if (c_stop and status != "EXIT") else None
                t1_v   = r[c_t1 - 1].value   if (c_t1   and status != "EXIT") else None
                t2_v   = r[c_t2 - 1].value   if (c_t2   and status != "EXIT") else None
                if status == "EXIT" and h and "Exit Reason" in h:
                    exit_reason = r[h.index("Exit Reason")].value or ""
                # Investability lookup (Wave 2 · 11 sub-engines)
                _inv = _inv_map.get(tk, {})
                inv_score = _inv.get("score")
                inv_verdict = _inv.get("verdict", "")
                # 2026-08-12 P1-4 · CEO fix · when Investability hasn't been
                # computed yet for a NEW recommendation, substitute PENDING
                # instead of empty string (previously showed as NaN and the
                # Decision layer defaulted to PROTECT which is contradictory
                # for a same-day STRONG BUY like ZYDUSLIFE +6.43%).
                if not inv_verdict:
                    inv_verdict = "⏳ PENDING"

                # 2026-08-12 P0-1 · CEO fix · lifecycle-first detection.
                # These flags feed BOTH _classify_priority and _resolve_decision
                # so ARTIFACT/EXIT/NEW/ACTIVE state precedes generic protective
                # rules. Previously a same-day STRONG BUY (+6.43%) got PROTECT
                # because the decision layer ran trailing-stop logic without
                # asking "is this even a held position yet?".
                # `asof` is the run date; rec_dt is when the position was first
                # recommended. Same day => NEW position, day-0 rules apply.
                _is_new_position = bool(rec_dt) and str(rec_dt)[:10] == str(asof)[:10]
                # ARTIFACT detected inline below via is_same_day check.

                def _classify_priority(st, iv, pnl, is_same_day=False, alerts=""):
                    """Returns bucket letter · R (Risk Veto) OR A-J (existing).

                    2026-08-14 · Sprint K Part 28 · Risk Controller has veto.
                    Any binding risk signal in Alerts (STOP_LOSS_HIT · HARD_STOP ·
                    TRAILING_STOP_HIT · GAP_EXIT · PORTFOLIO_MAX_DD · EMERGENCY_EXIT ·
                    CRITICAL_DEEP_LOSS) forces bucket R regardless of Status +
                    Investability. Same-day rotations are still J even if a stop
                    also fired (rotation semantic wins for that pathological case).

                    2026-08-10 · same-day EXIT (Entry Date == Exit Date) reclassified
                    as J (ARTIFACT) instead of I (CLOSED) · not a real trade.
                    """
                    q_high = iv in ("🏆 QUALITY", "✓ OK")
                    q_mid = iv == "⚠ MARGINAL"
                    q_low = iv == "✗ AVOID"
                    pnl_neg = isinstance(pnl, (int, float)) and pnl < 0
                    # ── Risk Controller veto (Sprint K Part 28) ──
                    # Same-day ARTIFACT wins over R (never-held rotation is not
                    # a real position that could be stopped-out).
                    if st == "ROTATED_SAMEDAY": return "J"
                    if st == "EXIT" and is_same_day: return "J"
                    _alerts_up = str(alerts or "").upper()
                    for _sig in BINDING_RISK_SIGNALS:
                        if _sig in _alerts_up:
                            return "R"
                    # ── existing rules ──
                    if st == "EXIT":
                        return "H" if q_high else "I"
                    if st == "STRONG BUY" and iv == "🏆 QUALITY": return "A"
                    if st in ("BUY", "STRONG BUY") and q_high:    return "B"
                    if st in ("BUY", "STRONG BUY") and q_low:     return "F"
                    if st == "HOLD" and q_high and pnl_neg:       return "C"
                    if st == "HOLD" and q_high:                   return "D"
                    if q_mid:                                      return "E"
                    if q_low and pnl_neg:                         return "G"
                    if q_low:                                      return "F"
                    return "E"

                # Compute P&L for classification
                _pnl_for_class = None
                if isinstance(pnl_decimal, (int, float)):
                    _pnl_for_class = pnl_decimal * 100

                # Same-day detection · Entry Date == Exit Date == today = rotation artifact
                _is_same_day = bool(exit_date and rec_dt and str(exit_date)[:10] == rec_dt[:10])
                # 2026-08-14 Sprint K Part 28 · pass Alerts so Risk Controller
                # veto can force bucket R when STOP_LOSS_HIT etc. present.
                priority_bucket = _classify_priority(status, inv_verdict, _pnl_for_class,
                                                                        is_same_day=_is_same_day,
                                                                        alerts=alerts)
                _matrix = PRIORITY_MATRIX.get(priority_bucket,
                                                            ("—", "—", "—", "—", "F2F2F2"))
                priority_tag = priority_bucket   # for color lookup below
                urgency, reason, action, review, _color = _matrix

                # Final Action · human-readable follow-through (kept for context)
                def _final_action(st, iv):
                    q_high = iv in ("🏆 QUALITY", "✓ OK")
                    q_low = iv == "✗ AVOID"
                    if st == "STRONG BUY":
                        if iv == "🏆 QUALITY": return "🟢🟢 STRONG BUY · high conviction"
                        if iv == "✓ OK":       return "🟢 BUY · engine + quality aligned"
                        if iv == "⚠ MARGINAL": return "🟡 BUY SMALL · quality borderline"
                        if q_low:               return "🔴 SKIP · engine buys but quality FAILS"
                    if st == "BUY":
                        if q_high:              return "🟢 BUY · in buy zone · quality confirmed"
                        if iv == "⚠ MARGINAL": return "🟡 BUY SMALL · watch quality"
                        if q_low:               return "🔴 SKIP · buy signal but quality WEAK"
                    if st == "HOLD":
                        if iv == "🏆 QUALITY": return "🟢 HOLD · patient · both endorse"
                        if iv == "✓ OK":       return "🟢 HOLD · quality intact"
                        if iv == "⚠ MARGINAL": return "🟡 HOLD · tighten stop · watching"
                        if q_low:               return "🔴 REDUCE / EXIT · quality degraded"
                    if st == "EXIT":
                        if q_high: return "⚪ EXITED · quality was good · review if premature"
                        return "⚪ EXITED · position closed"
                    if st == "ROTATED_SAMEDAY":
                        return "⚪ Rotation artifact · not held"
                    return "—"

                final_action = _final_action(status, inv_verdict)

                # DECISION · single human-facing synthesis (col 2)
                decision_text, decision_color_key = _resolve_decision(
                    action, inv_verdict, status)

                # 2026-08-14 CEO fix · Sprint K Part 28 · Risk Controller veto +
                # closed-position uniformity + NEW-state routing. Precedence
                # order (highest first · every check is a hard override):
                #
                #   R bucket (RISK VETO · Alerts contains STOP_LOSS_HIT etc.)
                #     -> Decision = 🔴 EXIT · <alert reason> · IMMEDIATE
                #     -> BINDING · overrides Status/Investability/lifecycle
                #   J bucket (ARTIFACT · same-day rotation · never held)
                #     -> Decision = ⚪ ARTIFACT · not held
                #   I OR H bucket (EXIT closed positions · runner exited)
                #     -> Decision = ⚪ CLOSED  (H was HOLD before · Sprint K Part 28)
                #     -> Any "Premature Exit?" analysis moves to Post-Exit Assessment (Wave 4)
                #   NEW position (rec_dt == asof, not EXIT, not artifact)
                #     -> P0-2 · use NEW-state logic, NOT trailing-stop/protect
                #        · QUALITY/OK   -> 🟢 BUY (validate entry)
                #        · MARGINAL     -> 🟡 WATCH · small size
                #        · AVOID        -> 🔴 SKIP · quality fails
                #        · PENDING      -> ⏳ PROVISIONAL BUY · investability not yet computed
                if priority_bucket == "R":
                    # Extract the specific binding-signal name for the decision text
                    _alerts_up = str(alerts or "").upper()
                    _hit_signal = next(
                        (s for s in BINDING_RISK_SIGNALS if s in _alerts_up),
                        "HARD STOP")
                    decision_text, decision_color_key = (
                        f"🔴 EXIT · {_hit_signal.replace('_',' ').title()} · IMMEDIATE",
                        "red")
                elif priority_bucket == "J":
                    # 2026-08-20 · one-word rule · ARTIFACT collapsed to EXIT
                    decision_text, decision_color_key = "🔴 EXIT · same-day rotation", "red"
                elif priority_bucket in ("I", "H"):
                    # 2026-08-20 · one-word rule · CLOSED collapsed to EXIT
                    decision_text, decision_color_key = "🔴 EXIT", "red"
                elif _is_new_position and status != "EXIT":
                    _iv_key = str(inv_verdict).strip()
                    if _iv_key in ("🏆 QUALITY", "✓ OK"):
                        decision_text, decision_color_key = "🟢 BUY · new position · quality confirmed", "green"
                    elif _iv_key == "⚠ MARGINAL":
                        decision_text, decision_color_key = "🟡 WATCH · new · small size only", "yellow"
                    elif _iv_key == "✗ AVOID":
                        decision_text, decision_color_key = "🔴 SKIP · new · quality fails", "red"
                    elif _iv_key == "⏳ PENDING":
                        decision_text, decision_color_key = "⏳ PROVISIONAL BUY · investability pending", "yellow"
                    # else: keep _resolve_decision result

                # 2026-08-10 CEO v6 · closed positions get BLANK actionable fields
                # (operator: "You don't want CLOSED · Next Review 15-Aug ·
                # Decision HOLD · nonsense")
                # 2026-08-14 · R (risk veto) is NOT terminal · needs execution today
                # (Price Trigger + Exec Window populated). I/H/J stay terminal.
                is_terminal = action in ("CLOSED", "IGNORE") or priority_bucket in ("I", "J", "H")
                price_trigger = "" if is_terminal else _price_trigger(action, stop_v, t1_v, curr)
                next_review_anchor = rec_dt if rec_dt else dt
                next_review = "" if is_terminal else _next_review_date(review, next_review_anchor)
                exec_window = "" if is_terminal else _execution_window(action)

                # 2026-08-10 CEO fix v6 · added REVIEWING state (explicit)
                # 4 lifecycle states operator can act on unambiguously:
                #   🆕 NEW        · first day of recommendation
                # 2026-08-20 · operator directive "exit or close one word is
                # enough · prefer exit default". Lifecycle vocab collapsed to:
                #   🆕 NEW     · first day of the opportunity (rec_dt == today)
                #   🟢 ACTIVE  · held (BUY/HOLD/PROTECT)
                #   🔴 EXIT    · closed / rotated / same-day artifact · anything
                #                terminal · one word covers I / H / J / R buckets
                # Also · terminal Decision (starts with EXIT/CLOSED/ARTIFACT)
                # FORCES Lifecycle=EXIT · fixes the NTPC/LICI/BATAINDIA case
                # where Decision was EXIT but Lifecycle stayed ACTIVE.
                _dec_up = str(decision_text or "").upper()
                _is_terminal_decision = (
                    priority_bucket in ("R", "I", "J", "H")
                    or _dec_up.startswith("🔴 EXIT") or "CLOSED" in _dec_up
                    or "ARTIFACT" in _dec_up
                )
                if _is_terminal_decision:
                    lifecycle = "🔴 EXIT"
                elif rec_dt and dt and rec_dt == dt:
                    lifecycle = "🆕 NEW"
                else:
                    lifecycle = "🟢 ACTIVE"

                # 2026-08-10 CEO fix #3: R1/R2 Consensus column
                consensus = _consensus(tk, runner_val)

                # 2026-08-14 Sprint K Part 28 · Wave 4 · Post-Exit Assessment.
                # Analytical / research-only classification of the CLOSE event.
                # Never a trading instruction. Live Decision column is separate.
                #   R bucket → Stop Loss Triggered · was <alert>
                #   H bucket → Premature Exit? · quality was intact
                #   I bucket → Clean Exit · quality had degraded
                #   J bucket → Same-Day Rotation · never held
                #   active   → blank
                _post_exit_assessment = ""
                if priority_bucket == "R":
                    _au = str(alerts or "").upper()
                    _sig = next((s for s in BINDING_RISK_SIGNALS if s in _au), "HARD_STOP")
                    _post_exit_assessment = f"Stop Loss Triggered · {_sig.replace('_',' ').title()}"
                    if isinstance(pnl_decimal, (int, float)):
                        _post_exit_assessment += f" @ {pnl_decimal*100:+.2f}%"
                elif priority_bucket == "H":
                    _post_exit_assessment = "Premature Exit? · quality intact at close"
                elif priority_bucket == "I":
                    _post_exit_assessment = "Clean Exit · quality had degraded"
                elif priority_bucket == "J":
                    _post_exit_assessment = "Same-Day Rotation · never held"

                # 2026-08-15 · Section 13 · Decision Basis · one short reason
                # explaining WHY. Deterministic derivation · matches the
                # priority classifier's decision chain.
                _au = str(alerts or "").upper()
                if priority_bucket == "R":
                    _sig = next((s for s in BINDING_RISK_SIGNALS if s in _au), "HARD STOP")
                    _decision_basis = f"STOP LOSS HIT · {_sig.replace('_',' ').title()}"
                elif priority_bucket == "J":
                    _decision_basis = "SAME-DAY ROTATION"
                elif priority_bucket in ("I", "H"):
                    _decision_basis = "MODEL EXIT · Runner closed"
                elif _is_new_position and status != "EXIT":
                    _decision_basis = "NEW OPPORTUNITY"
                elif str(inv_verdict or "").strip() == "✗ AVOID":
                    _decision_basis = "QUALITY FAILED"
                elif priority_bucket == "E":
                    _decision_basis = "PROTECT · watch"
                elif priority_bucket == "G":
                    _decision_basis = "RISK REDUCTION"
                elif status in ("STRONG BUY", "BUY"):
                    _decision_basis = "MODEL CONTINUES · buy signal"
                else:
                    _decision_basis = "MODEL CONTINUES"

                vals = [
                    # IDENTITY (1-3)
                    tk, decision_text, lifecycle,
                    # EXECUTION LAYER (4-6)
                    price_trigger, next_review, exec_window,
                    # META (7-13)
                    runner_val, consensus, _sector_for(tk, mkt_key), _cap_size(tk, mkt_key),
                    rec_dt, exit_date, days,
                    # DECISION SUPPORT (14-20)
                    urgency, reason, action, review,
                    status, inv_verdict, inv_score,
                    # PRICE + P&L (21-24)
                    entry_v, curr, exit_price, pnl_decimal,
                    # RISK/TARGET (25-27)
                    stop_v, t1_v, t2_v,
                    # CONTEXT (28-30)
                    _ACTIONS.get(status, ""), alerts or "", exit_reason,
                    # POST-EXIT ASSESSMENT (31)
                    _post_exit_assessment,
                    # DECISION BASIS (32)
                    _decision_basis,
                ]
                for c, v in enumerate(vals, start=1):
                    cell = portfolio_ws.cell(i, c, v)
                    text_cols = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 28, 29, 30, 31, 32}
                    cell.alignment = _Align(
                        horizontal="left" if c in text_cols else "right",
                        vertical="center", wrap_text=True)
                    # Number formats
                    if c == 13 and isinstance(days, int):       # Days
                        cell.number_format = "0"
                    elif c == 20 and isinstance(inv_score, (int, float)):  # Investability
                        cell.number_format = "0.0"
                    elif c in (21, 22, 23, 25, 26, 27):         # Entry/Curr/Exit/Stop/T1/T2
                        cell.number_format = "#,##0.00"
                    elif c == 24 and pnl_decimal is not None:   # P&L %
                        cell.number_format = "+0.00%;-0.00%;0.00%"

                # DECISION cell gets its own color (col 2) · overrides row fill
                _dec_hex = DECISION_COLORS.get(decision_color_key, "E7E6E6")
                portfolio_ws.cell(i, 2).fill = _PF(
                    start_color=_dec_hex, end_color=_dec_hex, fill_type="solid")
                portfolio_ws.cell(i, 2).font = _Font(bold=True, size=11)

                # 2026-08-14 · operator-approved 6-tier color scheme (msg 380 approved).
                # Row color = decision-TIER (from configs/decision_colors.yaml).
                # Config-driven · edit YAML → next CI cycle picks up.
                _row_tier = _decision_tier(decision_text, _is_new_position)
                _tier_def = DECISION_TIERS.get(_row_tier) or {}
                _tier_hex_fill = _tier_def.get("hex_fill") or "F2F2F2"
                _tier_hex_text = _tier_def.get("hex_text") or "000000"
                _tier_bold = bool(_tier_def.get("bold"))
                _row_fill = _PF(start_color=_tier_hex_fill, end_color=_tier_hex_fill, fill_type="solid")
                _row_font = _Font(color=_tier_hex_text, bold=_tier_bold)
                for c in range(1, len(pos_hdr) + 1):
                    _cell = portfolio_ws.cell(i, c)
                    _cell.fill = _row_fill
                    # Preserve DECISION cell's own bold-strong font (col 2)
                    if c != 2:
                        # Keep existing font (alignment / number format) but tint text
                        try:
                            _cell.font = _Font(color=_tier_hex_text, bold=_tier_bold,
                                                    size=_cell.font.size or 11)
                        except Exception:
                            _cell.font = _row_font
            portfolio_ws.freeze_panes = f"A{_pos_header_row + 1}"

            # Rename Sheet 2 · make Portfolio come first
            ws2.title = f"AEGIS {mkt_key} History"

            wb2.save(out_path)
            src_wb.close()
            # Skip send if market has 0 rows (e.g., USA freshly wiped for S&P 500 reset)
            if len(keep_rows) == 0:
                print(f"[xlsx:{mkt_key}] SKIPPED · 0 rows for market (fresh start · awaiting next pipeline run)")
                return True
            # Send
            # 2026-08-10 · operator: "simple note with date · why note so big"
            # Suppress heartbeat banner + Monday operator guide from Telegram
            # caption (kept in stdout logs · zero UI clutter for operator)
            full_caption = caption_body
            ok, msg = _send_document(token, chat_id, out_path, caption=full_caption)
            print(f"[xlsx:{mkt_key}] file={out_path.name} · rows={len(keep_rows)} · sent={ok}")
            if not ok:
                print(f"  detail: {msg[:180]}")
            return ok

        # Import Font at module scope (used in split_and_send)
        from openpyxl.styles import Font as _Font
        from openpyxl.styles import Alignment as _Align

        # 2026-08-10 · operator directive · "why note is so big · simple note
        # with date in note like yesterday" · stripped captions to bare date
        india_caption = f"📊 AEGIS India · {asof}"
        usa_caption   = f"📊 AEGIS USA · {asof}"

        xlsx_ok = True
        if "india" in markets:
            xlsx_ok &= _split_and_send("India", "INDIA", india_caption)
        if "usa" in markets:
            xlsx_ok &= _split_and_send("USA",   "USA",   usa_caption)
        # Guard 10 · Data Integrity audit (CEO 17-point checklist · 2026-08-10)
        # Runs AFTER the XLSX is written · audits Prev Close · Today Move · PnL
        # math · Recommended immutability · Entry Price immutability · Opp Age
        try:
            from backend.context.data_integrity_guard import (
                audit as _di_audit, emit as _di_emit, render_summary as _di_render)
            _di_paths = [
                _ROOT / "reports" / "telegram" / f"aegis_history_{m}.xlsx" for m in markets
            ]
            _di_result = _di_audit(_ROOT, _di_paths)
            _di_emit(_ROOT, _di_result)
            print(f"[guard10:integrity] {_di_render(_di_result)}")
            if _di_result.get("verdict") == "RED":
                print(f"[guard10:integrity] 🔴 {_di_result['n_issues']} integrity issues detected · investigation needed")
                for i in _di_result.get("issues", [])[:5]:
                    print(f"    ✗ {i.get('type')}: {i.get('ticker')} {i.get('date','')}")
        except Exception as _e:
            print(f"[guard10:integrity] check failed · {type(_e).__name__}: {_e}")

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
