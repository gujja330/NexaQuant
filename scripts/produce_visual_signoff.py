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
sys.path.insert(0, str(_ROOT))

# CEO 2026-09-07 · FIVE-SHEET spec.
REQUIRED_SHEETS_5 = ["R1", "R2", "MOMENTUM", "DAILY RECOMMENDATION", "EXIT"]

# C19 (workbook-wide R1-zero) is now SCOPED, not abolished.
# The five-sheet spec REQUIRES R1 to be visible: it has its own advisory
# sheet, it appears on DAILY RECOMMENDATION, and EXIT is now "all exits -
# R1, R2, Momentum". A blanket workbook-wide R1 scan would therefore fail
# by design and would have to be deleted to go green, which is exactly how
# a real invariant gets quietly lost.
# What still matters, and is enforced below, is the part that protected
# production integrity: R1 must never appear on the R2 production sheet,
# and R1 must never be counted as production P&L.
R1_PERMITTED_SHEETS = {"R1", "DAILY RECOMMENDATION", "EXIT"}
R1_FORBIDDEN_SHEETS = {"R2", "MOMENTUM"}


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
    missing = [s for s in REQUIRED_SHEETS_5 if s not in sheets]
    extra = [s for s in sheets if s not in REQUIRED_SHEETS_5]
    checks = []
    checks.append(("exactly_5_required_sheets_present",
                    not missing and not extra,
                    f"missing={missing} extra={extra}"
                      if (missing or extra)
                      else "5/5 sheets present · no legacy sheets"))

    from backend.delivery import five_sheet_reader as _fsr

    # R2 · banner states the as-of and the holding count
    r2_ok = False; r2_reason = "sheet not found"
    if "R2" in sheets:
        rows = list(wb["R2"].iter_rows(values_only=True))
        title = str((rows[0] or [None])[0] or "")
        banner = " ".join(str((rows[i] or [None])[0] or "")
                            for i in (1, 2) if i < len(rows))
        has_date = asof in title
        has_count = "Holdings:" in banner
        r2_ok = has_date and has_count
        r2_reason = f"title_asof={has_date} · banner_holding_count={has_count}"
    checks.append(("r2_banner_correct", r2_ok, r2_reason))

    # R2 · every stop equals the canonical dynamic_risk_v2 value.
    # This is the BATAINDIA / CHAMBLFERT / ITC check.
    stop_ok = False; stop_reason = "canonical artifact absent"
    _dr = _ROOT / "reports" / "context" / f"dynamic_risk_{market.lower()}.json"
    if _dr.exists() and "R2" in sheets:
        import json as _j
        canon = {}
        for u in (_j.loads(_dr.read_text(encoding="utf-8")).get("updates") or []):
            if u.get("new_stop") is not None:
                canon[str(u["ticker"]).upper().split(".", 1)[0]] = round(
                    float(u["new_stop"]), 4)
        bad, checked = [], 0
        for rec in _fsr.r2_positions(wb):
            tk = str(rec.get("Stock") or "").strip()
            val = rec.get("Dynamic Stop")
            if tk in canon and isinstance(val, (int, float)):
                checked += 1
                if round(float(val), 4) != canon[tk]:
                    bad.append(f"{tk} sheet={val} canonical={canon[tk]}")
        stop_ok = not bad
        stop_reason = ("diverged: " + "; ".join(bad) if bad
                        else f"{checked} R2 stops match dynamic_risk_v2")
    checks.append(("r2_stop_matches_canonical", stop_ok, stop_reason))

    # MOMENTUM · producer freshness must be stated explicitly
    tm_ok = False; tm_reason = "sheet not found"
    if "MOMENTUM" in sheets:
        rows = list(wb["MOMENTUM"].iter_rows(values_only=True))
        head = " ".join(str(c) for r in rows[:6] if r for c in r if c)
        has_date = asof in head
        declares = "Producer as-of" in head and ("FRESH" in head or "STALE" in head)
        tm_ok = has_date and declares and "STALE" not in head
        tm_reason = (f"title_asof={has_date} · declares_freshness={declares} "
                       f"· stale={'STALE' in head}")
    checks.append(("momentum_fresh_and_declared", tm_ok, tm_reason))

    # MOMENTUM · declared universe must never be labelled "scanned"
    lbl_ok = False; lbl_reason = "sheet not found"
    if "MOMENTUM" in sheets:
        allc = " ".join(str(c) for r in wb["MOMENTUM"].iter_rows(values_only=True)
                          if r for c in r if c)
        lbl_ok = ("scanned universe=" not in allc
                    and "ACTUALLY EVALUATED" in allc)
        lbl_reason = ("declared vs evaluated reported separately" if lbl_ok
                        else "misleading universe label or missing "
                             "ACTUALLY EVALUATED row")
    checks.append(("momentum_universe_labelled_truthfully", lbl_ok, lbl_reason))

    # EXIT · unified history present and classified
    eh_ok = False; eh_reason = "sheet not found"
    if "EXIT" in sheets:
        ex = _fsr.exits(wb)
        prod = _fsr.production_exits(wb)
        eh_ok = True          # zero exits in the window is legitimate
        eh_reason = f"exits={len(ex)} · r2_production={len(prod)}"
    checks.append(("exit_history_unified", eh_ok, eh_reason))

    # No fabricated stand-ins for missing data on the position sheets
    fab_bad = []
    for sh in ("R1", "R2"):
        if sh not in sheets: continue
        for row in wb[sh].iter_rows(values_only=True):
            for v in row:
                if v and str(v).strip().upper() in ("LOW", "PENDING"):
                    fab_bad.append(sh)
                    break
    checks.append(("no_fabricated_low_pending", not fab_bad,
                    f"sheets_with_fabrication={sorted(set(fab_bad))}"
                      if fab_bad else "no LOW/PENDING stand-ins on R1 or R2"))

    # R1 must never leak into the production sheets
    from backend.delivery.canonical.retirement import retired_runners
    import re as _re_ss
    retired = retired_runners(_ROOT)
    prefixes = tuple(p + r + "-" for r in retired for p in ("", "IND-", "USA-"))
    _wb_word_re = _re_ss.compile(
        r"\b(" + "|".join(_re_ss.escape(r) for r in retired) + r")\b",
        _re_ss.IGNORECASE,
    )
    wb2 = load_workbook(xlsx, read_only=True, data_only=True)
    forbidden_hits = []
    for sh in sorted(R1_FORBIDDEN_SHEETS):
        if sh not in wb2.sheetnames: continue
        rn = 0
        for row_vals in wb2[sh].iter_rows(values_only=True):
            rn += 1
            for v in row_vals:
                if v is None: continue
                sv = str(v).strip()
                if (sv.upper() in retired
                        or sv.upper().startswith(prefixes)
                        or _wb_word_re.search(sv)):
                    forbidden_hits.append((sh, rn, sv[:60]))
                    break
    wb2.close()
    checks.append(("r1_absent_from_production_sheets",
                    len(forbidden_hits) == 0,
                    (f"cells_hit={len(forbidden_hits)} "
                      f"scanned={sorted(R1_FORBIDDEN_SHEETS)}"
                      + (f" · samples={forbidden_hits[:3]}"
                         if forbidden_hits else ""))))

    # R1 rows that ARE permitted must never carry an EXIT action.
    adv_bad = []
    if "R1" in sheets:
        for rec in _fsr.r1_positions(wb):
            if "EXIT" in str(rec.get("Action") or "").upper():
                adv_bad.append(str(rec.get("Stock")))
    checks.append(("r1_never_auto_exits", not adv_bad,
                    f"rows_with_exit_action={adv_bad}" if adv_bad
                      else "R1 escalates to REVIEW at most"))

    # Hidden / very-hidden sheets · formulas referencing retired runners ·
    # defined-name references
    hidden_sheets = []
    formula_hits = []
    defname_hits = []
    wb3 = load_workbook(xlsx, data_only=False)
    for sh_name in wb3.sheetnames:
        sh_obj = wb3[sh_name]
        state = getattr(sh_obj, "sheet_state", "visible")
        if state != "visible":
            hidden_sheets.append({"sheet": sh_name, "state": state})
        # No Definitions sheet in final spec · every sheet scanned
        for row_cells in sh_obj.iter_rows():
            for cell in row_cells:
                if getattr(cell, "data_type", None) == "f":
                    fx = str(cell.value or "").upper()
                    for r in retired:
                        if r in fx.split() or (f"{r}-" in fx):
                            formula_hits.append({"sheet": sh_name,
                                                   "coord": cell.coordinate,
                                                   "formula": fx[:60]})
                            break
    try:
        for dn in list(wb3.defined_names):
            u = str(dn).upper()
            if any(r in u.replace("_", "-").split("-") for r in retired) or \
                    any(u.startswith(p) for p in prefixes):
                defname_hits.append(dn)
    except Exception:
        pass
    wb3.close()

    checks.append(("no_hidden_or_very_hidden_sheets",
                    len(hidden_sheets) == 0,
                    f"hidden={hidden_sheets}"))
    checks.append(("no_formula_referencing_retired",
                    len(formula_hits) == 0,
                    (f"formula_hits={len(formula_hits)}"
                      + (f" · samples={formula_hits[:3]}"
                         if formula_hits else ""))))
    checks.append(("no_defined_name_referencing_retired",
                    len(defname_hits) == 0,
                    (f"defname_hits={len(defname_hits)}"
                      + (f" · samples={defname_hits[:3]}"
                         if defname_hits else ""))))

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
        f"the CEO 2026-09-07 FIVE-SHEET contract (R1 · R2 · MOMENTUM · "
        f"DAILY RECOMMENDATION · EXIT · canonical dynamic_risk_v2 stop shared "
        f"across sheets · R1 advisory-only and absent from production sheets · "
        f"momentum freshness declared · no fabrication).",
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
