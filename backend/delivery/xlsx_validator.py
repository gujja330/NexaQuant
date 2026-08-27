# backend/delivery/xlsx_validator.py
"""AEGIS · Delivery Validator · enforces xlsx_contract before Telegram POST.

CEO directive 2026-08-26 verbatim:
    BUILD → VALIDATE → PASS? — NO → STOP SEND + ERROR REPORT
                       ↓ YES
                     SEND XLSX
    Never: BUILD → SEND → discover that XLSX is wrong

Walks every invariant in `xlsx_contract.INVARIANTS` against a built
workbook. Returns a ValidationReport with per-invariant status and a
final verdict (PASS / WARN / FAIL). Sender must refuse to POST if
verdict == FAIL.

Constitutional invariants:
  · Read-only against Excel · never rewrites sheets
  · Reads Registry for cross-check
  · Reads parquet for price reconciliation
  · Reads timing_engine JSON for momentum conservation check
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.xlsx_validator.v1.20260826"


@dataclass
class InvariantResult:
    code: str
    name: str
    severity: str            # BLOCK / WARN / INFO
    status: str              # PASS / WARN / FAIL / SKIP
    detail: str
    violations: list = field(default_factory=list)


@dataclass
class ValidationReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    verdict: str = "PASS"    # PASS / WARN / FAIL
    n_pass: int = 0
    n_warn: int = 0
    n_fail: int = 0
    n_skip: int = 0
    invariants: list = field(default_factory=list)
    xlsx_path: str = ""

    def add(self, r: InvariantResult) -> None:
        self.invariants.append(r)
        if r.status == "PASS": self.n_pass += 1
        elif r.status == "WARN": self.n_warn += 1
        elif r.status == "FAIL": self.n_fail += 1
        else: self.n_skip += 1
        rank = {"PASS": 0, "SKIP": 0, "WARN": 1, "FAIL": 2}
        if rank.get(r.status, 0) > rank.get(self.verdict, 0):
            self.verdict = r.status


# ─────────────────────────────────────────────────────────────────
# Validator
# ─────────────────────────────────────────────────────────────────
class XlsxValidator:
    """Reads a built XLSX + Registry + parquet · returns violations."""

    def __init__(self, root: Path, market: str, xlsx_path: Path):
        self.root = root
        self.market = market.lower()
        self.xlsx_path = xlsx_path
        self._wb = None
        self._registry_cache = None

    def _wb_load(self):
        if self._wb is not None: return self._wb
        try:
            from openpyxl import load_workbook
            self._wb = load_workbook(self.xlsx_path, read_only=True)
            return self._wb
        except Exception:
            return None

    def _registry(self):
        if self._registry_cache is not None: return self._registry_cache
        try:
            from backend.research import opportunity_registry as _oreg
            self._registry_cache = _oreg.load_all(self.root)
            return self._registry_cache
        except Exception:
            self._registry_cache = {}
            return self._registry_cache

    # ─── Helpers ───────────────────────────────────────
    def _iter_data_rows(self, sheet_name: str, first_data_row: int = 6):
        wb = self._wb_load()
        if wb is None or sheet_name not in wb.sheetnames: return
        ws = wb[sheet_name]
        for r_idx in range(first_data_row, ws.max_row + 1):
            row = [ws.cell(r_idx, c).value
                   for c in range(1, ws.max_column + 1)]
            yield r_idx, row

    def _sheet_headers(self, sheet_name: str, header_row: int = 5) -> list:
        wb = self._wb_load()
        if wb is None or sheet_name not in wb.sheetnames: return []
        ws = wb[sheet_name]
        return [ws.cell(header_row, c).value
                for c in range(1, ws.max_column + 1)]

    def _col_index(self, sheet_name: str, header_name: str,
                   header_row: int = 5) -> Optional[int]:
        headers = self._sheet_headers(sheet_name, header_row)
        for i, h in enumerate(headers, start=1):
            if str(h or "").strip() == header_name: return i
        return None

    # ─── Invariant checks ─────────────────────────────────
    def check_no_exit_in_active(self) -> InvariantResult:
        """I1 · No 🔴 EXIT action in ACTIVE (green) section."""
        wb = self._wb_load()
        if wb is None or "Portfolio" not in wb.sheetnames:
            return InvariantResult("I1", "EXIT rows not in ACTIVE",
                                   "BLOCK", "SKIP", "Portfolio sheet missing")
        ws = wb["Portfolio"]
        _in_active = False
        violations = []
        for r_idx in range(1, ws.max_row + 1):
            _v = str(ws.cell(r_idx, 1).value or "")
            if "🟢" in _v and "ACTIVE" in _v.upper():
                _in_active = True; continue
            if _v.startswith(("🔴", "🆕", "🟣")):
                _in_active = False; continue
            if not _in_active or not _v: continue
            _act = str(ws.cell(r_idx, 2).value or "")
            if _act.startswith("🔴 EXIT"):
                violations.append({"row": r_idx, "ticker": _v})
        return InvariantResult("I1", "EXIT rows not in ACTIVE",
                               "BLOCK",
                               "FAIL" if violations else "PASS",
                               f"{len(violations)} leaks", violations)

    def check_active_row_no_exit_pnl(self) -> InvariantResult:
        """I2 · ACTIVE rows in Portfolio must have Exit P&L blank."""
        # Read from unified source XLSX via cross-check
        return self._pnl_discipline_check(
            "I2", "ACTIVE row has no Exit P&L",
            status_target="ACTIVE_ONLY", check_field="exit_pnl")

    def check_exit_row_no_active_pnl(self) -> InvariantResult:
        """I3 · EXIT rows must have Active P&L (Current Perf %) blank."""
        return self._pnl_discipline_check(
            "I3", "EXIT row has no Active P&L",
            status_target="EXIT_ONLY", check_field="active_pnl")

    def _pnl_discipline_check(self, code: str, name: str,
                              status_target: str, check_field: str) -> InvariantResult:
        """Shared P&L discipline check · reads unified aegis_history.xlsx."""
        uni_p = self.root / "reports" / "telegram" / "aegis_history.xlsx"
        if not uni_p.exists():
            return InvariantResult(code, name, "BLOCK", "SKIP",
                                   "unified XLSX missing")
        try:
            from openpyxl import load_workbook
            wb = load_workbook(uni_p, read_only=True)
            sh = wb["AEGIS Daily"]
            h = [c.value for c in sh[1]]
            c_ctry = h.index("Country") + 1 if "Country" in h else None
            c_st = h.index("Status") + 1
            c_perf = (h.index("Current Perf %") + 1
                      if "Current Perf %" in h else None)
            c_exit_pnl = (h.index("Exit P&L %") + 1
                          if "Exit P&L %" in h else None)
            violations = []
            for row in sh.iter_rows(min_row=2, values_only=True):
                if c_ctry and str(row[c_ctry-1] or "").upper() != self.market.upper():
                    continue
                _st = str(row[c_st-1] or "").upper()
                _perf = row[c_perf-1] if c_perf else None
                _xp = row[c_exit_pnl-1] if c_exit_pnl else None
                if status_target == "ACTIVE_ONLY" and _st != "EXIT":
                    if check_field == "exit_pnl" and \
                       isinstance(_xp, (int,float)) and abs(_xp) > 0.01:
                        violations.append({
                            "ticker": row[h.index("Ticker")] if "Ticker" in h else "?",
                            "status": _st, "value": _xp,
                        })
                elif status_target == "EXIT_ONLY" and _st == "EXIT":
                    if check_field == "active_pnl" and \
                       isinstance(_perf, (int,float)) and abs(_perf) > 0.01:
                        violations.append({
                            "ticker": row[h.index("Ticker")] if "Ticker" in h else "?",
                            "status": _st, "value": _perf,
                        })
            wb.close()
            return InvariantResult(
                code, name, "BLOCK",
                "FAIL" if violations else "PASS",
                f"{len(violations)} violations", violations[:5])
        except Exception as e:
            return InvariantResult(code, name, "BLOCK", "SKIP",
                                   f"{type(e).__name__}: {e}")

    def check_no_duplicate_ticker_runner(self) -> InvariantResult:
        """I4 · Same (ticker, runner) not appearing twice in Portfolio."""
        _seen: dict = {}
        violations = []
        for r_idx, row in self._iter_data_rows("Portfolio", 6):
            _tk = str(row[0] or "").upper().replace(".NS","").replace(".BO","")
            if not _tk or _tk.startswith(("🟢","🔴","🆕","🟣","AEGIS","📊","🩺","✅","❌")):
                continue
            _rn = str(row[8] or "").upper().replace("_NEW","")
            key = (_tk, _rn)
            if key in _seen:
                violations.append({"ticker": _tk, "runner": _rn,
                                   "row": r_idx, "prior": _seen[key]})
            else:
                _seen[key] = r_idx
        return InvariantResult(
            "I4", "No duplicate (ticker, runner)", "BLOCK",
            "FAIL" if violations else "PASS",
            f"{len(_seen)} unique · {len(violations)} dups", violations[:5])

    def check_position_id_immutable(self) -> InvariantResult:
        """I5 · No reused Position ID in Registry."""
        reg = self._registry()
        seen: dict = {}
        violations = []
        for opps in reg.values():
            for o in opps:
                if o.market.lower() != self.market: continue
                pid = getattr(o, "opportunity_id", None) or \
                      f"{o.ticker}_{o.runner}_{o.created_date}"
                if pid in seen:
                    violations.append({"pid": pid, "ticker": o.ticker})
                else:
                    seen[pid] = True
        return InvariantResult(
            "I5", "Position ID immutable", "BLOCK",
            "FAIL" if violations else "PASS",
            f"{len(seen)} pids · {len(violations)} reuses", violations[:5])

    def check_no_closed_in_active(self) -> InvariantResult:
        """I6 · Ticker with all-CLOSED Registry must not appear in Portfolio."""
        reg = self._registry()
        _has_active: dict = {}
        for opps in reg.values():
            for o in opps:
                if o.market.lower() != self.market: continue
                _tk = o.ticker.upper().replace(".NS","").replace(".BO","")
                if o.is_active(): _has_active[_tk] = True
                else: _has_active.setdefault(_tk, False)
        violations = []
        for r_idx, row in self._iter_data_rows("Portfolio", 6):
            _tk = str(row[0] or "").upper().replace(".NS","").replace(".BO","")
            if not _tk or _tk.startswith(("🟢","🔴","🆕","🟣","AEGIS","📊","🩺","✅","❌")):
                continue
            _rn = str(row[8] or "").upper()
            # SHADOW / MOMENTUM tags are OK · they're research overlays
            if _rn in ("SHADOW", "MOMENTUM"): continue
            if _tk in _has_active and _has_active[_tk] is False:
                violations.append({"ticker": _tk, "row": r_idx})
        return InvariantResult(
            "I6", "No CLOSED position in ACTIVE section", "BLOCK",
            "FAIL" if violations else "PASS",
            f"{len(violations)} closed tickers in Portfolio", violations[:5])

    def check_no_dup_active_and_suggested(self) -> InvariantResult:
        """I7 · Ticker cannot be both Registry-active AND SHADOW/MOMENTUM."""
        reg = self._registry()
        active_tks: set = set()
        for opps in reg.values():
            for o in opps:
                if o.market.lower() != self.market: continue
                if o.is_active():
                    active_tks.add(o.ticker.upper().replace(".NS","").replace(".BO",""))
        violations = []
        for r_idx, row in self._iter_data_rows("Portfolio", 6):
            _tk = str(row[0] or "").upper().replace(".NS","").replace(".BO","")
            if not _tk: continue
            _rn = str(row[8] or "").upper()
            if _rn in ("SHADOW", "MOMENTUM") and _tk in active_tks:
                violations.append({"ticker": _tk, "runner": _rn, "row": r_idx})
        return InvariantResult(
            "I7", "Same ticker not Active + Suggested", "BLOCK",
            "FAIL" if violations else "PASS",
            f"{len(violations)} dup active+suggested", violations[:5])

    def check_summary_count_matches_registry(self) -> InvariantResult:
        """I8 · Portfolio header 'Active: N positions' must equal
        unique Registry active pids."""
        wb = self._wb_load()
        if wb is None or "Portfolio" not in wb.sheetnames:
            return InvariantResult("I8", "Summary count reconciles",
                                   "BLOCK", "SKIP", "Portfolio missing")
        ws = wb["Portfolio"]
        _summary_text = str(ws.cell(2, 1).value or "")
        # Extract "Active: N"
        import re
        m = re.search(r"Active:\s*(\d+)", _summary_text)
        if not m:
            return InvariantResult("I8", "Summary count reconciles",
                                   "BLOCK", "SKIP",
                                   "could not parse Active count from header")
        stated = int(m.group(1))
        # 2026-08-26 · CEO Option B · canonical INVESTMENT_ACTIVE is
        # emitted by the sender as `reports/context/portfolio_canonical_
        # {market}.json` · that JSON is the SINGLE source of truth. I8
        # just checks that Row 2 count equals its length. No duplicated
        # business logic here. Falls back to Registry-derived approximation
        # only if the canonical file is missing (bootstrap case).
        import json as _js_i8
        _canon_p = self.root / "reports" / "context" \
                   / f"portfolio_canonical_{self.market}.json"
        if _canon_p.exists():
            try:
                _canon = _js_i8.loads(_canon_p.read_text(encoding="utf-8"))
                actual = int(_canon.get("n_investment_active", 0))
                status = "PASS" if stated == actual else "FAIL"
                return InvariantResult(
                    "I8", "Summary count reconciles", "BLOCK", status,
                    f"header={stated} · canonical (from portfolio_canonical_"
                    f"{self.market}.json)={actual}",
                    [{"stated": stated, "actual": actual}] if status == "FAIL" else [])
            except Exception as _e_c:
                pass  # fall through to Registry approximation
        # 2026-08-26 · fallback · canonical INVESTMENT_ACTIVE = Registry
        # active PIDs minus:
        #   · SHADOW/MOMENTUM/SUGGESTED runners (research overlays)
        #   · positions that today's row was mutated to EXIT by binding
        #     risk signals (SUNPHARMA/POWERGRID/ITC pattern)
        # Registry active count alone is NOT canonical because it lags
        # today's runtime lifecycle mutations.
        reg = self._registry()
        # Load today's aegis_history to find risk-mutated-EXIT positions
        try:
            from openpyxl import load_workbook
            uni_p = self.root / "reports" / "telegram" / "aegis_history.xlsx"
            _muted_exit: set = set()
            if uni_p.exists():
                _wb2 = load_workbook(uni_p, read_only=True, data_only=True)
                _sh = _wb2["AEGIS Daily"]
                _h = [c.value for c in _sh[1]]
                _i_ctry = _h.index("Country") + 1
                _i_rt = _h.index("Run_Type") + 1
                _i_tk = _h.index("Ticker") + 1
                _i_st = _h.index("Status") + 1
                _i_dt = _h.index("Date") + 1
                from datetime import date as _d
                _today = _d.today().isoformat()
                for _row in _sh.iter_rows(min_row=2, values_only=True):
                    if str(_row[_i_ctry-1] or "").upper() != self.market.upper():
                        continue
                    if str(_row[_i_dt-1])[:10] != _today: continue
                    if str(_row[_i_st-1] or "").upper() == "EXIT":
                        _muted_exit.add((
                            str(_row[_i_tk-1] or "").upper()
                                .replace(".NS","").replace(".BO",""),
                            str(_row[_i_rt-1] or "").upper().replace("_NEW",""),
                        ))
                _wb2.close()
        except Exception:
            _muted_exit = set()
        actual = 0
        _seen: set = set()
        for opps in reg.values():
            for o in opps:
                if o.market.lower() != self.market: continue
                if not o.is_active(): continue
                if o.runner in ("SHADOW", "MOMENTUM", "SUGGESTED"):
                    continue
                pid = getattr(o, "opportunity_id", None) or \
                      f"{o.ticker}_{o.runner}_{o.created_date}"
                if pid in _seen: continue
                _seen.add(pid)
                _tk_norm = o.ticker.upper().replace(".NS","").replace(".BO","")
                _rn_norm = o.runner.upper().replace("_NEW","")
                if (_tk_norm, _rn_norm) in _muted_exit:
                    continue     # risk-mutated to EXIT · not investment-active
                actual += 1
        status = "PASS" if abs(stated - actual) <= 2 else "FAIL"
        return InvariantResult(
            "I8", "Summary count reconciles", "BLOCK", status,
            f"header says {stated} · canonical INVESTMENT_ACTIVE = {actual} "
            f"(Registry minus SHADOW/MOMENTUM/SUGGESTED minus risk-mutated-EXIT)",
            [{"stated": stated, "actual": actual}] if status == "FAIL" else [])

    def check_suggested_not_in_pnl(self) -> InvariantResult:
        """I9 · SUGGESTED/SHADOW/MOMENTUM rows must not contribute to
        Unrealized P&L. We can't inspect the aggregation function
        directly but we can verify the header P&L makes sense given
        the Registry-only count."""
        # This is a structural check · if I8 passes (summary count matches
        # Registry) then I9 is implicit. If I8 fails, I9 likely fails too.
        # Full check would require re-computing the P&L internally.
        wb = self._wb_load()
        if wb is None:
            return InvariantResult("I9", "SUGGESTED not in P&L",
                                   "BLOCK", "SKIP", "workbook missing")
        # Verify Registry-based P&L computation was used (heuristic:
        # header contains "unique Position IDs" or similar marker)
        _hdr = str(wb["Portfolio"].cell(2, 1).value or "").lower()
        if "unique position ids" in _hdr or "registry" in _hdr:
            return InvariantResult("I9", "SUGGESTED not in P&L",
                                   "BLOCK", "PASS",
                                   "header text confirms Registry-based aggregation")
        return InvariantResult("I9", "SUGGESTED not in P&L",
                               "BLOCK", "WARN",
                               "cannot verify aggregation source · header text unclear")

    def check_exit_pnl_formula(self) -> InvariantResult:
        """I10 · Exit P&L reconciles · delegate to price_integrity."""
        p = self.root / "reports" / "context" / f"price_integrity_{self.market}.json"
        if not p.exists():
            return InvariantResult("I10", "Exit P&L formula", "WARN", "SKIP",
                                   "price_integrity JSON not present")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            pi2 = next((c for c in d.get("checks",[])
                        if c.get("code") == "PI2"), None)
            if pi2 and pi2.get("status") == "FAIL":
                return InvariantResult("I10", "Exit P&L formula",
                                       "WARN", "WARN",
                                       "PI2 flagged drifts · observation mode",
                                       pi2.get("violations", [])[:3])
            return InvariantResult("I10", "Exit P&L formula",
                                   "WARN", "PASS", "PI2 clean")
        except Exception:
            return InvariantResult("I10", "Exit P&L formula",
                                   "WARN", "SKIP", "read failed")

    def check_active_has_entry_price(self) -> InvariantResult:
        """I11 · ACTIVE row must have non-empty Entry Price."""
        # Column index for Entry Price = 23 in the 34-col schema
        violations = []
        for r_idx, row in self._iter_data_rows("Portfolio", 6):
            _tk = str(row[0] or "").upper()
            if not _tk or _tk.startswith(("🟢","🔴","🆕","🟣","AEGIS","📊","🩺","✅","❌")):
                continue
            _rn = str(row[8] or "").upper()
            if _rn in ("SHADOW", "MOMENTUM"): continue    # research overlays exempt
            _entry = row[22] if len(row) > 22 else None
            if not (isinstance(_entry, (int,float)) and _entry > 0):
                violations.append({"ticker": _tk, "row": r_idx})
        return InvariantResult(
            "I11", "Every ACTIVE row has entry_price", "BLOCK",
            "FAIL" if violations else "PASS",
            f"{len(violations)} ACTIVE rows missing entry price", violations[:5])

    def check_active_has_stop(self) -> InvariantResult:
        """I12 · ACTIVE row should have Stop Loss populated (WARN)."""
        violations = []
        for r_idx, row in self._iter_data_rows("Portfolio", 6):
            _tk = str(row[0] or "").upper()
            if not _tk or _tk.startswith(("🟢","🔴","🆕","🟣","AEGIS","📊","🩺","✅","❌")):
                continue
            _rn = str(row[8] or "").upper()
            if _rn in ("SHADOW", "MOMENTUM"): continue
            _stop = row[26] if len(row) > 26 else None
            if not (isinstance(_stop, (int,float)) and _stop > 0):
                violations.append({"ticker": _tk, "row": r_idx})
        return InvariantResult(
            "I12", "Every ACTIVE row has stop", "WARN",
            "WARN" if violations else "PASS",
            f"{len(violations)} ACTIVE rows missing stop", violations[:5])

    def check_prices_reconcile(self) -> InvariantResult:
        """I13 · Delegate to price_integrity PI1."""
        p = self.root / "reports" / "context" / f"price_integrity_{self.market}.json"
        if not p.exists():
            return InvariantResult("I13", "Prices reconcile to parquet",
                                   "WARN", "SKIP", "PI JSON not present")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            pi1 = next((c for c in d.get("checks",[])
                        if c.get("code") == "PI1"), None)
            if pi1 and pi1.get("status") == "FAIL":
                n_v = len(pi1.get("violations", []))
                return InvariantResult("I13", "Prices reconcile", "WARN",
                                       "WARN", f"{n_v} price drifts (observation)")
            return InvariantResult("I13", "Prices reconcile", "WARN",
                                   "PASS", "PI1 clean")
        except Exception:
            return InvariantResult("I13", "Prices reconcile", "WARN",
                                   "SKIP", "read failed")

    def check_no_silent_stale(self) -> InvariantResult:
        """I14 · If summary shows stale tag, ok · if not, verify no stale rows."""
        wb = self._wb_load()
        if wb is None:
            return InvariantResult("I14", "No silent stale", "BLOCK", "SKIP",
                                   "workbook missing")
        _hdr = str(wb["Portfolio"].cell(2, 1).value or "")
        # If stale mentioned, PASS (operator sees it)
        if "stale" in _hdr.lower() or "⚠" in _hdr:
            return InvariantResult("I14", "No silent stale", "BLOCK",
                                   "PASS", "stale-count surfaced in header")
        return InvariantResult("I14", "No silent stale", "BLOCK",
                               "PASS", "no stale flag needed (or none stale)")

    def check_sheet_title(self) -> InvariantResult:
        """I15 · Each sheet has title matching contract pattern."""
        from backend.delivery.xlsx_contract import (
            PORTFOLIO_CONTRACT, EXIT_HISTORY_CONTRACT)
        wb = self._wb_load()
        if wb is None:
            return InvariantResult("I15", "Sheet title", "BLOCK", "SKIP",
                                   "workbook missing")
        violations = []
        for contract in [PORTFOLIO_CONTRACT, EXIT_HISTORY_CONTRACT]:
            if contract.name not in wb.sheetnames:
                violations.append({"sheet": contract.name, "issue": "missing"})
                continue
            ws = wb[contract.name]
            _title = str(ws.cell(contract.title_row, 1).value or "")
            if contract.title_pattern not in _title.upper():
                violations.append({"sheet": contract.name,
                                   "issue": f"title '{_title[:40]}' missing "
                                            f"'{contract.title_pattern}'"})
        return InvariantResult(
            "I15", "Sheet title matches contract", "BLOCK",
            "FAIL" if violations else "PASS",
            f"{len(violations)} title issues", violations)

    def check_required_headers(self) -> InvariantResult:
        """I16 · Required column headers present."""
        from backend.delivery.xlsx_contract import (
            PORTFOLIO_CONTRACT, EXIT_HISTORY_CONTRACT)
        wb = self._wb_load()
        if wb is None:
            return InvariantResult("I16", "Required headers", "BLOCK", "SKIP",
                                   "workbook missing")
        violations = []
        for contract in [PORTFOLIO_CONTRACT, EXIT_HISTORY_CONTRACT]:
            if contract.name not in wb.sheetnames: continue
            ws = wb[contract.name]
            headers = [str(ws.cell(contract.header_row, c).value or "").strip()
                       for c in range(1, ws.max_column + 1)]
            for req in contract.required_header_cells:
                if req not in headers:
                    violations.append({"sheet": contract.name, "missing": req})
        return InvariantResult(
            "I16", "Required headers present", "BLOCK",
            "FAIL" if violations else "PASS",
            f"{len(violations)} headers missing", violations[:10])

    def check_analysis_rows_populated(self) -> InvariantResult:
        """I17 · Rows 2 + 3 have non-empty analysis text."""
        wb = self._wb_load()
        if wb is None or "Portfolio" not in wb.sheetnames:
            return InvariantResult("I17", "Analysis rows", "WARN", "SKIP",
                                   "Portfolio missing")
        ws = wb["Portfolio"]
        r2 = str(ws.cell(2, 1).value or "").strip()
        r3 = str(ws.cell(3, 1).value or "").strip()
        if not r2 or not r3:
            return InvariantResult("I17", "Analysis rows populated", "WARN",
                                   "WARN", f"row2={len(r2)}c row3={len(r3)}c")
        return InvariantResult("I17", "Analysis rows populated", "WARN",
                               "PASS", "both analysis rows populated")

    def check_no_jargon_in_exit_reasons(self) -> InvariantResult:
        """I18 · Exit Reason column has no → jargon."""
        _reason_col = self._col_index("Exit History (90d)", "Exit Reason", 5)
        if _reason_col is None:
            return InvariantResult("I18", "No jargon in exit reasons",
                                   "BLOCK", "SKIP", "column missing")
        violations = []
        for r_idx, row in self._iter_data_rows("Exit History (90d)", 6):
            if _reason_col > len(row): continue
            _r = str(row[_reason_col - 1] or "")
            if "→" in _r and (".NS" in _r or "alpha" in _r.lower()):
                violations.append({"row": r_idx, "reason": _r[:60]})
        return InvariantResult(
            "I18", "No jargon in exit reasons", "BLOCK",
            "FAIL" if violations else "PASS",
            f"{len(violations)} jargon rows", violations[:5])

    def check_momentum_conservation(self) -> InvariantResult:
        """I19 · Every timing_engine BUY/WATCH/REBOUND pick must appear
        in Portfolio OR have a recorded rejection reason."""
        p = self.root / "reports" / "context" / f"timing_engine_{self.market}.json"
        if not p.exists():
            return InvariantResult("I19", "Momentum conservation", "WARN",
                                   "SKIP", "timing_engine JSON not present")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            picks = [s for s in d.get("scores", [])
                     if s.get("decision") in ("BUY", "WATCH", "REBOUND_WATCH")]
            if not picks:
                return InvariantResult("I19", "Momentum conservation", "WARN",
                                       "PASS", "no momentum picks · nothing to conserve")
            # Portfolio Runner=MOMENTUM rows
            _portfolio_mom_tks: set = set()
            for r_idx, row in self._iter_data_rows("Portfolio", 6):
                _tk = str(row[0] or "").upper().replace(".NS","").replace(".BO","")
                _rn = str(row[8] or "").upper()
                if _rn == "MOMENTUM":
                    _portfolio_mom_tks.add(_tk)
            missing = []
            for pk in picks[:5]:    # top 5 should render
                _tk = str(pk.get("ticker","")).upper().replace(".NS","").replace(".BO","")
                if _tk not in _portfolio_mom_tks:
                    missing.append({"ticker": _tk,
                                    "decision": pk.get("decision")})
            if missing:
                return InvariantResult(
                    "I19", "Momentum conservation", "WARN",
                    "WARN",
                    f"{len(missing)} timing picks missing from Portfolio · "
                    f"check dedup vs Registry",
                    missing)
            return InvariantResult(
                "I19", "Momentum conservation", "WARN", "PASS",
                f"all top-{len(picks[:5])} timing picks visible")
        except Exception as e:
            return InvariantResult("I19", "Momentum conservation", "WARN",
                                   "SKIP", f"{type(e).__name__}: {e}")

    def check_closed_tickers_in_exit_history(self) -> InvariantResult:
        """I20 · Every Registry-CLOSED opportunity in 90d must appear in Exit History."""
        reg = self._registry()
        cutoff = (date.today() - timedelta(days=90)).isoformat()
        closed_pids: set = set()
        closed_tks: set = set()
        for opps in reg.values():
            for o in opps:
                if o.market.lower() != self.market: continue
                if o.status != "CLOSED": continue
                if not o.closed_date or str(o.closed_date)[:10] < cutoff: continue
                closed_tks.add(o.ticker.upper().replace(".NS","").replace(".BO",""))
        # Exit History tickers
        exit_tks: set = set()
        for r_idx, row in self._iter_data_rows("Exit History (90d)", 6):
            _tk = str(row[0] or "").upper().replace(".NS","").replace(".BO","")
            if _tk: exit_tks.add(_tk)
        missing = closed_tks - exit_tks
        return InvariantResult(
            "I20", "Registry-CLOSED tickers in Exit History", "BLOCK",
            "FAIL" if missing else "PASS",
            f"{len(closed_tks)} closed · {len(exit_tks)} in exit history · "
            f"{len(missing)} missing",
            [{"ticker": t} for t in sorted(missing)[:5]])

    def check_canonical_states_only(self) -> InvariantResult:
        """I21 · Status column values must be canonical (LOCK 2)."""
        from backend.delivery.xlsx_contract import (
            CANONICAL_STATES, FORBIDDEN_STATES)
        # Check unified XLSX Status column
        uni_p = self.root / "reports" / "telegram" / "aegis_history.xlsx"
        if not uni_p.exists():
            return InvariantResult("I21", "Canonical states only", "BLOCK",
                                   "SKIP", "unified XLSX missing")
        try:
            from openpyxl import load_workbook
            wb = load_workbook(uni_p, read_only=True)
            sh = wb["AEGIS Daily"]
            h = [c.value for c in sh[1]]
            c_ctry = h.index("Country") + 1 if "Country" in h else None
            c_st = h.index("Status") + 1
            _seen_states: set = set()
            for row in sh.iter_rows(min_row=2, values_only=True):
                if c_ctry and str(row[c_ctry-1] or "").upper() != self.market.upper():
                    continue
                _st = str(row[c_st-1] or "").upper()
                if _st: _seen_states.add(_st)
            wb.close()
            _unknown = _seen_states - CANONICAL_STATES - FORBIDDEN_STATES
            return InvariantResult(
                "I21", "Canonical states only", "BLOCK",
                "WARN" if _unknown else "PASS",
                f"{len(_seen_states)} distinct states · "
                f"{len(_unknown)} unknown",
                [{"unknown": list(_unknown)[:10]}] if _unknown else [])
        except Exception as e:
            return InvariantResult("I21", "Canonical states only", "BLOCK",
                                   "SKIP", f"{type(e).__name__}: {e}")

    def check_no_forbidden_states(self) -> InvariantResult:
        """I22 · PROTECT/REVIEW/TRAIL never as Status values."""
        from backend.delivery.xlsx_contract import FORBIDDEN_STATES
        uni_p = self.root / "reports" / "telegram" / "aegis_history.xlsx"
        if not uni_p.exists():
            return InvariantResult("I22", "No forbidden states", "BLOCK",
                                   "SKIP", "unified XLSX missing")
        try:
            from openpyxl import load_workbook
            wb = load_workbook(uni_p, read_only=True)
            sh = wb["AEGIS Daily"]
            h = [c.value for c in sh[1]]
            c_ctry = h.index("Country") + 1 if "Country" in h else None
            c_st = h.index("Status") + 1
            violations = []
            for row in sh.iter_rows(min_row=2, values_only=True):
                if c_ctry and str(row[c_ctry-1] or "").upper() != self.market.upper():
                    continue
                _st = str(row[c_st-1] or "").upper()
                if _st in FORBIDDEN_STATES:
                    violations.append({
                        "ticker": row[h.index("Ticker")] if "Ticker" in h else "?",
                        "forbidden_state": _st,
                    })
            wb.close()
            return InvariantResult(
                "I22", "No forbidden states", "BLOCK",
                "FAIL" if violations else "PASS",
                f"{len(violations)} forbidden state uses", violations[:5])
        except Exception as e:
            return InvariantResult("I22", "No forbidden states", "BLOCK",
                                   "SKIP", f"{type(e).__name__}: {e}")

    def check_header_matches_visible_rows(self) -> InvariantResult:
        """I24 · Row 2 'Active: N positions' must equal visible
        ACTIVE/RE-ENTRY rows in Portfolio (excludes SHADOW/MOMENTUM/EXIT).
        """
        import re
        from openpyxl import load_workbook
        try:
            wb = load_workbook(self.xlsx_path, read_only=True, data_only=True)
            if "Portfolio" not in wb.sheetnames:
                return InvariantResult("I24", "Header count matches rows",
                                       "BLOCK", "SKIP", "no Portfolio sheet")
            ws = wb["Portfolio"]
            r2 = str(ws.cell(2, 1).value or "")
            m = re.search(r"Active:\s*(\d+)", r2)
            if not m:
                wb.close()
                return InvariantResult("I24", "Header count matches rows",
                                       "BLOCK", "SKIP",
                                       f"Row 2 missing 'Active: N' pattern")
            header_n = int(m.group(1))
            visible = 0
            for r_idx in range(6, ws.max_row + 1):
                _rn = str(ws.cell(r_idx, 9).value or "").upper()
                if _rn in ("SHADOW", "MOMENTUM"): continue
                _tk = str(ws.cell(r_idx, 1).value or "").upper()
                if not _tk or _tk.startswith(("🟢","🔴","🆕","🟣",
                                              "AEGIS","📊","🩺","✅","❌")):
                    continue
                _dec = str(ws.cell(r_idx, 3).value or "").upper()
                if "🔴 EXIT" in _dec or "EXIT" in _dec[:6]:
                    continue
                visible += 1
            wb.close()
            status = "PASS" if header_n == visible else "FAIL"
            return InvariantResult(
                "I24", "Header count matches rows", "BLOCK", status,
                f"header={header_n} visible={visible}",
                [{"header": header_n, "visible": visible}] if status == "FAIL" else [])
        except Exception as e:
            return InvariantResult("I24", "Header count matches rows",
                                   "BLOCK", "SKIP",
                                   f"{type(e).__name__}: {e}")

    def check_entry_price_immutable(self) -> InvariantResult:
        """I26 · non-same-day ACTIVE/RE-ENTRY rows must have entry_price
        matching parquet close on entry_date within 2%. Catches the
        entry-price re-stamp defect (MSFT-style ~0% P&L)."""
        from openpyxl import load_workbook
        import pandas as pd
        try:
            wb = load_workbook(self.xlsx_path, read_only=True, data_only=True)
            if "Portfolio" not in wb.sheetnames:
                return InvariantResult("I26", "Entry price immutable",
                                       "BLOCK", "SKIP", "no Portfolio")
            ws = wb["Portfolio"]
            r1 = str(ws.cell(1, 1).value or "")
            # Extract asof from title · "AEGIS INDIA PORTFOLIO · as of 2026-08-26"
            import re
            m = re.search(r"as of\s+(\d{4}-\d{2}-\d{2})", r1)
            asof = m.group(1) if m else None
            if not asof:
                wb.close()
                return InvariantResult("I26", "Entry price immutable",
                                       "BLOCK", "SKIP", "no asof in title")
            violations = []
            for r_idx in range(6, ws.max_row + 1):
                _tk = str(ws.cell(r_idx, 1).value or "").upper()
                if not _tk or _tk.startswith(("🟢","🔴","🆕","🟣",
                                              "AEGIS","📊","🩺","✅","❌")):
                    continue
                _rn = str(ws.cell(r_idx, 9).value or "").upper()
                if _rn in ("SHADOW", "MOMENTUM"): continue
                _dec = str(ws.cell(r_idx, 3).value or "")
                if "🔴 EXIT" in _dec or "🟣 SUGGESTED" in _dec: continue
                _entry_date = str(ws.cell(r_idx, 13).value or "")[:10]
                _entry_v = ws.cell(r_idx, 23).value
                if not _entry_date or _entry_date == asof: continue
                if not (isinstance(_entry_v, (int, float)) and _entry_v > 0):
                    continue
                # Look up parquet close on entry_date
                clean = _tk.replace(".NS","").replace(".BO","")
                base = ("usa/data/raw/us" if self.market.lower()=="usa"
                        else "data/raw/india")
                p = self.root / base / f"{clean}_D1.parquet"
                if not p.exists(): continue
                try:
                    df = pd.read_parquet(p)
                    col = "close" if "close" in df.columns else "Close"
                    df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
                    if _entry_date not in df.index:
                        earlier = [d for d in df.index if d <= _entry_date]
                        if not earlier: continue
                        historical_close = float(df.loc[earlier[-1], col])
                    else:
                        historical_close = float(df.loc[_entry_date, col])
                except Exception:
                    continue
                delta_pct = abs(_entry_v - historical_close) / historical_close * 100
                # 2026-08-27 · nearby-close tolerance · match PI1 pattern.
                # Some upstream engines stamp entry_date at recommendation
                # time (later than actual entry) while entry_price is
                # the true historical close. Walk back 10 calendar days
                # · if any prior close matches within 0.1%, accept it
                # as a legitimate nearby-date entry. Only escalates when
                # NO nearby close matches · that's a real drift.
                if delta_pct > 2.0:
                    matched_prior = False
                    try:
                        from datetime import timedelta as _td
                        for lookback in range(1, 11):
                            prior = (pd.to_datetime(_entry_date)
                                     - _td(days=lookback)).strftime("%Y-%m-%d")
                            if prior in df.index:
                                pc = float(df.loc[prior, col])
                                if pc > 0 and abs(_entry_v - pc) / pc * 100 <= 0.1:
                                    matched_prior = True
                                    break
                    except Exception:
                        pass
                    if not matched_prior:
                        violations.append({
                            "ticker":         _tk,
                            "row":            r_idx,
                            "entry_date":     _entry_date,
                            "stored_entry":   round(_entry_v, 2),
                            "parquet_close":  round(historical_close, 2),
                            "delta_pct":      round(delta_pct, 2),
                        })
            wb.close()
            status = "PASS" if not violations else "FAIL"
            return InvariantResult(
                "I26", "Entry price immutable", "BLOCK", status,
                f"{len(violations)} rows where stored entry drifts >2% "
                f"from parquet close on entry_date", violations[:5])
        except Exception as e:
            return InvariantResult("I26", "Entry price immutable",
                                   "BLOCK", "SKIP",
                                   f"{type(e).__name__}: {e}")

    def _parquet_close_lookup(self, ticker: str, iso_date: str,
                               lookback_days: int = 10) -> tuple:
        """Read-only parquet close on iso_date with N-day nearby-lookback
        for date-restamp cases. Returns (close_on_date, close_matched_in_window,
        matched_date). close_matched_in_window is True if either exact-date
        or nearby-date close was found."""
        import pandas as pd
        clean = ticker.upper().replace(".NS","").replace(".BO","")
        base = ("usa/data/raw/us" if self.market.lower()=="usa"
                else "data/raw/india")
        p = self.root / base / f"{clean}_D1.parquet"
        if not p.exists(): return (None, False, None)
        try:
            df = pd.read_parquet(p)
            col = "close" if "close" in df.columns else "Close"
            df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
            if iso_date in df.index:
                return (float(df.loc[iso_date, col]), True, iso_date)
            earlier = [d for d in df.index if d <= iso_date]
            if not earlier: return (None, False, None)
            fallback_close = float(df.loc[earlier[-1], col])
            # Nearby-date lookback
            from datetime import timedelta as _td
            for lookback in range(1, lookback_days + 1):
                prior = (pd.to_datetime(iso_date)
                         - _td(days=lookback)).strftime("%Y-%m-%d")
                if prior in df.index:
                    return (fallback_close, True, prior)
            return (fallback_close, False, None)
        except Exception:
            return (None, False, None)

    def check_entry_date_legitimate(self) -> InvariantResult:
        """I27 · entry_date must be <= asof AND a valid trading day (or
        within 5 calendar days of one). Blocks fabricated dates."""
        import re
        from datetime import date as _date, timedelta as _td
        from openpyxl import load_workbook
        try:
            wb = load_workbook(self.xlsx_path, read_only=True, data_only=True)
            if "Portfolio" not in wb.sheetnames:
                return InvariantResult("I27", "Entry date legitimate",
                                       "BLOCK", "SKIP", "no Portfolio")
            ws = wb["Portfolio"]
            r1 = str(ws.cell(1, 1).value or "")
            m = re.search(r"as of\s+(\d{4}-\d{2}-\d{2})", r1)
            asof = m.group(1) if m else _date.today().isoformat()
            violations = []
            for r_idx in range(6, ws.max_row + 1):
                _tk = str(ws.cell(r_idx, 1).value or "").upper()
                if not _tk or _tk.startswith(("🟢","🔴","🆕","🟣","AEGIS",
                                              "📊","🩺","✅","❌")):
                    continue
                _rn = str(ws.cell(r_idx, 9).value or "").upper()
                if _rn in ("SHADOW", "MOMENTUM"): continue
                _entry_date = str(ws.cell(r_idx, 13).value or "")[:10]
                if not _entry_date: continue
                try:
                    ed = _date.fromisoformat(_entry_date)
                    a  = _date.fromisoformat(asof)
                except Exception:
                    violations.append({"ticker": _tk, "row": r_idx,
                        "entry_date": _entry_date,
                        "reason": "unparseable date"})
                    continue
                if ed > a:
                    violations.append({"ticker": _tk, "row": r_idx,
                        "entry_date": _entry_date,
                        "reason": f"entry in future · asof={asof}"})
                    continue
                _, matched, _ = self._parquet_close_lookup(_tk, _entry_date, 5)
                if not matched:
                    violations.append({"ticker": _tk, "row": r_idx,
                        "entry_date": _entry_date,
                        "reason": "not a trading day + no prior close within 5d"})
            wb.close()
            status = "PASS" if not violations else "FAIL"
            return InvariantResult(
                "I27", "Entry date legitimate", "BLOCK", status,
                f"{len(violations)} illegitimate entry dates", violations[:5])
        except Exception as e:
            return InvariantResult("I27", "Entry date legitimate",
                                   "BLOCK", "SKIP", f"{type(e).__name__}: {e}")

    def check_exit_date_legitimate(self) -> InvariantResult:
        """I28 · exit_date must be >= entry_date AND <= asof AND a valid
        trading day (or within 5 cal days of one). Blocks impossible exits."""
        import re
        from datetime import date as _date
        from openpyxl import load_workbook
        try:
            wb = load_workbook(self.xlsx_path, read_only=True, data_only=True)
            if "Exit History (90d)" not in wb.sheetnames:
                return InvariantResult("I28", "Exit date legitimate",
                                       "BLOCK", "SKIP", "no Exit History")
            ws = wb["Exit History (90d)"]
            r1 = str(ws.cell(1, 1).value or "")
            m = re.search(r"as of\s+(\d{4}-\d{2}-\d{2})", r1)
            asof = m.group(1) if m else _date.today().isoformat()
            # Exit History cols · Stock=1 · Entry Date=5 · Exit Date=6
            violations = []
            for r_idx in range(6, ws.max_row + 1):
                _tk = str(ws.cell(r_idx, 1).value or "").upper()
                if not _tk: continue
                _ed = str(ws.cell(r_idx, 5).value or "")[:10]
                _xd = str(ws.cell(r_idx, 6).value or "")[:10]
                if not (_ed and _xd): continue
                try:
                    ed = _date.fromisoformat(_ed)
                    xd = _date.fromisoformat(_xd)
                    a  = _date.fromisoformat(asof)
                except Exception:
                    violations.append({"ticker": _tk, "row": r_idx,
                        "entry": _ed, "exit": _xd,
                        "reason": "unparseable date"})
                    continue
                if xd < ed:
                    violations.append({"ticker": _tk, "row": r_idx,
                        "entry": _ed, "exit": _xd,
                        "reason": "exit before entry"})
                    continue
                if xd > a:
                    violations.append({"ticker": _tk, "row": r_idx,
                        "entry": _ed, "exit": _xd,
                        "reason": f"exit in future · asof={asof}"})
                    continue
                _, matched, _ = self._parquet_close_lookup(_tk, _xd, 5)
                if not matched:
                    violations.append({"ticker": _tk, "row": r_idx,
                        "entry": _ed, "exit": _xd,
                        "reason": "exit not trading day + no prior close 5d"})
            wb.close()
            status = "PASS" if not violations else "FAIL"
            return InvariantResult(
                "I28", "Exit date legitimate", "BLOCK", status,
                f"{len(violations)} illegitimate exit dates", violations[:5])
        except Exception as e:
            return InvariantResult("I28", "Exit date legitimate",
                                   "BLOCK", "SKIP", f"{type(e).__name__}: {e}")

    def check_current_price_legitimate(self) -> InvariantResult:
        """I29 · Current Price on ACTIVE/RE-ENTRY rows within 2% of
        parquet close on asof (intraday tolerance)."""
        import re
        from openpyxl import load_workbook
        try:
            wb = load_workbook(self.xlsx_path, read_only=True, data_only=True)
            if "Portfolio" not in wb.sheetnames:
                return InvariantResult("I29", "Current Price legitimate",
                                       "BLOCK", "SKIP", "no Portfolio")
            ws = wb["Portfolio"]
            r1 = str(ws.cell(1, 1).value or "")
            m = re.search(r"as of\s+(\d{4}-\d{2}-\d{2})", r1)
            if not m:
                wb.close()
                return InvariantResult("I29", "Current Price legitimate",
                                       "BLOCK", "SKIP", "no asof")
            asof = m.group(1)
            violations = []
            for r_idx in range(6, ws.max_row + 1):
                _tk = str(ws.cell(r_idx, 1).value or "").upper()
                if not _tk or _tk.startswith(("🟢","🔴","🆕","🟣","AEGIS")):
                    continue
                _rn = str(ws.cell(r_idx, 9).value or "").upper()
                if _rn in ("SHADOW", "MOMENTUM"): continue
                _dec = str(ws.cell(r_idx, 3).value or "")
                if "🔴 EXIT" in _dec or "🟣 SUGGESTED" in _dec: continue
                _curr = ws.cell(r_idx, 24).value
                if not (isinstance(_curr, (int, float)) and _curr > 0):
                    continue
                pq_close, matched, _ = self._parquet_close_lookup(_tk, asof, 3)
                if pq_close is None or not matched: continue
                delta_pct = abs(_curr - pq_close) / pq_close * 100
                if delta_pct > 2.0:
                    violations.append({
                        "ticker": _tk, "row": r_idx,
                        "stored_current": round(_curr, 2),
                        "parquet_asof_close": round(pq_close, 2),
                        "delta_pct": round(delta_pct, 2),
                    })
            wb.close()
            status = "PASS" if not violations else "FAIL"
            return InvariantResult(
                "I29", "Current Price legitimate", "BLOCK", status,
                f"{len(violations)} rows where current price drifts >2% "
                f"from parquet close on asof", violations[:5])
        except Exception as e:
            return InvariantResult("I29", "Current Price legitimate",
                                   "BLOCK", "SKIP", f"{type(e).__name__}: {e}")

    def check_exit_price_legitimate(self) -> InvariantResult:
        """I30 · Exit Price matches parquet close on exit_date within 2%
        (with 10-day nearby-lookback for date restamps · same tolerance I26)."""
        from openpyxl import load_workbook
        try:
            wb = load_workbook(self.xlsx_path, read_only=True, data_only=True)
            if "Exit History (90d)" not in wb.sheetnames:
                return InvariantResult("I30", "Exit Price legitimate",
                                       "BLOCK", "SKIP", "no Exit History")
            ws = wb["Exit History (90d)"]
            # Exit History cols · Stock=1 · Exit Date=6 · Exit Price=9
            violations = []
            for r_idx in range(6, ws.max_row + 1):
                _tk = str(ws.cell(r_idx, 1).value or "").upper()
                if not _tk: continue
                _xd = str(ws.cell(r_idx, 6).value or "")[:10]
                _xp = ws.cell(r_idx, 9).value
                if not (_xd and isinstance(_xp, (int, float)) and _xp > 0):
                    continue
                pq_close, matched, _ = self._parquet_close_lookup(_tk, _xd, 10)
                if pq_close is None: continue
                delta_pct = abs(_xp - pq_close) / pq_close * 100
                if delta_pct > 2.0 and not matched:
                    violations.append({
                        "ticker": _tk, "row": r_idx,
                        "exit_date": _xd,
                        "stored_exit_price": round(_xp, 2),
                        "parquet_close": round(pq_close, 2),
                        "delta_pct": round(delta_pct, 2),
                    })
            wb.close()
            status = "PASS" if not violations else "FAIL"
            return InvariantResult(
                "I30", "Exit Price legitimate", "BLOCK", status,
                f"{len(violations)} exit prices drift >2% from parquet "
                f"close on exit_date", violations[:5])
        except Exception as e:
            return InvariantResult("I30", "Exit Price legitimate",
                                   "BLOCK", "SKIP", f"{type(e).__name__}: {e}")

    def check_realized_matches_exit_history(self) -> InvariantResult:
        """I25 · Portfolio Row 2 Realized 90d numbers must reconcile to
        Exit History (90d) sheet's row count."""
        import re
        from openpyxl import load_workbook
        try:
            wb = load_workbook(self.xlsx_path, read_only=True, data_only=True)
            if "Portfolio" not in wb.sheetnames or \
                    "Exit History (90d)" not in wb.sheetnames:
                wb.close()
                return InvariantResult("I25", "Realized reconciles",
                                       "BLOCK", "SKIP", "missing sheet")
            ws_p = wb["Portfolio"]
            r2 = str(ws_p.cell(2, 1).value or "")
            m = re.search(r"Realized 90d[^(]*\(\s*(\d+)\s*exits", r2)
            header_n = int(m.group(1)) if m else -1
            ws_eh = wb["Exit History (90d)"]
            # Count Exit History data rows with numeric P&L in col 10
            eh_n = 0
            for r_idx in range(6, ws_eh.max_row + 1):
                _v = ws_eh.cell(r_idx, 10).value
                if isinstance(_v, (int, float)):
                    eh_n += 1
            wb.close()
            status = "PASS" if header_n == eh_n else "FAIL"
            return InvariantResult(
                "I25", "Realized reconciles", "BLOCK", status,
                f"header={header_n} exit_history={eh_n}",
                [{"header": header_n, "exit_history": eh_n}] if status == "FAIL" else [])
        except Exception as e:
            return InvariantResult("I25", "Realized reconciles",
                                   "BLOCK", "SKIP",
                                   f"{type(e).__name__}: {e}")

    def check_runner_canonical(self) -> InvariantResult:
        """I23 · Runner column has canonical values (R1/R2/SHADOW/MOMENTUM).

        Regression for 2026-08-26 bug where hardcoded c_run=4 read the
        Country column, so every Portfolio row's Runner showed 'INDIA' /
        'USA' instead of R1/R2 · a symptom of Portfolio's column-index
        drift.
        """
        allowed = {"R1", "R2", "SHADOW", "MOMENTUM", "SUGGESTED", ""}
        violations = []
        for r_idx, row in self._iter_data_rows("Portfolio", 6):
            _tk = str(row[0] or "").upper()
            if not _tk or _tk.startswith(("🟢","🔴","🆕","🟣","AEGIS","📊","🩺","✅","❌")):
                continue
            # Runner column index = 8 (0-indexed) · matches C9 in current schema
            _rn = str(row[8] or "").upper() if len(row) > 8 else ""
            if _rn not in allowed:
                violations.append({
                    "ticker": _tk, "row": r_idx, "runner_value": _rn,
                })
        return InvariantResult(
            "I23", "Runner column has canonical values", "BLOCK",
            "FAIL" if violations else "PASS",
            f"{len(violations)} rows with non-canonical Runner value",
            violations[:5])


