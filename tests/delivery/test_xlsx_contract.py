# tests/delivery/test_xlsx_contract.py
"""AEGIS · Delivery Contract + Validator tests.

Contract definitions must be internally consistent · validator must
correctly detect violations · golden integration tests must pass on a
synthetic XLSX + Registry fixture.
"""
from __future__ import annotations

from pathlib import Path
from openpyxl import Workbook
import pytest


# ═════════════════════════════════════════════════════════════════
# Contract structure tests
# ═════════════════════════════════════════════════════════════════
class TestContract:

    def test_all_invariants_have_unique_codes(self):
        from backend.delivery.xlsx_contract import INVARIANTS
        codes = [i.code for i in INVARIANTS]
        assert len(codes) == len(set(codes))

    def test_all_invariants_have_check_fn(self):
        from backend.delivery.xlsx_contract import INVARIANTS
        from backend.delivery.xlsx_validator import XlsxValidator
        for i in INVARIANTS:
            assert hasattr(XlsxValidator, i.check_fn_name), \
                f"Missing check function {i.check_fn_name} for {i.code}"

    def test_all_invariants_severity_valid(self):
        from backend.delivery.xlsx_contract import INVARIANTS
        for i in INVARIANTS:
            assert i.severity in ("BLOCK", "WARN", "INFO"), \
                f"{i.code} has invalid severity {i.severity}"

    def test_20_plus_invariants(self):
        from backend.delivery.xlsx_contract import INVARIANTS
        # CEO's list required 20+ invariants
        assert len(INVARIANTS) >= 20

    def test_at_least_10_blocking(self):
        from backend.delivery.xlsx_contract import BLOCK_INVARIANTS
        # Should be substantial blocking set
        assert len(BLOCK_INVARIANTS) >= 10

    def test_forbidden_states_defined(self):
        from backend.delivery.xlsx_contract import FORBIDDEN_STATES
        assert "PROTECT" in FORBIDDEN_STATES
        assert "REVIEW" in FORBIDDEN_STATES
        assert "TRAIL" in FORBIDDEN_STATES

    def test_canonical_states_correct(self):
        from backend.delivery.xlsx_contract import CANONICAL_STATES
        for s in ("NEW", "ACTIVE", "ACTIVE+", "EXIT"):
            assert s in CANONICAL_STATES


# ═════════════════════════════════════════════════════════════════
# Golden-file integration test · synthetic XLSX + Registry
# ═════════════════════════════════════════════════════════════════
@pytest.fixture
def synthetic_xlsx(tmp_path):
    """Build a minimal valid Portfolio XLSX matching the contract."""
    p = tmp_path / "reports" / "telegram" / "aegis_history_india.xlsx"
    p.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    # Portfolio sheet
    ws = wb.active
    ws.title = "Portfolio"
    # Row 1 · title
    ws.cell(1, 1, "AEGIS INDIA PORTFOLIO · as of 2026-08-26")
    # Row 2 · analysis
    ws.cell(2, 1, "🟢 Active: 2 positions (unique Position IDs)  ·  "
                   "Unrealized P&L: +1.50%  ·  Today's P&L: +0.20%")
    # Row 3 · analysis
    ws.cell(3, 1, "✅ Positive: 1 pos · avg +2.50%  ·  "
                   "❌ Negative: 1 pos · avg -1.00%")
    # Row 5 · header
    headers = ["Ticker", "🎯 ACTION", "🎯 DECISION", "Lifecycle", "Month",
               "Trigger", "Review", "Window",
               "Runner", "R1/R2 Consensus", "Sector", "Cap",
               "Entry Date", "Exit Date", "Days",
               "Urgency", "Reason", "Action", "Review",
               "Status", "Inv Quality", "Investability",
               "Entry", "Current", "Exit Price", "P&L %",
               "Stop Loss", "Target 1", "Target 2",
               "Action Note", "Alerts", "Exit Reason",
               "Post-Exit", "Basis"]
    for c, h in enumerate(headers, start=1):
        ws.cell(5, c, h)
    # Row 6 · valid ACTIVE row (TCS)
    row6 = ["TCS", "🟢 ACTIVE · stop ₹3300", "🟢 ACTIVE", "ACTIVE",
            "Aug 2026", "", "", "",
            "R2", "R1+R2", "Technology", "LARGE",
            "2026-08-01", "", 25,
            "HIGH", "", "", "",
            "HOLD", "🏆 QUALITY", 85.0,
            3500.0, 3550.0, None, 0.0143,
            3300.0, 3800.0, 4000.0,
            "", "", "", "", ""]
    for c, v in enumerate(row6, start=1):
        ws.cell(6, c, v)
    # Exit History sheet
    eh = wb.create_sheet("Exit History (90d)")
    eh.cell(1, 1, "AEGIS INDIA · EXIT HISTORY · last 90 days as of 2026-08-26")
    eh.cell(2, 1, "📊 Total: 5 exits · Realized P&L: +12.5%  ·  Win Rate: 60%")
    eh.cell(3, 1, "✅ Positive: 3 · +18.5%  ·  ❌ Negative: 2 · -6.0%")
    eh_hdr = ["Stock", "Sector", "Month", "Runner",
              "Entry Date", "Exit Date", "Days Held",
              "Entry Price", "Exit Price", "P&L %", "Confidence",
              "Verdict", "Exit Reason"]
    for c, h in enumerate(eh_hdr, start=1):
        eh.cell(5, c, h)
    eh.cell(6, 1, "HDFC")
    eh.cell(6, 2, "Financial Services")
    eh.cell(6, 3, "Aug 2026")
    eh.cell(6, 4, "R2")
    eh.cell(6, 5, "2026-07-15")
    eh.cell(6, 6, "2026-08-10")
    eh.cell(6, 13, "Profit target hit")
    wb.save(p)
    return tmp_path


