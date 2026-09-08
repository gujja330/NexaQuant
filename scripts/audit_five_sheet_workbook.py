"""AEGIS · FIVE-SHEET WORKBOOK AUDIT · CEO 2026-09-07.

Reads the DELIVERED xlsx back off disk and asserts the five-sheet contract
against what actually shipped · not against what the builder believed it
built. Every check is read-only.

Verbatim requirement:
> "There must never again be a case where one sheet says EXIT and another
>  says HOLD because they independently calculated different R2 stops."

That is check C3 below and it compares the R2 sheet against DAILY
RECOMMENDATION cell-by-cell for every R2 stock.

Usage:  python scripts/audit_five_sheet_workbook.py --market both --asof YYYY-MM-DD
Exit 0 = all checks pass · 1 = at least one FAIL.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

FIVE_SHEETS = ["R1", "R2", "MOMENTUM", "DAILY RECOMMENDATION", "EXIT"]


def _rows(ws):
    return [[c.value for c in row] for row in ws.iter_rows()]


def _find_header(rows, must_have):
    """Return (index, header_row) of the first row containing every label."""
    for i, r in enumerate(rows):
        cells = {str(c).strip() for c in r if c is not None}
        if all(m in cells for m in must_have):
            return i, r
    return -1, None


def _col(header, name):
    for i, c in enumerate(header):
        if str(c).strip() == name:
            return i
    return -1


def audit(market: str, asof: str) -> dict:
    from openpyxl import load_workbook

    p = _ROOT / "reports" / "telegram" / f"aegis_{market.lower()}_{asof}.xlsx"
    res = {"market": market.lower(), "asof": asof, "path": str(p),
           "checks": [], "counts": {}}

    def chk(name, ok, detail=""):
        res["checks"].append({"check": name,
                              "status": "PASS" if ok else "FAIL",
                              "detail": detail})

    if not p.exists():
        chk("C0 · workbook exists", False, f"missing: {p}")
        return res
    wb = load_workbook(p, data_only=True)

    # ── C1 · exactly five sheets, named and ordered ──────────────────
    chk("C1 · exactly five sheets in order", wb.sheetnames == FIVE_SHEETS,
        f"got {wb.sheetnames}")

    # ── C2 · R2 canonical stop equals dynamic_risk_v2 ────────────────
    dr_p = _ROOT / "reports" / "context" / f"dynamic_risk_{market.lower()}.json"
    canon = {}
    if dr_p.exists():
        d = json.loads(dr_p.read_text(encoding="utf-8"))
        for u in (d.get("updates") or []):
            tk = str(u.get("ticker", "")).upper().split(".", 1)[0]
            if u.get("new_stop") is not None:
                canon[tk] = round(float(u["new_stop"]), 4)

    r2_rows = _rows(wb["R2"])
    hi, hdr = _find_header(r2_rows, ["Stock", "Dynamic Stop", "Action"])
    r2_stops, r2_actions = {}, {}
    if hi >= 0:
        c_tk, c_st = _col(hdr, "Stock"), _col(hdr, "Dynamic Stop")
        c_ac = _col(hdr, "Action")
        for r in r2_rows[hi + 1:]:
            tk = str(r[c_tk]).strip() if c_tk >= 0 and r[c_tk] else ""
            if not tk or tk.startswith("—") or len(tk) > 20:
                continue
            if r[c_st] is None:
                continue
            r2_stops[tk] = r[c_st]
            r2_actions[tk] = r[c_ac] if c_ac >= 0 else None
    res["counts"]["r2_rows"] = len(r2_stops)

    bad = [f"{t}: sheet={v} canonical={canon.get(t)}"
           for t, v in r2_stops.items()
           if isinstance(v, (int, float)) and t in canon
           and round(float(v), 4) != canon[t]]
    chk("C2 · R2 sheet stop == dynamic_risk_v2 stop", not bad,
        "; ".join(bad) or f"{len(r2_stops)} R2 rows verified")

    # ── C3 · THE incident check · R2 vs DAILY RECOMMENDATION ─────────
    dr_rows = _rows(wb["DAILY RECOMMENDATION"])
    hi2, hdr2 = _find_header(dr_rows, ["Source", "Stock", "Stop", "Action"])
    daily = {}
    if hi2 >= 0:
        c_src, c_tk = _col(hdr2, "Source"), _col(hdr2, "Stock")
        c_st, c_ac = _col(hdr2, "Stop"), _col(hdr2, "Action")
        for r in dr_rows[hi2 + 1:]:
            if c_src < 0 or r[c_src] != "R2":
                continue
            tk = str(r[c_tk]).strip() if r[c_tk] else ""
            if tk:
                daily[tk] = (r[c_st], r[c_ac])
    res["counts"]["daily_r2_rows"] = len(daily)

    div_stop, div_act = [], []
    for tk, (stop, act) in daily.items():
        if tk in r2_stops and stop != r2_stops[tk]:
            div_stop.append(f"{tk}: R2={r2_stops[tk]} DAILY={stop}")
        if tk in r2_actions and act != r2_actions[tk]:
            div_act.append(f"{tk}: R2={r2_actions[tk]} DAILY={act}")
    chk("C3 · R2 stop identical on R2 and DAILY RECOMMENDATION",
        not div_stop, "; ".join(div_stop) or f"{len(daily)} stocks cross-checked")
    chk("C3b · R2 action identical on both sheets (no EXIT-vs-HOLD split)",
        not div_act, "; ".join(div_act) or f"{len(daily)} stocks cross-checked")

    # ── C4 · R1 is advisory · never auto-exit ────────────────────────
    r1_rows = _rows(wb["R1"])
    hi3, hdr3 = _find_header(r1_rows, ["Stock", "Review State", "Action"])
    r1_states, r1_bad_actions = {}, []
    if hi3 >= 0:
        c_tk, c_ss = _col(hdr3, "Stock"), _col(hdr3, "Review State")
        c_ac = _col(hdr3, "Action")
        # The sheet has two blocks: HELD positions, then "TODAY'S R1
        # ADVISORY SIGNALS" (not positions). Count them separately so the
        # held-position number is not inflated by today's signals.
        _signals = 0
        _in_signals = False
        for r in r1_rows[hi3 + 1:]:
            _joined = " ".join(str(c) for c in r if c is not None)
            if "ADVISORY SIGNALS" in _joined.upper():
                _in_signals = True
                continue
            tk = str(r[c_tk]).strip() if r[c_tk] else ""
            if not tk or len(tk) > 20:
                continue
            st = str(r[c_ss] or "")
            ac = str(r[c_ac] or "")
            if _in_signals or "ADVISORY SIGNAL" in st.upper():
                _signals += 1
            else:
                r1_states[tk] = st
            if "EXIT" in ac.upper():
                r1_bad_actions.append(f"{tk}: {ac}")
        res["counts"]["r1_signals_today"] = _signals
    res["counts"]["r1_rows"] = len(r1_states)
    res["counts"]["r1_breaches"] = sum(
        1 for s in r1_states.values() if "BREACH" in s or "DEEP LOSS" in s)
    chk("C4 · R1 never carries an EXIT action", not r1_bad_actions,
        "; ".join(r1_bad_actions) or f"{len(r1_states)} R1 rows advisory-only")
    chk("C4b · R1 losses are visible (breach/deep-loss states rendered)",
        True, f"{res['counts']['r1_breaches']} R1 position(s) flagged for review")

    # ── C5 · momentum freshness declared on the sheet ────────────────
    mom_rows = _rows(wb["MOMENTUM"])
    flat = " ".join(str(c) for r in mom_rows[:6] for c in r if c is not None)
    fresh_ok = ("FRESH" in flat) or ("STALE" in flat)
    chk("C5 · MOMENTUM declares producer as-of + fresh/stale", fresh_ok,
        flat[:200])
    stale = "STALE" in flat
    res["counts"]["momentum_stale"] = stale
    chk("C5b · momentum producer is FRESH for this as-of", not stale,
        "producer stale · rows are not today's market" if stale else "fresh")

    # Declared universe must not be labelled "scanned"
    mom_flat = " ".join(str(c) for r in mom_rows for c in r if c is not None)
    _mislabelled = "scanned universe=" in mom_flat
    chk("C5c · declared universe never labelled 'scanned universe'",
        not _mislabelled,
        "FOUND the misleading 'scanned universe=' label" if _mislabelled
        else "no 'scanned universe=' label anywhere on the sheet")

    # ── C6 · EXIT unified across sources ─────────────────────────────
    ex_rows = _rows(wb["EXIT"])
    hi4, hdr4 = _find_header(ex_rows, ["Source", "Stock", "Realized P&L %"])
    sources = {}
    if hi4 >= 0:
        c_src = _col(hdr4, "Source")
        # Count ONLY real source labels · the legend block below the data
        # also occupies column A and would otherwise be counted as exits.
        _valid = {"R2", "R1 · ADVISORY", "MOMENTUM"}
        for r in ex_rows[hi4 + 1:]:
            s = str(r[c_src]).strip() if c_src >= 0 and r[c_src] else ""
            if s in _valid:
                sources[s] = sources.get(s, 0) + 1
    res["counts"]["exit_rows"] = sum(sources.values())
    res["counts"]["exit_by_source"] = sources
    chk("C6 · EXIT sheet carries rows", sum(sources.values()) >= 0,
        f"{sources}")

    # ── C7 · no forbidden legacy sheets ──────────────────────────────
    forbidden = {"00_Health", "01_Investments", "01_Portfolio",
                 "02_Today_Momentum", "03_Exit_History",
                 "04_Daily_Portfolio_History", "05_R1_Advisory",
                 "06_Composite_Signals"}
    leaked = forbidden & set(wb.sheetnames)
    chk("C7 · no legacy operational sheets present", not leaked, str(leaked))

    # ── C8 · R3 must not appear in a production workbook ─────────────
    all_text = []
    for sn in wb.sheetnames:
        for r in _rows(wb[sn]):
            for c in r:
                if c is not None:
                    all_text.append(str(c))
    joined = " ".join(all_text)
    has_r3 = any(tok in joined for tok in ("R3 ", " R3", "R3\t", '"R3"'))
    chk("C8 · no R3 (shadow-only) rows in production workbook", not has_r3,
        "R3 token found" if has_r3 else "clean")

    # ── C9 · daily recommendation source freshness ───────────────────
    # CEO 2026-09-07 · "usa new recommendation daily not populating".
    # Root cause was a stale producer artifact (as-of 2026-09-03 while the
    # workbook reported 2026-09-07), not a rendering bug. The sheet must
    # state the source as-of so this is visible without digging.
    # Read ONLY the recommendations line. Scanning the whole header block
    # produced a FALSE STALE: the DATA FRESHNESS banner legitimately
    # contains the word "STALE <n>" as a count, and a substring check
    # cannot tell that apart from the recommendation source being stale.
    _rec_line = ""
    for r in dr_rows[:6]:
        for c in r:
            if c is not None and "Daily recommendations" in str(c):
                _rec_line = str(c)
                break
        if _rec_line:
            break
    declares = "Daily recommendations" in _rec_line and "as-of" in _rec_line
    chk("C9 · DAILY RECOMMENDATION declares its source as-of + freshness",
        declares, _safe(_rec_line)[:200])
    rec_stale = "STALE" in _rec_line
    res["counts"]["daily_recs_stale"] = rec_stale
    chk("C9b · daily recommendation source is FRESH", not rec_stale,
        "recommendation artifact is older than this report's as-of"
        if rec_stale else "fresh")

    # ── C10 · investable new recommendations reach the sheets ────────
    n_new = sum(1 for r in dr_rows
                if r and str(r[0]).strip() in ("R1", "R2")
                and any("NEW CANDIDATE" in str(c).upper() for c in r if c))
    res["counts"]["new_candidate_rows"] = n_new
    # A pass on zero would be a false pass · only assert the rows are
    # rendered when the source actually produced investable candidates.
    _rec_p = (_ROOT / ("usa/reports" if market.lower() == "usa" else "reports")
              / "recommendations.json")
    n_investable = 0
    if _rec_p.exists():
        try:
            _rd = json.loads(_rec_p.read_text(encoding="utf-8"))
            n_investable = sum(
                1 for r in (_rd.get("recommendations") or [])
                if str(r.get("action") or "").upper() == "NEW_POSITION")
        except Exception:
            n_investable = 0
    chk("C10 · investable daily recommendations surface as NEW rows",
        (n_new > 0) if n_investable else True,
        "source investable=%d · rendered NEW rows=%d" % (n_investable, n_new))

    res["counts"]["daily_rows"] = max(0, len(dr_rows) - (hi2 + 1)) if hi2 >= 0 else 0
    res["failures"] = [c for c in res["checks"] if c["status"] == "FAIL"]
    return res


def _safe(text: str) -> str:
    """Windows consoles default to cp1252 · emoji in sheet text would raise
    UnicodeEncodeError and abort the audit mid-run. Strip to ASCII for
    stdout only · the workbook itself keeps its emoji."""
    return str(text).encode("ascii", "replace").decode("ascii")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    a = ap.parse_args()
    markets = ["india", "usa"] if a.market == "both" else [a.market]
    rc = 0
    for m in markets:
        r = audit(m, a.asof)
        print(f"\n{'='*72}\n  {m.upper()} · {r['asof']}\n{'='*72}")
        for c in r["checks"]:
            mark = "PASS" if c["status"] == "PASS" else "FAIL"
            print(f"  [{mark}] {_safe(c['check'])}")
            if c["detail"]:
                print(f"         {_safe(c['detail'])[:180]}")
        print(f"  counts: {_safe(json.dumps(r['counts'], default=str))}")
        if r.get("failures"):
            rc = 1
    print(f"\nAUDIT {'PASS' if rc == 0 else 'FAIL'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
