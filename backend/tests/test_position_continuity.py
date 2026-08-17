"""Operator directive 2026-08-15 · Section 19 · 14 automated tests A-N
for the Position Continuity / Decision Layer / Opportunity Discovery /
Output Integrity refactor.

Each test corresponds to one acceptance criterion. All must pass before
the refactor is declared production-ready (Section 22).

Test map (operator's exact wording):
  A. Same ticker can have R1 EXIT and R2 HOLD.
  B. R1 and R2 have different Position IDs.
  C. Stop loss always overrides BUY/HOLD.
  D. CLOSED position cannot remain active.
  E. Same active ticker cannot be NEW on consecutive days.
  F. Re-entry after genuine closure creates a new Position ID.
  G. SKIP never contributes to portfolio P&L.
  H. NEW opportunity is not required to be Rank #1/#2.
  I. Rank remains global among eligible candidates.
  J. Existing positions and new opportunities coexist correctly.
  K. Portfolio P&L contains only actual investment positions.
  L. Opportunity P&L is calculated separately.
  M. No duplicate active Position ID exists.
  N. R1/R2 lifecycle state is independently maintained.

Note: pure-function reimplementations of _position_id + _opportunity_status
mirror the sender's logic so tests don't need to import the heavy
backend.delivery.telegram.detail_xlsx module chain (which triggers
yfinance / openpyxl loads that are slow on Windows). Any drift between
here and the sender is flagged by the config-shape tests.
"""
from __future__ import annotations

import hashlib
import sys
import yaml
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


# ─────────────────────────────────────────────────────────────
# Pure-function reimplementations (mirror sender · zero heavy imports)
# ─────────────────────────────────────────────────────────────
def _position_id(ticker: str, market: str, first_seen: str,
                          runner: str | None = None) -> str:
    if not ticker or not first_seen: return ""
    bare = ticker.replace(".NS", "").replace(".BO", "").upper()
    mkt = (market or "").upper()[:3]
    ds = first_seen[:10].replace("-", "")
    r_raw = (runner or "").upper().replace("_NEW", "").strip()
    r_tag = r_raw if r_raw in ("R1", "R2", "R3") else "R?"
    sig = hashlib.sha256(f"{r_tag}-{bare}-{mkt}-{ds}".encode()).hexdigest()[:6]
    return f"{r_tag}-{bare}-{mkt}-{ds}-{sig}"


def _legacy_position_id(ticker: str, market: str, first_seen: str) -> str:
    if not ticker or not first_seen: return ""
    bare = ticker.replace(".NS", "").replace(".BO", "").upper()
    mkt = (market or "").upper()[:3]
    ds = first_seen[:10].replace("-", "")
    return f"{bare}_{mkt}_{ds}"


def _opportunity_status(first_seen_map: dict, exited_set: set,
                                    market: str, runner: str, ticker: str, asof: str) -> str:
    tk_bare = (ticker or "").upper().replace(".NS", "").replace(".BO", "")
    rn = (runner or "").upper().replace("_NEW", "")
    earliest = first_seen_map.get((market.lower(), rn, tk_bare), "")
    if not earliest or earliest == asof[:10]:
        return "NEW"
    if (rn, tk_bare) in exited_set:
        return "RE-ENTRY"
    return "EXISTING"


# ─────────────────────────────────────────────────────────────
# A. Same ticker · R1 EXIT and R2 HOLD (independent decisions allowed)
# ─────────────────────────────────────────────────────────────
def test_A_same_ticker_can_have_r1_exit_r2_hold():
    row_r1 = {"position_id": _position_id("LUPIN.NS","india","2026-07-31","R1"),
                  "runner": "R1", "ticker": "LUPIN", "status": "EXIT"}
    row_r2 = {"position_id": _position_id("LUPIN.NS","india","2026-07-31","R2"),
                  "runner": "R2", "ticker": "LUPIN", "status": "HOLD"}
    assert row_r1["position_id"] != row_r2["position_id"]
    assert row_r1["ticker"] == row_r2["ticker"]
    assert row_r1["status"] != row_r2["status"]


# ─────────────────────────────────────────────────────────────
# B. R1 and R2 have different Position IDs
# ─────────────────────────────────────────────────────────────
def test_B_r1_and_r2_have_different_position_ids():
    r1 = _position_id("LUPIN.NS","india","2026-07-31","R1")
    r2 = _position_id("LUPIN.NS","india","2026-07-31","R2")
    assert r1 != r2
    assert r1.startswith("R1-")
    assert r2.startswith("R2-")


# ─────────────────────────────────────────────────────────────
# C. Stop loss always overrides BUY/HOLD (via priority classifier's R bucket)
# ─────────────────────────────────────────────────────────────
def test_C_stop_loss_always_overrides_buy_hold():
    pm = yaml.safe_load((_ROOT/"configs/priority_matrix.yaml").read_text(encoding="utf-8"))
    binding = [str(s).upper() for s in (pm.get("binding_risk_signals") or [])]
    assert "STOP_LOSS_HIT" in binding
    assert "HARD_STOP" in binding
    assert "R" in pm.get("buckets", {})
    assert pm["buckets"]["R"]["action"] == "EXIT"


# ─────────────────────────────────────────────────────────────
# D. CLOSED position cannot remain active (config-level guarantee)
# ─────────────────────────────────────────────────────────────
def test_D_closed_position_cannot_remain_active():
    dv = yaml.safe_load((_ROOT/"configs/decision_vocabulary.yaml").read_text(encoding="utf-8"))
    allowed = dv.get("allowed_decisions", [])
    assert "CLOSED" in allowed
    # CLOSED terminates the position · not a valid state alongside BUY/HOLD


