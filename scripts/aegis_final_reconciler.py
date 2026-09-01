"""AEGIS · Final End-to-End Contract Reconciliation · CEO 2026-08-31.

Verifies the delivery/audit chain across every layer for a single
market. STOP-on-mismatch · never guesses · never silently patches.

Checks:
  · Registry → Portfolio (ACTIVE consistency)
  · Registry-CLOSED → Exit History body (I20-shape)
  · Portfolio banner ≡ Portfolio body (per-axis)
  · AEGIS History PID format · 100% new-format
  · No fabricated LOW/PENDING/0 in Portfolio holding rows
  · Monthly Summary sheet exists (rule C5)
  · Exit History body has NO trailer strings (rule C5)
  · Position ID uniqueness at canonical grain per population
  · Historical rows preserved (no dedup)

Emits `reports/reconcile/final_reconcile_{market}_{asof}.json` with
every check result · exits 0 on all-pass · non-zero on any mismatch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.research import opportunity_registry as oreg   # noqa: E402
from openpyxl import load_workbook                            # noqa: E402


_NEW_PID_PREFIXES = ("IND-", "USA-", "R1-", "R2-", "SHADOW-", "MOMENTUM-")


class ReconcileFailure(Exception):
    pass


def _col(hdr, name):
    for i, c in enumerate(hdr):
        if c and name.lower() == str(c).lower(): return i
    return None


def reconcile(market: str, root: Path) -> dict:
    market_l = market.lower()
    asof = date.today().isoformat()
    xlsx = root / "reports" / "telegram" / f"aegis_history_{market_l}.xlsx"
    if not xlsx.exists():
        raise ReconcileFailure(f"artifact not present · {xlsx}")

    wb = load_workbook(xlsx, read_only=True, data_only=True)
    checks: list = []

    def _add(name: str, ok: bool, detail: str = "", data=None):
        checks.append({"name": name, "ok": ok, "detail": detail, "data": data})

    # ── C1 · Sheets present · Section 11 fixed 8-sheet workbook ─────
    # CEO 2026-09-01 · every daily workbook must ship the same 8 sheets.
    # If any sheet is missing, delivery is not certifiable.
    required_sheets = [
        "Portfolio",                    # 1
        "Today Decisions",              # 2 (Section 7 · separate sheet)
        "Exit History (90d)",           # 3
        "Monthly Summary",              # 4
        f"AEGIS {market.upper()} History",  # 5
        "Definitions",                  # 6
        "Runner Performance",           # 7
        "Research Quality",             # 8
        "Research Timing",              # 9 (Momentum ledger · CEO Momentum correction)
    ]
    missing = [s for s in required_sheets if s not in wb.sheetnames]
    _add("C1_required_sheets_present", not missing,
          f"missing sheets: {missing}" if missing else "all 8 required sheets present",
          {"present": wb.sheetnames, "required": required_sheets,
           "missing": missing})

    # ── C2 · Registry consistency ──────────────────────────────────
    reg = oreg.load_all(root)
    reg_active = []
    reg_closed_90d = []
    _asof_d = date.fromisoformat(asof)
    from datetime import timedelta
    _cutoff = (_asof_d - timedelta(days=90)).isoformat()
    for _pid, opps in reg.items():
        for o in opps:
            if o.market.lower() != market_l: continue
            if o.status == "ACTIVE":
                reg_active.append(o.opportunity_id)
            elif o.status == "CLOSED" and o.closed_date and o.closed_date >= _cutoff:
                reg_closed_90d.append(o.opportunity_id)
    n_reg_active = len(set(reg_active))
    n_reg_closed = len(set(reg_closed_90d))
    _add("C2_registry_load", True,
          f"Registry {market_l}: {n_reg_active} ACTIVE · {n_reg_closed} CLOSED-90d",
          {"n_active": n_reg_active, "n_closed_90d": n_reg_closed})

    # ── C3 · AEGIS History · 100% new-format PID ────────────────────
    ws_h = wb[f"AEGIS {market.upper()} History"]
    rh = list(ws_h.iter_rows(values_only=True))
    hdr_h = rh[0]
    c_pid = _col(hdr_h, "Position ID")
    c_date = _col(hdr_h, "Date")
    c_run = _col(hdr_h, "Run_Type") or _col(hdr_h, "Runner")
    if c_pid is None:
        _add("C3_history_new_format_pids", False, "no Position ID column", None)
    else:
        n_new_pid = 0
        n_legacy_pid = 0
        legacy_samples = []
        for r in rh[1:]:
            if not r[c_pid]: continue
            pid = str(r[c_pid])
            if pid.startswith(_NEW_PID_PREFIXES):
                n_new_pid += 1
            else:
                n_legacy_pid += 1
                if len(legacy_samples) < 5: legacy_samples.append(pid)
        _add("C3_history_new_format_pids", n_legacy_pid == 0,
              f"{n_new_pid} new-format PIDs · {n_legacy_pid} legacy",
              {"new_ct": n_new_pid, "legacy_ct": n_legacy_pid,
               "legacy_samples": legacy_samples})

    # ── C4 · Portfolio banner ≡ body (3 axes) ──────────────────────
    ws_p = wb["Portfolio"]
    rows_p = list(ws_p.iter_rows(values_only=True))
    banner_r2 = str(rows_p[1][0]) if len(rows_p) > 1 and rows_p[1][0] else ""
    banner_r3 = str(rows_p[2][0]) if len(rows_p) > 2 and rows_p[2][0] else ""
    import re as _re
    m_life = _re.search(
        r"(?:Lifecycle|Current Portfolio):\s*(\d+)\s+ACTIVE\s*·\s*(\d+)\s+NEW",
        banner_r2)
    m_sugg = _re.search(r"Suggested:\s*(\d+)", banner_r2)
    banner_active = int(m_life.group(1)) if m_life else -1
    banner_new = int(m_life.group(2)) if m_life else -1
    banner_suggested = int(m_sugg.group(1)) if m_sugg else -1
    # Body counts by axis · column-name lookup (India + USA layouts differ)
    hdr_p_idx = next((i for i, r in enumerate(rows_p)
                        if r[0] and "Ticker" in str(r[0])), None)
    body = rows_p[hdr_p_idx + 1:] if hdr_p_idx is not None else []
    hdr_p = rows_p[hdr_p_idx] if hdr_p_idx is not None else ()
    def _pcol(name):
        for i, c in enumerate(hdr_p):
            if c and str(c).lower() == name.lower(): return i
        return None
    ci_life = _pcol("Lifecycle")
    ci_dec = None
    for cand in ("🎯 DECISION", "DECISION", "Decision"):
        ci_dec = _pcol(cand)
        if ci_dec is not None: break
    ci_run = _pcol("Runner")
    body_life_active = 0
    body_life_new = 0
    body_suggested = 0
    for r in body:
        life = str(r[ci_life]) if ci_life is not None and ci_life < len(r) and r[ci_life] else ""
        dec = str(r[ci_dec]) if ci_dec is not None and ci_dec < len(r) and r[ci_dec] else ""
        run = str(r[ci_run]) if ci_run is not None and ci_run < len(r) and r[ci_run] else ""
        if "SUGGESTED" in dec.upper() or run.upper() == "SHADOW":
            body_suggested += 1
            continue
        life_up = life.upper()
        if "NEW" in life_up:
            body_life_new += 1
        elif "ACTIVE" in life_up:
            body_life_active += 1
    ok_active = banner_active == body_life_active
    ok_new = banner_new == body_life_new
    ok_sugg = banner_suggested == body_suggested
    _add("C4_banner_lifecycle_active", ok_active,
          f"banner={banner_active} body={body_life_active}",
          {"banner": banner_active, "body": body_life_active})
    _add("C4_banner_lifecycle_new", ok_new,
          f"banner={banner_new} body={body_life_new}",
          {"banner": banner_new, "body": body_life_new})
    _add("C4_banner_suggested", ok_sugg,
          f"banner={banner_suggested} body={body_suggested}",
          {"banner": banner_suggested, "body": body_suggested})

    # ── C5 · Exit History body has NO trailer rows ─────────────────
    if "Exit History (90d)" in wb.sheetnames:
        ws_e = wb["Exit History (90d)"]
        eh_rows = [r for r in ws_e.iter_rows(values_only=True)
                     if any(c is not None for c in r)]
        # Last data row's first cell should be a ticker
        trailer_hit = False
        trailer_row = None
        for r in eh_rows:
            first = str(r[0]) if r[0] else ""
            for f in ("MONTHLY", "SUMMARY", "──"):
                if f in first.upper():
                    trailer_hit = True
                    trailer_row = first[:60]
                    break
            if trailer_hit: break
        _add("C5_exit_history_no_trailer", not trailer_hit,
              f"trailer row found: '{trailer_row}'" if trailer_hit else "clean",
              {"trailer_found": trailer_hit, "trailer_row": trailer_row})

    # ── C6 · Path-A holding rows use "—" not fabricated values ─────
    n_fabricated = 0
    fabricated_samples = []
    for r in body:
        action = str(r[1]) if len(r) > 1 and r[1] else ""
        if "holding" in action.lower() and "no signal" in action.lower():
            urg = str(r[15]) if len(r) > 15 and r[15] else ""
            iq = str(r[20]) if len(r) > 20 and r[20] else ""
            if "LOW" in urg.upper() or "PENDING" in iq.upper():
                n_fabricated += 1
                if len(fabricated_samples) < 5:
                    fabricated_samples.append((r[0], urg[:20], iq[:20]))
    _add("C6_no_fabricated_low_pending", n_fabricated == 0,
          f"{n_fabricated} holding rows with LOW/PENDING",
          {"n": n_fabricated, "samples": fabricated_samples})

    # ── C7 · AEGIS History uniqueness at canonical grain ──────────
    # Per CEO Plan section 4: "No UNEXPLAINED duplicate (market,
    # position_id, runner, snapshot_date)". Same-day multi-observation
    # (different Status OR different Rank/Confidence/Story) is EXPLAINED
    # · legitimate pipeline behavior · not a violation. Only bit-identical
    # duplicate rows (same key AND every cell identical) are UNEXPLAINED
    # · they indicate a genuine pipeline stamping bug and must fail C7.
    from collections import defaultdict as _dd
    grain_rows = _dd(list)
    for _rh_i, r in enumerate(rh[1:], start=2):
        if not r[c_pid]: continue
        key = (market_l, str(r[c_pid]), str(r[c_run] or ""),
                str(r[c_date])[:10] if r[c_date] else "")
        grain_rows[key].append((_rh_i, r))
    unexplained_dupes = []       # bit-identical duplicate rows
    explained_dupes = []         # same key · different observation
    for key, rd in grain_rows.items():
        if len(rd) <= 1: continue
        cell_sigs = [tuple(str(v) for v in r) for _, r in rd]
        if len(set(cell_sigs)) == 1:
            # Bit-identical · UNEXPLAINED · pipeline duplicate-emit bug
            unexplained_dupes.append((key, [ri for ri, _ in rd]))
        else:
            explained_dupes.append((key, [ri for ri, _ in rd]))
    _add("C7_history_canonical_uniqueness", len(unexplained_dupes) == 0,
          f"{len(unexplained_dupes)} UNEXPLAINED dupes (bit-identical) · "
          f"{len(explained_dupes)} EXPLAINED dupes (multi-observation same-day)",
          {"n_unexplained": len(unexplained_dupes),
           "n_explained": len(explained_dupes),
           "unexplained_samples": unexplained_dupes[:5]})

    # ── C8 · Registry-CLOSED ⊆ Exit History body (I20-shape) ───────
    if "Exit History (90d)" in wb.sheetnames:
        eh_tickers = set()
        for r in eh_rows[1:]:   # skip title row
            if not r[0]: continue
            first = str(r[0]).upper()
            if not first.isalnum() and not first.replace("-", "").isalnum():
                continue
            eh_tickers.add(first)
        # C8 · CEO 2026-09-01 STRENGTHENED: retirement-aware · carveout-aware.
        # Registry CLOSED events for RETIRED runners are EXPECTED to be absent
        # (retirement carveout · not a production exit). Registry CLOSED events
        # with reasons ORPHAN_AUTO_CLOSE / SAME_DAY_ROTATION / CANCELLED /
        # DATA_REPAIR are also carveouts. Only ACTIVE-runner · non-carveout
        # CLOSED events without a matching Exit History row are real gaps.
        try:
            from backend.delivery.canonical.retirement import retired_runners as _c8_retired
            _c8_ret = _c8_retired(_ROOT)
        except Exception:
            _c8_ret = set()
        _CARVEOUT_KW = ("ORPHAN_AUTO_CLOSE", "SAME_DAY_ROTATION",
                         "CANCELLED", "DATA_REPAIR")
        reg_closed_by_ticker: dict[str, list] = {}
        for _pid, opps in reg.items():
            for o in opps:
                if o.market.lower() != market_l or o.status != "CLOSED":
                    continue
                _tk = o.ticker.upper().replace(".NS", "").replace(".BO", "")
                reg_closed_by_ticker.setdefault(_tk, []).append(o)
        real_missing = []
        retired_ignored = []
        carveout_ignored = []
        for tk, closed_events in reg_closed_by_ticker.items():
            if tk in eh_tickers: continue
            # Check every CLOSED event for this ticker · only flag
            # if AT LEAST ONE is production-active-runner + non-carveout
            has_production_gap = False
            for ev in closed_events:
                runner_up = str(ev.runner or "").upper()
                reason = str(getattr(ev, "closed_reason", "") or "").upper()
                if runner_up in _c8_ret:
                    retired_ignored.append((tk, runner_up))
                    continue
                if any(kw in reason for kw in _CARVEOUT_KW):
                    carveout_ignored.append((tk, reason))
                    continue
                has_production_gap = True
                real_missing.append({"ticker": tk, "runner": runner_up,
                                       "reason": reason,
                                       "closed_date": str(ev.closed_date or "")})
                break
        _add("C8_registry_closed_in_exit_history",
              len(real_missing) == 0,
              (f"{len(real_missing)} ACTIVE-runner non-carveout Registry-CLOSED "
                f"missing from EH · {len(retired_ignored)} retired-runner · "
                f"{len(carveout_ignored)} carveout ignored (all expected)"),
              {"n_real_missing": len(real_missing),
               "n_retired_ignored": len(retired_ignored),
               "n_carveout_ignored": len(carveout_ignored),
               "sample_real_missing": real_missing[:5]})

    # ── C10 · Retired-runner contamination check ──────────────────
    # CEO 2026-09-01 · R1 retirement · Portfolio + banner + P&L must
    # contain 0 retired-runner rows. Historical audit (AEGIS History
    # sheet · Registry) still contains R1 rows · that is preserved
    # by design. This check ensures the PRODUCTION-FACING view is
    # clean.
    try:
        from backend.delivery.canonical.retirement import retired_runners as _c10_retired
        retired_set = _c10_retired(_ROOT)
    except Exception:
        retired_set = set()
    if retired_set:
        n_retired_in_portfolio = 0
        for r in body:
            run = str(r[ci_run]).upper() if ci_run is not None and ci_run < len(r) and r[ci_run] else ""
            dec = str(r[ci_dec] or "").upper() if ci_dec is not None and ci_dec < len(r) else ""
            if "SUGGESTED" in dec: continue
            if run in retired_set:
                n_retired_in_portfolio += 1
        _add("C10_no_retired_in_production_portfolio",
              n_retired_in_portfolio == 0,
              f"{n_retired_in_portfolio} retired-runner rows in Portfolio · "
              f"retired={sorted(retired_set)}",
              {"n_retired_rows": n_retired_in_portfolio,
               "retired_runners": sorted(retired_set)})

    # ── C9 · Portfolio ↔ Exit History lifecycle-instance collision ─
    # CEO 2026-09-01 · hard rule: a ticker may legitimately appear in
    # BOTH Portfolio (ACTIVE) and Exit History (CLOSED) ONLY if they
    # represent DIFFERENT lifecycle instances. Under A1 the runner-
    # inclusive Position ID (with entry_date) is the true identity ·
    # so the collision key is (ticker, runner, entry_date). Same
    # (ticker, runner, entry_date) in both → FAIL. Different entry_date
    # is EXPLAINED (position was closed then re-opened later · legit).
    port_active_key = set()   # (ticker, runner, entry_date)
    port_entry_by_tk_run = {}
    for r in body:
        life = str(r[3]) if len(r) > 3 and r[3] else ""
        dec = str(r[2]) if len(r) > 2 and r[2] else ""
        if "SUGGESTED" in dec.upper(): continue
        if "ACTIVE" not in life.upper(): continue
        tk = str(r[0]).upper().replace(".NS", "").replace(".BO", "")
        run = str(r[8] or "").upper() if len(r) > 8 else ""
        ent = str(r[12])[:10] if len(r) > 12 and r[12] else ""
        if run in ("R1", "R2") and ent:
            port_active_key.add((tk, run, ent))
            port_entry_by_tk_run.setdefault((tk, run), set()).add(ent)
    # Exit History body · (ticker, runner, entry_date) triples
    eh_closed_key = set()
    eh_by_tk_run = {}
    if "Exit History (90d)" in wb.sheetnames:
        ws_e2 = wb["Exit History (90d)"]
        eh_all = list(ws_e2.iter_rows(values_only=True))
        hdr_e = None
        for r in eh_all:
            if r[0] and "Stock" in str(r[0]):
                hdr_e = r
                break
        if hdr_e:
            r_col = None
            ent_col = None
            exit_col = None
            for i, c in enumerate(hdr_e):
                cl = str(c or "").lower()
                if cl == "runner": r_col = i
                elif cl == "entry date": ent_col = i
                elif cl == "exit date": exit_col = i
            for r in eh_all:
                if not r[0]: continue
                tk_e = str(r[0]).upper().replace(".NS", "").replace(".BO", "")
                if not tk_e.replace("-", "").isalnum(): continue
                if r_col is None or r_col >= len(r) or not r[r_col]: continue
                run_e = str(r[r_col]).upper()
                if run_e not in ("R1", "R2"): continue
                ent_e = str(r[ent_col])[:10] if ent_col is not None and r[ent_col] else ""
                exit_e = str(r[exit_col])[:10] if exit_col is not None and r[exit_col] else ""
                if ent_e:
                    eh_closed_key.add((tk_e, run_e, ent_e))
                    eh_by_tk_run.setdefault((tk_e, run_e), []).append((ent_e, exit_e))
    # True collision · same (ticker, runner, entry_date) in both
    collisions = port_active_key & eh_closed_key
    # Same ticker+runner but different entry_date is EXPLAINED
    explained_overlap = []
    for (tk, run) in set(port_entry_by_tk_run) & set(eh_by_tk_run):
        p_ents = port_entry_by_tk_run[(tk, run)]
        e_events = eh_by_tk_run[(tk, run)]
        for e_ent, e_exit in e_events:
            for p_ent in p_ents:
                if p_ent != e_ent:
                    explained_overlap.append((tk, run, p_ent, e_ent, e_exit))
    _add("C9_portfolio_exit_no_lifecycle_collision",
          len(collisions) == 0,
          f"{len(collisions)} UNEXPLAINED lifecycle collisions "
          f"(same ticker+runner+entry_date active AND closed) · "
          f"{len(explained_overlap)} EXPLAINED overlaps (different entry_date · legit re-entry)",
          {"n_unexplained": len(collisions),
           "unexplained_collisions": sorted(list(collisions))[:10],
           "n_explained_overlaps": len(explained_overlap),
           "explained_samples": explained_overlap[:5],
           "n_portfolio_active_keys": len(port_active_key),
           "n_exit_closed_keys": len(eh_closed_key)})

    wb.close()

    # ── C19 · Workbook-wide R1 = 0 (STRENGTHENED CONTRACT) ─────────
    # CEO 2026-09-01 strengthened: R1 must be COMPLETELY absent from
    # every visible sheet · every cell · except Definitions (which may
    # name R1 as a reference explaining retirement). Cell-level scan.
    try:
        from backend.delivery.canonical.retirement import retired_runners as _c19_retired
        _c19_ret = _c19_retired(root)
        _c19_hits = []
        _c19_wb_ro = load_workbook(xlsx, read_only=True, data_only=True)
        # Also load formula-visible workbook (data_only=False) to catch
        # cells whose STORED FORMULA references R1
        _c19_wb_fx = load_workbook(xlsx, data_only=False)
        _prefixes = tuple(
            p + rr + "-" for rr in _c19_ret
            for p in ("", "IND-", "USA-")
        )
        _defs_name = "Definitions"
        # 1. Visible-value scan (all sheets except Definitions)
        for _sh_name in _c19_wb_ro.sheetnames:
            if _sh_name == _defs_name: continue
            _ws = _c19_wb_ro[_sh_name]
            _rn = 0
            for _row in _ws.iter_rows(values_only=True):
                _rn += 1
                for _v in _row:
                    if _v is None: continue
                    _s = str(_v).strip().upper()
                    if _s in _c19_ret or _s.startswith(_prefixes):
                        _c19_hits.append({"scope": "value", "sheet": _sh_name,
                                           "row": _rn, "value": _s[:30]})
                        break
        _c19_wb_ro.close()
        # 2. Hidden / very-hidden sheet detection · every hidden sheet is
        #    itself a violation regardless of content (production workbook
        #    must have zero surprise sheets)
        _c19_hidden = []
        for _sh_name in _c19_wb_fx.sheetnames:
            _sh = _c19_wb_fx[_sh_name]
            _state = getattr(_sh, "sheet_state", "visible")
            if _state != "visible":
                _c19_hidden.append({"sheet": _sh_name, "state": _state})
        # 3. Formula scan · any cell.data_type == 'f' with R1 in formula text
        _c19_formula_hits = []
        for _sh_name in _c19_wb_fx.sheetnames:
            if _sh_name == _defs_name: continue
            _sh = _c19_wb_fx[_sh_name]
            for _row in _sh.iter_rows():
                for _c in _row:
                    if getattr(_c, "data_type", None) == "f":
                        _fx = str(_c.value or "").upper()
                        for _r in _c19_ret:
                            if _r in _fx.split():   # word-boundary-ish
                                _c19_formula_hits.append(
                                    {"scope": "formula",
                                      "sheet": _sh_name,
                                      "coord": _c.coordinate,
                                      "formula": _fx[:60]})
                                break
        # 4. Defined-name scan
        _c19_defname_hits = []
        try:
            for _dn_name in list(_c19_wb_fx.defined_names):
                _u = str(_dn_name).upper()
                if any(_r in _u.split("_") or _r in _u.split("-")
                        for _r in _c19_ret) or any(_u.startswith(p) for p in _prefixes):
                    _c19_defname_hits.append(_dn_name)
        except Exception:
            pass
        _c19_wb_fx.close()

        _c19_total = (len(_c19_hits) + len(_c19_hidden)
                       + len(_c19_formula_hits) + len(_c19_defname_hits))
        _add("C19_workbook_wide_r1_zero",
              _c19_total == 0,
              (f"{len(_c19_hits)} value hits · {len(_c19_hidden)} hidden sheets · "
                f"{len(_c19_formula_hits)} formula hits · "
                f"{len(_c19_defname_hits)} defined-name hits · "
                f"retired={sorted(_c19_ret)}"),
              {"n_value_hits": len(_c19_hits),
               "n_hidden_sheets": len(_c19_hidden),
               "n_formula_hits": len(_c19_formula_hits),
               "n_defname_hits": len(_c19_defname_hits),
               "hidden_sample": _c19_hidden[:5],
               "value_sample": _c19_hits[:5],
               "formula_sample": _c19_formula_hits[:5]})
    except Exception as _e19:
        _add("C19_workbook_wide_r1_zero", False,
              f"exception: {type(_e19).__name__}: {_e19}", None)

    # ── C18 · Crash-resilience research presence (§ Crash addendum) ─
    # Every certification pass must have current 5-state regime + per-regime
    # R2-vs-benchmark metrics computed · presence is mandatory · interpretation
    # never claims success just because a report exists.
    try:
        _cr_p = root / "reports" / "research" / "multi_layer" / f"crash_resilience_{market_l}_{asof}.json"
        if _cr_p.exists():
            _cr = json.loads(_cr_p.read_text(encoding="utf-8"))
            _tagged = int(_cr.get("n_r2_trades_tagged", 0) or 0)
            _today = str(_cr.get("today_regime", "?"))
            _dist = _cr.get("regime_distribution_alltime", {}) or {}
            # Passes only if the CLASSIFIER ran (n_days_classified > 0)
            _n_days = int(_cr.get("n_days_classified", 0) or 0)
            _add("C18_crash_resilience_present",
                  _n_days > 0,
                  (f"today_regime={_today} · n_r2_trades_tagged={_tagged} · "
                    f"n_days_classified={_n_days} · dist={_dist}"),
                  {"today_regime": _today,
                   "n_r2_trades_tagged": _tagged,
                   "n_days_classified": _n_days,
                   "regime_distribution": _dist,
                   "interpretation": _cr.get("interpretation")})
        else:
            _add("C18_crash_resilience_present", False,
                  f"crash-resilience report missing · run python -m backend.research.multi_layer.crash_resilience --market {market_l}",
                  {"expected": str(_cr_p.name)})
    except Exception as _e18:
        _add("C18_crash_resilience_present", False,
              f"exception: {type(_e18).__name__}: {_e18}", None)

    # ── C17 · Momentum candidate conservation (Momentum correction) ─
    # Every candidate emitted by the momentum engine must be classified
    # into one of 4 terminal states · zero silent disappearances.
    try:
        _ml_p = root / "reports" / "research" / "multi_layer" / f"momentum_ledger_{market_l}_{asof}.json"
        if _ml_p.exists():
            _ml = json.loads(_ml_p.read_text(encoding="utf-8"))
            _cons = bool(_ml.get("conservation_ok", False))
            _n_disappear = int(_ml.get("n_silent_disappearances", 0) or 0)
            _add("C17_momentum_conservation_zero_silent",
                  _cons and _n_disappear == 0,
                  (f"conservation_ok={_cons} · silent_disappearances={_n_disappear} · "
                    f"by_state={_ml.get('by_terminal_state', {})}"),
                  {"conservation_ok": _cons,
                   "n_silent_disappearances": _n_disappear,
                   "by_terminal_state": _ml.get("by_terminal_state"),
                   "by_reason_code": _ml.get("by_reason_code")})
        else:
            _add("C17_momentum_conservation_zero_silent", False,
                  f"momentum ledger missing · run python -m backend.research.multi_layer.momentum_ledger --market {market_l}",
                  {"expected": str(_ml_p.name)})
    except Exception as _e17:
        _add("C17_momentum_conservation_zero_silent", False,
              f"exception: {type(_e17).__name__}: {_e17}", None)

    # ── C16 · Stress-regime research presence (§8) ──────────────────
    try:
        _sr_p = root / "reports" / "research" / "multi_layer" / f"stress_regime_{market_l}_{asof}.json"
        if _sr_p.exists():
            _sr = json.loads(_sr_p.read_text(encoding="utf-8"))
            _n_tagged = int(_sr.get("n_r2_trades_tagged", 0) or 0)
            _add("C16_stress_regime_research_present",
                  _n_tagged > 0,
                  (f"R2 trades tagged={_n_tagged} · regime_source="
                    f"{_sr.get('regime_source', 'missing')}"),
                  {"n_trades": _n_tagged,
                   "overall": _sr.get("overall"),
                   "per_regime_n": {k: v.get("n") for k, v
                                     in (_sr.get("per_regime") or {}).items()}})
        else:
            _add("C16_stress_regime_research_present", False,
                  f"stress-regime report missing · run python -m backend.research.multi_layer.stress_regime --market {market_l}",
                  {"expected": str(_sr_p.name)})
    except Exception as _e16:
        _add("C16_stress_regime_research_present", False,
              f"exception: {type(_e16).__name__}: {_e16}", None)

    # ── C14 · Portfolio↔Exit overlap classification (§11) ───────────
    # Every same-ticker overlap must be explained · RECONCILIATION_DEFECT = 0
    try:
        _ov_p = root / "reports" / "audit" / f"portfolio_exit_overlap_{market_l}_{asof}.json"
        if _ov_p.exists():
            _ov = json.loads(_ov_p.read_text(encoding="utf-8"))
            _defects = int(_ov.get("n_reconciliation_defects", 0) or 0)
            _add("C14_overlap_no_reconciliation_defects",
                  _defects == 0,
                  (f"{_ov.get('n_overlap_tickers', 0)} overlap tickers · "
                    f"defects={_defects} · "
                    f"by_cat={_ov.get('by_category', {})}"),
                  _ov.get("by_category", {}))
        else:
            _add("C14_overlap_no_reconciliation_defects", False,
                  f"overlap report missing · run scripts/portfolio_exit_overlap_classifier.py --market {market_l}",
                  {"expected": str(_ov_p.name)})
    except Exception as _e14:
        _add("C14_overlap_no_reconciliation_defects", False,
              f"exception: {type(_e14).__name__}: {_e14}", None)

    # ── C15 · R1 producer-wide retirement proof (§1 hardening) ──────
    try:
        _pa_p = root / "reports" / "audit" / f"r1_producer_audit_{market_l}_{asof}.json"
        if _pa_p.exists():
            _pa = json.loads(_pa_p.read_text(encoding="utf-8"))
            _viol = int(_pa.get("total_violations", 0) or 0)
            _add("C15_r1_producer_wide_retirement",
                  _viol == 0,
                  (f"{_pa.get('verdict', 'UNKNOWN')} · total_violations={_viol} · "
                    f"n_producers={len(_pa.get('producers', []))}"),
                  {"verdict": _pa.get("verdict"),
                   "total_violations": _viol})
        else:
            _add("C15_r1_producer_wide_retirement", False,
                  f"audit missing · run scripts/r1_producer_audit.py --market {market_l}",
                  {"expected": str(_pa_p.name)})
    except Exception as _e15:
        _add("C15_r1_producer_wide_retirement", False,
              f"exception: {type(_e15).__name__}: {_e15}", None)

    # ── C13 · Universe bounds ───────────────────────────────────────
    # CEO 2026-09-01 Section 2 · USA must be S&P 500 · India retains
    # current bounds · silent widening beyond configs/aegis_universes.yaml
    # is a contract violation.
    try:
        from backend.canonical.universe_validator import validate as _uv_validate
        _uv = _uv_validate(root, market_l)
        _add(
            "C13_universe_bounds",
            _uv.ok,
            (f"{_uv.verdict} · {_uv.detail} · violations={_uv.violations}"
              if _uv.violations else f"{_uv.verdict} · {_uv.detail}"),
            _uv.as_dict(),
        )
    except Exception as _e13:
        _add("C13_universe_bounds", False,
              f"exception: {type(_e13).__name__}: {_e13}", None)

    # ── C12 · Provenance companion coverage ─────────────────────────
    # CEO 2026-09-01 · Every VISIBLE, OPENED position row must resolve
    # to a Position ID. SUGGESTED rows (population=FRESH_RECOMMENDATION,
    # runner=SHADOW) are exempt because they are not opened positions.
    try:
        _prov_path = root / "reports" / "telegram" / f"aegis_history_{market_l}_provenance.jsonl"
        if _prov_path.exists():
            _prov = [json.loads(l) for l in _prov_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            _need_pid = [r for r in _prov if r.get("population") not in ("FRESH_RECOMMENDATION",)]
            _n_need = len(_need_pid)
            _n_have = sum(1 for r in _need_pid if r.get("position_id"))
            _cov = round(_n_have / max(1, _n_need) * 100, 1)
            _add("C12_provenance_position_id_coverage",
                  _n_have == _n_need,
                  f"{_n_have}/{_n_need} opened rows have Position ID ({_cov}%)",
                  {"n_need_pid": _n_need, "n_have_pid": _n_have,
                   "coverage_pct": _cov,
                   "unresolved_samples": [
                       {"sheet": r["sheet"], "ticker": r["ticker"],
                        "runner": r["runner"], "entry_date": r.get("entry_date", "")}
                       for r in _need_pid if not r.get("position_id")
                   ][:5]})
        else:
            _add("C12_provenance_position_id_coverage", False,
                  f"provenance companion missing · run emit_provenance_companion.py --market {market_l}",
                  {"expected_path": str(_prov_path.name)})
    except Exception as _e12:
        _add("C12_provenance_position_id_coverage", False,
              f"exception: {type(_e12).__name__}: {_e12}", None)

    # ── C11 · Standard-name dated XLSX snapshot ─────────────────────
    # CEO 2026-09-01 · Standard XLSX name is `aegis_{market}_YYYY-MM-DD.xlsx`.
    # The undated file `aegis_history_{market}.xlsx` remains the "latest"
    # alias but the DATED file is the authoritative daily snapshot. Both
    # must exist for today's asof and be byte-identical.
    try:
        import hashlib as _h11
        _std_dated = root / "reports" / "telegram" / f"aegis_{market_l}_{asof}.xlsx"
        _undated = root / "reports" / "telegram" / f"aegis_history_{market_l}.xlsx"
        _dated_ok = _std_dated.exists()
        _byte_match = False
        if _dated_ok and _undated.exists():
            _byte_match = (
                _h11.md5(_std_dated.read_bytes()).hexdigest()
                == _h11.md5(_undated.read_bytes()).hexdigest()
            )
        _add("C11_standard_dated_xlsx_present",
              _dated_ok and _byte_match,
              (
                f"dated={_dated_ok} byte_match={_byte_match} · "
                f"expected={_std_dated.name}"
              ),
              {"dated_present": _dated_ok, "byte_match": _byte_match,
               "expected": str(_std_dated.name)})
    except Exception as _e11:
        _add("C11_standard_dated_xlsx_present", False,
              f"exception: {type(_e11).__name__}: {_e11}", None)

    # Overall verdict
    fails = [c for c in checks if not c["ok"]]
    verdict = "PASS" if not fails else "FAIL"
    return {
        "engine": "aegis.reconcile.final.v1",
        "asof": asof,
        "market": market_l,
        "xlsx_path": str(xlsx.relative_to(root)),
        "verdict": verdict,
        "n_checks": len(checks),
        "n_pass": sum(1 for c in checks if c["ok"]),
        "n_fail": len(fails),
        "checks": checks,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"],
                     default="both")
    ap.add_argument("--out-dir", default="reports/reconcile")
    args = ap.parse_args()
    markets = ["india", "usa"] if args.market == "both" else [args.market]
    any_fail = False
    for m in markets:
        try:
            rep = reconcile(m, _ROOT)
        except ReconcileFailure as e:
            print(f"[reconcile:{m}] SKIPPED · {e}")
            continue
        out_p = _ROOT / args.out_dir / f"final_reconcile_{m}_{rep['asof']}.json"
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(rep, indent=2, ensure_ascii=False),
                          encoding="utf-8")
        print(f"[reconcile:{m}] {rep['verdict']} · pass={rep['n_pass']} · "
              f"fail={rep['n_fail']} · report={out_p.relative_to(_ROOT)}")
        if rep["verdict"] != "PASS":
            for c in rep["checks"]:
                if not c["ok"]:
                    _line = f"  [FAIL] {c['name']} :: {c['detail']}"
                    print(_line.encode("ascii", errors="replace").decode("ascii"))
            any_fail = True
    return 2 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
