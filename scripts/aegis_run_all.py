"""AEGIS · one-shot end-to-end runner.

Single command that reproduces LOCALLY what the two GitHub workflows do
in production (aegis-daily.yml + aegis-usa.yml):

    stage 1  Refresh market data          (India yfinance append · USA yfinance append)
    stage 2  Regenerate recommendations   (India Phase 2 orchestrator · USA daily)
    stage 3  SSoT enrichment              (backend.recommendation.ssot.run · both)
    stage 4  Rebuild unified XLSX          (reports/telegram/aegis_history.xlsx)
    stage 5  Preview Telegram message      (dry-run render · shown in terminal)
    stage 6  Send to Telegram              (one message per market · India + USA)
    stage 7  Research P0 · rebuild canonical Outcome Dataset
    stage 8  Research P1 · rebuild Attribution Analysis

Every stage is optional via flags — useful for iteration/debugging.

USAGE
─────
Full flow (default · does everything · both markets):
    python scripts/aegis_run_all.py

India only:
    python scripts/aegis_run_all.py --market india

Fast iteration (data already fresh · just rebuild XLSX + send):
    python scripts/aegis_run_all.py --skip-refresh --skip-regen

Dry-run everything (no Telegram send):
    python scripts/aegis_run_all.py --dry-run

Force send even when guards flag stale data (emergency use):
    python scripts/aegis_run_all.py --force-stale

Skip research post-processing (send only · no P0/P1 refresh):
    python scripts/aegis_run_all.py --skip-research

REQUIRED SECRETS (place in .env.telegram · loaded automatically):
    TELEGRAM_BOT_TOKEN=<bot token>
    TELEGRAM_CHAT_ID=<chat id>

Single market:
    python scripts/aegis_run_all.py --market india
    python scripts/aegis_run_all.py --market usa

Preview message only (no send · no XLSX rebuild):
    python scripts/aegis_run_all.py --preview-only

Force send even if data is stale (bypasses Guard 5+6):
    python scripts/aegis_run_all.py --force-stale

FLAGS
─────
    --market {india,usa,both}   default: both
    --skip-refresh               skip stage 1 (data refresh)
    --skip-regen                 skip stages 2+3 (rec regen + SSoT)
    --skip-xlsx                  skip stage 4 (XLSX rebuild)
    --dry-run                    skip stage 6 (Telegram send) · previews only
    --preview-only               run stages 4+5 only · no data mutation · no send
    --force-stale                bypass freshness guards (SEND_FORCE_STALE=1)
    --asof YYYY-MM-DD            date stamp (default: today IST)
    --open-xlsx                  open the XLSX in Excel when done (Windows)

EXIT CODES
──────────
    0   all requested stages succeeded
    1   a stage failed (see printed summary)
    2   Telegram tokens missing (send skipped · other stages still ran)
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import time
from datetime import date as _date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


_ROOT = Path(__file__).resolve().parents[1]
_PYTHON = sys.executable


def _banner(stage_num: int, total: int, title: str) -> None:
    bar = "═" * 60
    print(f"\n{bar}")
    print(f"  Stage {stage_num}/{total} · {title}")
    print(bar)


def _run(cmd: list[str], *, cwd: Path = _ROOT, env_extra: dict | None = None) -> tuple[bool, float]:
    """Run a subprocess · stream output live · return (ok, elapsed_seconds)."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    print(f"  $ {' '.join(cmd)}")
    t0 = time.time()
    try:
        result = subprocess.run(cmd, cwd=str(cwd), env=env, check=False)
        ok = result.returncode == 0
    except FileNotFoundError as e:
        print(f"  [skip] {e}")
        return False, 0.0
    return ok, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                       description=__doc__)
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--skip-refresh", action="store_true", help="skip stage 1")
    ap.add_argument("--skip-regen", action="store_true", help="skip stages 2+3")
    ap.add_argument("--skip-xlsx", action="store_true", help="skip stage 4")
    ap.add_argument("--skip-research", action="store_true", help="skip stages 7+8 (P0+P1 refresh)")
    ap.add_argument("--dry-run", action="store_true",
                       help="preview message · do not send to Telegram")
    ap.add_argument("--preview-only", action="store_true",
                       help="stages 4+5 only · no data mutation · no send")
    ap.add_argument("--force-stale", action="store_true",
                       help="bypass Guards 5+6 (SEND_FORCE_STALE=1)")
    ap.add_argument("--asof", default=_date.today().isoformat(),
                       help="date stamp (default: today)")
    ap.add_argument("--open-xlsx", action="store_true",
                       help="open the XLSX in Excel when done (Windows only)")
    args = ap.parse_args()

    # ── Preview-only shortcut ──
    if args.preview_only:
        args.skip_refresh = True
        args.skip_regen = True
        args.dry_run = True

    markets = ["india", "usa"] if args.market == "both" else [args.market]

    # Stage plan (skips accounted for)
    stages = []
    if not args.skip_refresh:
        stages.append("refresh")
    if not args.skip_regen:
        stages.append("regen")
        stages.append("ssot")
    if not args.skip_xlsx:
        stages.append("xlsx")
    stages.append("preview")
    if not args.dry_run:
        stages.append("send")
    if not args.skip_research:
        stages.append("research")
    total = len(stages) + (1 if "research" in stages else 0)   # research is 2 stages

    print(f"\n▶ AEGIS end-to-end · asof={args.asof} · markets={markets}")
    print(f"  stages: {' → '.join(stages)}")

    results: list[tuple[str, bool, float]] = []
    stage_num = 0

    # ── Stage 1 · Refresh market data ──
    if "refresh" in stages:
        stage_num += 1
        _banner(stage_num, total, "Refresh market data (append fresh bars)")
        for m in markets:
            if m == "india":
                ok, dt = _run([_PYTHON, "india/refresh_data.py"])
                results.append((f"refresh:india", ok, dt))
            else:
                # USA has no dedicated refresh script · bars append inside usa_daily
                print(f"  [usa] refresh handled inside usa_daily · skipping standalone step")
                results.append((f"refresh:usa", True, 0.0))

    # ── Stage 2 · Regenerate recommendations ──
    if "regen" in stages:
        stage_num += 1
        _banner(stage_num, total, "Regenerate recommendations (base engines)")
        for m in markets:
            if m == "india":
                # Legacy R1 generator
                ok1, dt1 = _run([_PYTHON, "india/recommendation_generator.py"])
                results.append((f"regen:india:R1", ok1, dt1))
                # Phase 2 v2 (adaptive rec + fusion · produces enriched recs.json)
                ok2, dt2 = _run([_PYTHON, "scripts/aegis_daily_v2.py", "--continue"])
                results.append((f"regen:india:v2", ok2, dt2))
            else:
                # USA daily orchestrator (bars + engine + everything)
                ok, dt = _run([_PYTHON, "usa/scripts/usa_daily.py"])
                results.append((f"regen:usa", ok, dt))

    # ── Stage 3 · SSoT enrichment ──
    if "ssot" in stages:
        stage_num += 1
        _banner(stage_num, total, "SSoT enrichment (cycles 3-4 + R006)")
        for m in markets:
            ok, dt = _run([_PYTHON, "-m", "backend.recommendation.ssot.run",
                                 "--market", m])
            results.append((f"ssot:{m}", ok, dt))

    # ── Stage 4 · Rebuild unified XLSX ──
    if "xlsx" in stages:
        stage_num += 1
        _banner(stage_num, total, "Rebuild unified XLSX (Date+Country+Run_Type+Ticker)")
        xlsx_cmd = [_PYTHON, "scripts/rebuild_xlsx_local.py",
                        "--asof", args.asof, "--market", args.market]
        if args.open_xlsx:
            xlsx_cmd.append("--open")
        ok, dt = _run(xlsx_cmd)
        results.append(("xlsx", ok, dt))

    # ── Stage 5 · Preview Telegram message (dry-run render) ──
    if "preview" in stages:
        stage_num += 1
        _banner(stage_num, total, "Preview Telegram message (dry-run render)")
        ok, dt = _run([_PYTHON, "scripts/telegram_command_center_send.py",
                            "--market", args.market, "--dry-run"])
        results.append(("preview", ok, dt))

    # ── Stage 6 · Send to Telegram (one message per market) ──
    if "send" in stages:
        stage_num += 1
        _banner(stage_num, total, "Send to Telegram (compact msg + XLSX attachment)")
        env_extra = {"SEND_FORCE_STALE": "1"} if args.force_stale else None
        if args.force_stale:
            env_extra["PRICE_GUARD_OVERRIDE"] = "1"
        for m in markets:
            ok, dt = _run([_PYTHON, "scripts/telegram_command_center_send.py",
                                "--market", m], env_extra=env_extra)
            results.append((f"send:{m}", ok, dt))

    # ── Stage 7 · Research P0 · rebuild canonical Outcome Dataset ──
    if "research" in stages:
        stage_num += 1
        _banner(stage_num, total, "Research P0 · rebuild Outcome Dataset (canonical)")
        ok, dt = _run([_PYTHON, "scripts/build_outcome_dataset.py"])
        results.append(("research:p0", ok, dt))

        # ── Stage 8 · Research P1 · rebuild Attribution Analysis ──
        stage_num += 1
        _banner(stage_num, total, "Research P1 · rebuild Attribution Analysis")
        ok, dt = _run([_PYTHON, "scripts/run_attribution.py"])
        results.append(("research:p1", ok, dt))

    # ── Summary ──
    print(f"\n{'═' * 60}")
    print(f"  SUMMARY · {len(results)} stages")
    print("═" * 60)
    fail_count = 0
    for name, ok, dt in results:
        icon = "✓" if ok else "✗"
        print(f"  {icon}  {name:<28}  {dt:6.1f}s")
        if not ok:
            fail_count += 1
    print("═" * 60)

    xlsx_path = _ROOT / "reports" / "telegram" / "aegis_history.xlsx"
    if xlsx_path.exists():
        size_kb = xlsx_path.stat().st_size / 1024
        print(f"  XLSX: {xlsx_path.relative_to(_ROOT)} ({size_kb:.1f} KB)")

    if fail_count:
        print(f"\n  ✗ {fail_count} stage(s) FAILED · see logs above")
        return 1
    print(f"\n  ✓ all stages ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