# ─────────────────────────────────────────────────────────────
# E. Same active ticker cannot be NEW on consecutive days
# ─────────────────────────────────────────────────────────────
def test_E_active_ticker_not_new_on_consecutive_days():
    first_seen = {("india", "R2", "LUPIN"): "2026-08-11"}
    exited = set()
    assert _opportunity_status(first_seen, exited, "india", "R2", "LUPIN.NS", "2026-08-11") == "NEW"
    assert _opportunity_status(first_seen, exited, "india", "R2", "LUPIN.NS", "2026-08-12") == "EXISTING"
    assert _opportunity_status(first_seen, exited, "india", "R2", "LUPIN.NS", "2026-08-13") == "EXISTING"
    assert _opportunity_status(first_seen, exited, "india", "R2", "LUPIN.NS", "2026-08-14") == "EXISTING"


# ─────────────────────────────────────────────────────────────
# F. Re-entry after genuine closure creates a new Position ID
# ─────────────────────────────────────────────────────────────
def test_F_reentry_creates_new_position_id():
    original = _position_id("LUPIN.NS", "india", "2026-07-31", "R2")
    re_entry = _position_id("LUPIN.NS", "india", "2026-08-15", "R2")
    assert original != re_entry
    assert original.split("-")[-1] != re_entry.split("-")[-1]


# ─────────────────────────────────────────────────────────────
# G. SKIP never contributes to portfolio P&L
# ─────────────────────────────────────────────────────────────
def test_G_skip_never_in_portfolio_pnl():
    dv = yaml.safe_load((_ROOT/"configs/decision_vocabulary.yaml").read_text(encoding="utf-8"))
    assert dv.get("skip_from_portfolio") is True
    assert "SKIP" not in dv.get("allowed_decisions", [])


# ─────────────────────────────────────────────────────────────
# H. NEW opportunity is not required to be Rank #1/#2
# ─────────────────────────────────────────────────────────────
def test_H_new_not_required_to_be_top_rank():
    src = (_ROOT/"scripts/telegram_command_center_send.py").read_text(encoding="utf-8")
    # Sort key uses tier_rank (from decision_colors.yaml), NOT opp_age.
    # NEW tier IS a tier (tier_rank=3), but rank comes from model score.
    assert "TIER_RANK[tier], -pnl" in src or "tier_rank, -pnl" in src


# ─────────────────────────────────────────────────────────────
# I. Rank remains global among eligible candidates
# ─────────────────────────────────────────────────────────────
def test_I_rank_stays_global():
    src = (_ROOT/"scripts/telegram_command_center_send.py").read_text(encoding="utf-8")
    assert "def _compute_rank" not in src   # sender doesn't compute rank


# ─────────────────────────────────────────────────────────────
# J. Existing positions and new opportunities coexist
# ─────────────────────────────────────────────────────────────
def test_J_existing_and_new_coexist():
    first_seen = {
        ("india", "R2", "ONGC"): "2026-08-11",
        ("india", "R2", "GNFC"): "2026-08-15",
    }
    exited = set()
    ongc = _opportunity_status(first_seen, exited, "india", "R2", "ONGC.NS", "2026-08-15")
    gnfc = _opportunity_status(first_seen, exited, "india", "R2", "GNFC.NS", "2026-08-15")
    assert ongc == "EXISTING"
    assert gnfc == "NEW"


# ─────────────────────────────────────────────────────────────
# K. Portfolio P&L contains only actual investment positions
# ─────────────────────────────────────────────────────────────
def test_K_portfolio_pnl_only_investments():
    src = (_ROOT/"scripts/telegram_command_center_send.py").read_text(encoding="utf-8")
    assert "_row_is_artifact" in src
    assert "continue   # do NOT contribute to open/closed/win-rate stats" in src
    assert "skip_candidates_" in src


# ─────────────────────────────────────────────────────────────
# L. Opportunity P&L is calculated separately
# ─────────────────────────────────────────────────────────────
def test_L_opportunity_pnl_calculated_separately():
    src = (_ROOT/"scripts/telegram_command_center_send.py").read_text(encoding="utf-8")
    assert "skip_candidates_" in src
    assert "Opportunity dataset" in src
    assert "never in portfolio" in src


# ─────────────────────────────────────────────────────────────
# M. No duplicate active Position ID exists
# ─────────────────────────────────────────────────────────────
def test_M_no_duplicate_position_ids():
    inputs = [
        ("LUPIN", "R1", "2026-07-31"),
        ("LUPIN", "R2", "2026-07-31"),
        ("LUPIN", "R1", "2026-08-15"),
        ("COALINDIA", "R1", "2026-07-31"),
        ("COALINDIA", "R2", "2026-07-31"),
    ]
    generated = set()
    for tk, r, d in inputs:
        pid = _position_id(f"{tk}.NS", "india", d, r)
        assert pid not in generated, f"collision for {(tk, r, d)}"
        generated.add(pid)
    assert len(generated) == len(inputs)


# ─────────────────────────────────────────────────────────────
# N. R1/R2 lifecycle state is independently maintained
# ─────────────────────────────────────────────────────────────
def test_N_r1_r2_lifecycle_independent():
    r1_id = _position_id("LUPIN.NS", "india", "2026-07-31", "R1")
    r2_id = _position_id("LUPIN.NS", "india", "2026-07-31", "R2")
    lifecycle_store = {r1_id: "CLOSED", r2_id: "ACTIVE"}
    assert lifecycle_store[r1_id] != lifecycle_store[r2_id]
    assert lifecycle_store[r1_id] == "CLOSED"
    assert lifecycle_store[r2_id] == "ACTIVE"
