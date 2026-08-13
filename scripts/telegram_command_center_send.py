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

                def _hist_classify(st, iv, pnl, is_same_day=False):
                    q_high = iv in ("🏆 QUALITY", "✓ OK")
                    q_mid = iv == "⚠ MARGINAL"
                    q_low = iv == "✗ AVOID"
                    pnl_neg = isinstance(pnl, (int, float)) and pnl < 0
                    if st == "ROTATED_SAMEDAY": return "J"
                    if st == "EXIT":
                        if is_same_day: return "J"
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

                # Same-day detection for History rows too
                _hist_exit_date_col = h.index("Exit Date")+1 if "Exit Date" in h else None
                _hist_ed = str(row[_hist_exit_date_col-1].value or "")[:10] if _hist_exit_date_col else ""
                _hist_same_day = bool(_hist_ed and entry_dt and _hist_ed == entry_dt[:10])
                hist_bucket = _hist_classify(_row_status, inv_v_verdict, _pnl_pct_hist,
                                                                 is_same_day=_hist_same_day)
                _matrix_h = PRIORITY_MATRIX.get(hist_bucket,
                                                                ("—", "—", "—", "—", "F2F2F2"))
                h_urg, h_rea, h_act, h_rev, _ = _matrix_h
                h_decision, _ = _resolve_decision(h_act, inv_v_verdict, _row_status)

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
                opp_age = "🆕 NEW" if (row_dt and row_dt == entry_dt) else "OLD"
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

            # Aggregate: sum realized (EXIT rows) + unrealized (open rows) using repaired numbers
            realized_sum = 0.0; n_realized = 0
            unrealized_sum = 0.0; n_unrealized = 0
            n_win = 0; n_loss = 0; n_flat = 0
            best_pos = ("", 0.0); worst_pos = ("", 0.0)
            for dt, r in positions:
                status = r[c_st-1].value
                pnl = None
                if status == "EXIT" and c_exit_pnl:
                    v = r[c_exit_pnl-1].value
                    if isinstance(v, (int, float)):
                        pnl = v; realized_sum += v; n_realized += 1
                elif status != "ROTATED_SAMEDAY" and status != "EXIT":
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
            win_rate = round(n_win / max(1, n_total) * 100, 1)

            # Portfolio header + KPI banner
            portfolio_ws.merge_cells("A1:L1")
            portfolio_ws["A1"] = f"AEGIS {mkt_key} PORTFOLIO · as of {latest_date or 'today'}"
            portfolio_ws["A1"].font = _Font(bold=True, size=14, color="FFFFFF")
            portfolio_ws["A1"].fill = HEADER_FILL if 'HEADER_FILL' in globals() else _PF(
                start_color="1F4E78", end_color="1F4E78", fill_type="solid")
            portfolio_ws["A1"].alignment = _Align(horizontal="center", vertical="center")
            portfolio_ws.row_dimensions[1].height = 28

            kpi_rows = [
                ["Realized P&L (closed)", realized_sum / 100.0, f"{n_realized} closed",
                 "Best position", f"{best_pos[0]} {best_pos[1]:+.2f}%"],
                ["Unrealized P&L (open)", unrealized_sum / 100.0, f"{n_unrealized} open",
                 "Worst position", f"{worst_pos[0]} {worst_pos[1]:+.2f}%"],
                ["COMBINED PORTFOLIO",    combined / 100.0,      f"{n_total} positions",
                 "Win rate", f"{win_rate}% ({n_win}W / {n_loss}L / {n_flat} flat)"],
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
            ]
            widths_pos = [12, 24, 12,
                              22, 12, 30,
                              8, 14, 22, 20, 12, 12, 8,
                              12, 20, 16, 14, 12, 14, 12,
                              12, 12, 12, 10,
                              12, 12, 12,
                              40, 40, 30]

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
            for c, name in enumerate(pos_hdr, start=1):
                cell = portfolio_ws.cell(7, c, name)
                cell.font = _Font(bold=True, color="FFFFFF", size=11)
                cell.fill = HEADER_FILL if 'HEADER_FILL' in globals() else _PF(
                    start_color="1F4E78", end_color="1F4E78", fill_type="solid")
                cell.alignment = _Align(horizontal="center", vertical="center")
                portfolio_ws.column_dimensions[_gcl_src(c)].width = widths_pos[c-1]

            # Sort positions: EXIT first, then by P&L descending
            def _sort_key(item):
                dt, r = item
                status = r[c_st-1].value
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
                # EXIT rows first (group=0), then non-EXIT by descending P&L
                group = 0 if status == "EXIT" else 1
                return (group, -pnl)

            positions_sorted = sorted(positions, key=_sort_key)
            for i, (dt, r) in enumerate(positions_sorted, start=8):
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

                def _classify_priority(st, iv, pnl, is_same_day=False):
                    """Returns bucket letter A-J.
                    2026-08-10: same-day EXIT (Entry Date == Exit Date) reclassified
                    as J (ARTIFACT) instead of I (CLOSED) · not a real trade."""
                    q_high = iv in ("🏆 QUALITY", "✓ OK")
                    q_mid = iv == "⚠ MARGINAL"
                    q_low = iv == "✗ AVOID"
                    pnl_neg = isinstance(pnl, (int, float)) and pnl < 0
                    if st == "ROTATED_SAMEDAY": return "J"
                    if st == "EXIT":
                        if is_same_day: return "J"    # same-day rotation · not real trade
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
                priority_bucket = _classify_priority(status, inv_verdict, _pnl_for_class,
                                                                        is_same_day=_is_same_day)
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
                # 2026-08-10 CEO v6 · closed positions get BLANK actionable fields
                # (operator: "You don't want CLOSED · Next Review 15-Aug ·
                # Decision HOLD · nonsense")
                is_terminal = action in ("CLOSED", "IGNORE")
                price_trigger = "" if is_terminal else _price_trigger(action, stop_v, t1_v, curr)
                next_review_anchor = rec_dt if rec_dt else dt
                next_review = "" if is_terminal else _next_review_date(review, next_review_anchor)
                exec_window = "" if is_terminal else _execution_window(action)

                # 2026-08-10 CEO fix v6 · added REVIEWING state (explicit)
                # 4 lifecycle states operator can act on unambiguously:
                #   🆕 NEW        · first day of recommendation
                #   🟢 ACTIVE     · held · both Runner + Portfolio agree to hold/protect
                #   🟡 REVIEWING  · Runner=EXIT · Portfolio challenging (Priority H)
                #   ⚪ CLOSED     · Runner=EXIT · Portfolio agrees close (Priority I)
                #   ⚪ ARTIFACT   · same-day rotation (never held)
                if priority_bucket == "I":
                    lifecycle = "⚪ CLOSED"
                elif priority_bucket == "H":
                    lifecycle = "🟡 REVIEWING"   # NEW · portfolio disputing exit
                elif priority_bucket == "J":
                    lifecycle = "⚪ ARTIFACT"
                elif rec_dt and dt and rec_dt == dt:
                    lifecycle = "🆕 NEW"
                else:
                    lifecycle = "🟢 ACTIVE"

                # 2026-08-10 CEO fix #3: R1/R2 Consensus column
                consensus = _consensus(tk, runner_val)

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
                ]
                for c, v in enumerate(vals, start=1):
                    cell = portfolio_ws.cell(i, c, v)
                    text_cols = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 28, 29, 30}
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

                # ROW COLOR now follows PRIORITY (not Status) · CEO call:
                # "color code to change based on inv verdict now"
                # Priority IS the composite of Status × Inv Verdict → colors reflect
                # the synthesized decision, not either signal alone.
                if priority_tag in PRIORITY_FILLS:
                    fill = PRIORITY_FILLS[priority_tag]
                    for c in range(1, len(pos_hdr) + 1):
                        portfolio_ws.cell(i, c).fill = fill
                if status in _STATUS_FILLS_LOCAL:
                    fill = _STATUS_FILLS_LOCAL[status]
                    for c in range(1, len(pos_hdr)+1):
                        portfolio_ws.cell(i, c).fill = fill
            portfolio_ws.freeze_panes = "A8"

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