class TestValidator:

    def test_validate_returns_report(self, synthetic_xlsx):
        from backend.delivery import xlsx_validator as _val
        rep = _val.validate(
            synthetic_xlsx, "india",
            synthetic_xlsx / "reports" / "telegram" / "aegis_history_india.xlsx")
        assert rep.market == "india"
        assert rep.n_pass + rep.n_warn + rep.n_fail + rep.n_skip == \
               len(rep.invariants)

    def test_should_block_send_false_when_all_pass(self, synthetic_xlsx):
        from backend.delivery import xlsx_validator as _val
        # Mock a report with no BLOCK failures
        rep = _val.ValidationReport(
            market="india", asof="2026-08-26",
            generated_utc="2026-08-26T00:00:00Z",
        )
        assert _val.should_block_send(rep) is False

    def test_should_block_send_true_on_block_fail(self):
        from backend.delivery import xlsx_validator as _val
        rep = _val.ValidationReport(
            market="india", asof="2026-08-26",
            generated_utc="2026-08-26T00:00:00Z",
        )
        rep.add(_val.InvariantResult(
            "I1", "test", "BLOCK", "FAIL", "test fail"))
        assert _val.should_block_send(rep) is True

    def test_render_blocked_alert_readable(self):
        from backend.delivery import xlsx_validator as _val
        rep = _val.ValidationReport(
            market="india", asof="2026-08-26",
            generated_utc="2026-08-26T00:00:00Z",
        )
        rep.add(_val.InvariantResult(
            "I1", "EXIT in ACTIVE", "BLOCK", "FAIL", "2 leaks"))
        alert = _val.render_blocked_alert(rep)
        assert "🚫 AEGIS DELIVERY BLOCKED" in alert
        assert "I1" in alert

    def test_summary_line_format(self):
        from backend.delivery import xlsx_validator as _val
        rep = _val.ValidationReport(
            market="india", asof="2026-08-26",
            generated_utc="2026-08-26T00:00:00Z",
        )
        s = _val.summary_line(rep)
        assert "xlsx_validator" in s
        assert "verdict=" in s

    def test_emit_writes_json(self, synthetic_xlsx):
        from backend.delivery import xlsx_validator as _val
        rep = _val.validate(
            synthetic_xlsx, "india",
            synthetic_xlsx / "reports" / "telegram" / "aegis_history_india.xlsx")
        p = _val.emit(synthetic_xlsx, rep)
        assert p.exists()

    def test_sheet_title_check(self, synthetic_xlsx, monkeypatch):
        from backend.delivery.xlsx_validator import XlsxValidator
        v = XlsxValidator(
            synthetic_xlsx, "india",
            synthetic_xlsx / "reports" / "telegram" / "aegis_history_india.xlsx")
        r = v.check_sheet_title()
        assert r.status == "PASS"

    def test_required_headers_check(self, synthetic_xlsx):
        from backend.delivery.xlsx_validator import XlsxValidator
        v = XlsxValidator(
            synthetic_xlsx, "india",
            synthetic_xlsx / "reports" / "telegram" / "aegis_history_india.xlsx")
        r = v.check_required_headers()
        # Our synthetic has all required headers · should PASS
        assert r.status == "PASS", f"Missing headers: {r.violations}"

    def test_analysis_rows_populated(self, synthetic_xlsx):
        from backend.delivery.xlsx_validator import XlsxValidator
        v = XlsxValidator(
            synthetic_xlsx, "india",
            synthetic_xlsx / "reports" / "telegram" / "aegis_history_india.xlsx")
        r = v.check_analysis_rows_populated()
        assert r.status == "PASS"