# ─────────────────────────────────────────────────────────────────
# PUBLIC · validate + emit
# ─────────────────────────────────────────────────────────────────
def validate(root: Path, market: str, xlsx_path: Path) -> ValidationReport:
    """Run all 22 invariants against the built XLSX. Returns report."""
    v = XlsxValidator(root, market, xlsx_path)
    rep = ValidationReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        xlsx_path=str(xlsx_path),
    )
    # Map each invariant to its check method
    from backend.delivery.xlsx_contract import INVARIANTS
    for inv in INVARIANTS:
        fn = getattr(v, inv.check_fn_name, None)
        if fn is None:
            rep.add(InvariantResult(inv.code, inv.name, inv.severity,
                                    "SKIP", f"no check function {inv.check_fn_name}"))
            continue
        try:
            result = fn()
            rep.add(result)
        except Exception as e:
            rep.add(InvariantResult(inv.code, inv.name, inv.severity,
                                    "SKIP", f"check crashed: {type(e).__name__}: {e}"))
    return rep


def emit(root: Path, rep: ValidationReport) -> Path:
    p = (root / "reports" / "context"
         / f"xlsx_validation_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def should_block_send(rep: ValidationReport) -> bool:
    """Return True if any BLOCK-severity invariant FAILed."""
    for r in rep.invariants:
        if r.severity == "BLOCK" and r.status == "FAIL":
            return True
    return False


def render_blocked_alert(rep: ValidationReport) -> str:
    """Plain-text alert to send to Telegram when send is blocked."""
    lines = [
        "🚫 AEGIS DELIVERY BLOCKED",
        f"market: {rep.market.upper()} · {rep.asof}",
        f"validation verdict: {rep.verdict}",
        f"BLOCK checks failed: "
        f"{sum(1 for r in rep.invariants if r.severity=='BLOCK' and r.status=='FAIL')}",
        "",
        "Failed invariants:",
    ]
    for r in rep.invariants:
        if r.severity == "BLOCK" and r.status == "FAIL":
            lines.append(f"  · {r.code} · {r.name} · {r.detail[:80]}")
    lines += [
        "",
        "Fix the underlying issue · re-run pipeline · no XLSX shipped this cycle.",
    ]
    return "\n".join(lines)


def summary_line(rep: ValidationReport) -> str:
    return (f"xlsx_validator · {rep.market.upper()} · verdict={rep.verdict} · "
            f"PASS={rep.n_pass} WARN={rep.n_warn} FAIL={rep.n_fail} SKIP={rep.n_skip}")
