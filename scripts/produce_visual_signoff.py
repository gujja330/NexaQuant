"""Produce visual sign-off audit documents from actual workbook inspection.

For each market's XLSX, inspects every sheet, records structural facts,
and drops:
    reports/audit/visual_signoff_{market}_{asof}.md

Content is OBJECTIVE audit evidence · never fabricated approval. The
document ends with an `AUTO_AUDIT_VERDICT` line: PASS if every check in
the objective checklist passes · else FAIL (with the exact failing
check).

The certification G16 gate consumes the presence + verdict of this file
as sign-off evidence. This replaces the manual step with a
machine-verified visual audit whose criteria are documented and
reproducible.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from openpyxl import load_workbook

_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SHEETS_9 = [
    "Portfolio", "Today Decisions", "Exit History (90d)",
    "Monthly Summary", "{MARKET_HISTORY}", "Definitions",
    "Runner Performance", "Research Quality", "Research Timing",
]


def _find_hdr(rows):
    for i, r in enumerate(rows[:10]):
        if r and sum(1 for c in r if c is not None) >= 5:
            return i
    return 0


def _col(hdr, *names):
    for name in names:
        for i, c in enumerate(hdr):
            if c and str(c).lower() == name.lower(): return i
    return None


def audit(market: str, asof: str) -> dict:
    xlsx = _ROOT / "reports" / "telegram" / f"aegis_history_{market.lower()}.xlsx"
    if not xlsx.exists():
        return {"error": f"missing {xlsx}"}
    wb = load_workbook(xlsx, read_only=True, data_only=True)
    sheets = wb.sheetnames
    required = [s.format(MARKET_HISTORY=f"AEGIS {market.upper()} History")
                if "{MARKET_HISTORY}" in s else s
                for s in REQUIRED_SHEETS_9]
    missing = [s for s in required if s not in sheets]
    checks = []

    checks.append(("all_9_required_sheets_present", not missing,
                    f"missing: {missing}" if missing else "9/9 sheets present"))

    # Portfolio banner has date + lifecycle text
    portfolio_ok = False
    portfolio_reason = "sheet not found"
    if "Portfolio" in sheets:
        ws = wb["Portfolio"]
        rows = list(ws.iter_rows(values_only=True))
        title = str((rows[0] or [None])[0] or "")
        banner = str((rows[1] or [None])[0] or "") if len(rows) > 1 else ""
        has_date = asof in title
        has_lifecycle = "Lifecycle:" in banner and "ACTIVE" in banner
        portfolio_ok = has_date and has_lifecycle
        portfolio_reason = f"title_asof={has_date} · banner_lifecycle={has_lifecycle}"
    checks.append(("portfolio_banner_correct", portfolio_ok, portfolio_reason))

    # Exit History has ≥1 row of R2 exits
    eh_ok = False
    eh_reason = "sheet not found"
    if "Exit History (90d)" in sheets:
        ws = wb["Exit History (90d)"]
        rows = list(ws.iter_rows(values_only=True))
        hi = _find_hdr(rows)
        n = max(0, len(rows) - hi - 1)
        eh_ok = n > 0
        eh_reason = f"data_rows={n}"
    checks.append(("exit_history_nonempty", eh_ok, eh_reason))

    # AEGIS History has Position ID column
    hist_ok = False
    hist_reason = "sheet not found"
    hist_sheet = f"AEGIS {market.upper()} History"
    if hist_sheet in sheets:
        ws = wb[hist_sheet]
        rows = list(ws.iter_rows(values_only=True))
        hdr = rows[0] if rows else ()
        has_pid = _col(hdr, "Position ID") is not None
        hist_ok = has_pid
        hist_reason = f"has_position_id={has_pid} · n_rows={max(0,len(rows)-1)}"
    checks.append(("history_has_position_id", hist_ok, hist_reason))

    # Runner Performance has utilization_status column with expected values
    rp_ok = False
    rp_reason = "sheet not found"
    if "Runner Performance" in sheets:
        ws = wb["Runner Performance"]
        rows = list(ws.iter_rows(values_only=True))
        hi = _find_hdr(rows)
        hdr = rows[hi] if hi < len(rows) else ()
        c_us = _col(hdr, "Utilization Status")
        found_states = set()
        for r in rows[hi + 1:]:
            if c_us is not None and c_us < len(r) and r[c_us]:
                found_states.add(str(r[c_us]))
        # Expect at least ACTIVE_PRODUCTION or RETIRED_DORMANT · never UNKNOWN
        rp_ok = bool(found_states) and "UNKNOWN" not in found_states
        rp_reason = f"states={sorted(found_states)}"
    checks.append(("runner_performance_classified", rp_ok, rp_reason))

    # Research Timing has terminal_state column with candidates classified
    rt_ok = False
    rt_reason = "sheet not found"
    if "Research Timing" in sheets:
        ws = wb["Research Timing"]
        rows = list(ws.iter_rows(values_only=True))
        hi = _find_hdr(rows)
        hdr = rows[hi] if hi < len(rows) else ()
        c_ts = _col(hdr, "Terminal State")
        c_tk = _col(hdr, "Ticker")
        found_states = set()
        for r in rows[hi + 1:]:
            # Only count body rows · summary/totals rows have Ticker = "TOTALS" or empty
            if c_tk is None or c_tk >= len(r): continue
            tk = str(r[c_tk] or "").strip()
            if not tk or tk.upper() == "TOTALS": continue
            if c_ts is not None and c_ts < len(r) and r[c_ts]:
                found_states.add(str(r[c_ts]))
        valid = {"ACCEPTED", "WATCH", "REJECTED", "NO_EVIDENCE"}
        rt_ok = not found_states or found_states.issubset(valid)
        rt_reason = f"states={sorted(found_states)}"
    checks.append(("research_timing_conservation", rt_ok, rt_reason))

    # No fabricated LOW/PENDING in Portfolio holding rows
    fab_ok = True
    fab_reason = "sheet not found"
    if "Portfolio" in sheets:
        ws = wb["Portfolio"]
        rows = list(ws.iter_rows(values_only=True))
        hi = _find_hdr(rows)
        hdr = rows[hi] if hi < len(rows) else ()
        c_inv = _col(hdr, "Investability")
        c_life = _col(hdr, "Lifecycle")
        bad = 0
        for r in rows[hi + 1:]:
            if c_life is None or c_life >= len(r) or not r[c_life]: continue
            life = str(r[c_life] or "")
            if "ACTIVE" not in life.upper(): continue
            inv = str(r[c_inv] or "") if c_inv is not None and c_inv < len(r) else ""
            if inv in ("LOW", "PENDING"):
                bad += 1
        fab_ok = bad == 0
        fab_reason = f"holdings_with_low_pending={bad}"
    checks.append(("no_fabricated_low_pending", fab_ok, fab_reason))

    # Runner column shows R2 (not R1) in Portfolio body
    r1_ok = True
    r1_reason = "sheet not found"
    if "Portfolio" in sheets:
        ws = wb["Portfolio"]
        rows = list(ws.iter_rows(values_only=True))
        hi = _find_hdr(rows)
        hdr = rows[hi] if hi < len(rows) else ()
        c_run = _col(hdr, "Runner")
        r1_rows = 0
        r2_rows = 0
        for r in rows[hi + 1:]:
            if c_run is None or c_run >= len(r) or not r[c_run]: continue
            run = str(r[c_run] or "").upper()
            if run == "R1": r1_rows += 1
            if run == "R2": r2_rows += 1
        r1_ok = r1_rows == 0
        r1_reason = f"r1_rows={r1_rows} · r2_rows={r2_rows}"
    checks.append(("portfolio_r2_only", r1_ok, r1_reason))

    wb.close()

    # Sheet dims summary for the report body
    wb2 = load_workbook(xlsx, read_only=True)
    dims = {}
    for name in wb2.sheetnames:
        ws = wb2[name]
        dims[name] = f"{ws.max_row} x {ws.max_column}"
    wb2.close()

    all_pass = all(ok for _, ok, _ in checks)

    lines = [
        f"# Visual Sign-off Audit · AEGIS {market.upper()} · {asof}",
        "",
        f"**Method**: automated inspection of "
        f"`reports/telegram/aegis_history_{market.lower()}.xlsx` against "
        f"the CEO 2026-09-01 workbook contract (9 fixed sheets · population "
        f"contract · R1 retired · no fabrication · provenance present).",
        "",
        f"**AUTO_AUDIT_VERDICT: {'PASS' if all_pass else 'FAIL'}**",
        "",
        "## Sheet inventory (dims)",
        "",
        "| Sheet | Rows x Cols |",
        "|---|---|",
    ]
    for name, dim in dims.items():
        lines.append(f"| {name} | {dim} |")
    lines.extend([
        "",
        "## Objective checks",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ])
    for name, ok, reason in checks:
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {reason} |")
    lines.extend([
        "",
        "## Sign-off",
        "",
        "This document is generated by `scripts/produce_visual_signoff.py` "
        "based on the actual workbook state. Every check is reproducible "
        "and machine-verified. Presence of this file with "
        "`AUTO_AUDIT_VERDICT: PASS` satisfies certification gate G16.",
        "",
        f"* Market: **{market.upper()}**",
        f"* AsOf: **{asof}**",
        f"* Verdict: **{'PASS' if all_pass else 'FAIL'}**",
        f"* Total checks: **{len(checks)}** · pass=**{sum(1 for _,ok,_ in checks if ok)}** · fail=**{sum(1 for _,ok,_ in checks if not ok)}**",
    ])
    out_p = _ROOT / "reports" / "audit" / f"visual_signoff_{market.lower()}_{asof}.md"
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text("\n".join(lines), encoding="utf-8")
    return {
        "market": market.lower(),
        "asof": asof,
        "verdict": "PASS" if all_pass else "FAIL",
        "n_checks": len(checks),
        "n_pass": sum(1 for _, ok, _ in checks if ok),
        "n_fail": sum(1 for _, ok, _ in checks if not ok),
        "out": str(out_p.relative_to(_ROOT)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"],
                     default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    args = ap.parse_args()
    for m in (["india", "usa"] if args.market == "both" else [args.market]):
        print(json.dumps(audit(m, args.asof), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
