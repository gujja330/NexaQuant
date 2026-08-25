# backend/delivery/row_classifier.py
"""AEGIS · single-source-of-truth row classifier for the Portfolio dashboard.

Operator directive 2026-08-25: "same 4 blockers persist · make this a
proper product". Root cause of the recurring A17/A22/A24 blockers is that
the sender has row-decision logic scattered across 5+ functions
(_row_classify_bucket, _row_section, ACTION-string generator, section-header
router). They disagree, and A-checks catch the disagreement AFTER the row
is already written.

This module is the ONE place that decides, for a given row of the raw XLSX,
- which section it belongs to (ACTION / ACTIVE / NEW / EXIT_HISTORY)
- what the ACTION column string reads
- whether it counts as a "closed" opportunity for downstream dedup

The sender must use ONLY this module. Any callsite that computes its own
section/action string is a bug.

The classifier is a pure function of the raw row + a few registry lookups
(investability verdict, runner-aware opportunity state). No I/O.

Testable invariants (see tests/delivery/test_row_classifier.py):
  I-A17 · decision.section != "existing" whenever action_str starts "🔴 EXIT"
  I-A18 · decision.reason contains no "→", "alpha", or "Xpp" jargon
  I-A22 · same ticker in Portfolio + Exit History is OK when runner column
           differs (multi-runner canonical position)
  I-A24 · closed-in-registry ticker is OK in Portfolio when the same
           ticker's other runner is ACTIVE
  I-verdict · section-header emoji matches ACTION emoji every time
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ─────────────────────────────────────────────────────────────────
# Vocab v5.0 · four action verbs · three colors
# ─────────────────────────────────────────────────────────────────
SECTION_ACTION = "action"       # red · "ACTION REQUIRED TODAY"
SECTION_ACTIVE = "existing"     # green · "ACTIVE"
SECTION_NEW    = "new_opps"     # purple · "NEW"
SECTION_CLOSED = "closed"       # gray · "Exit History"

_VALID_SECTIONS = (SECTION_ACTION, SECTION_ACTIVE, SECTION_NEW, SECTION_CLOSED)

BINDING_RISK_SIGNALS = (
    "STOP_LOSS_HIT", "STOP HIT", "TIME_STOP", "TIME STOP",
    "TRAILING_STOP", "TRAILING STOP", "PROFIT_TAKE_HIT", "PROFIT TAKE",
)


@dataclass(frozen=True)
class RowDecision:
    """One row's routing verdict · used by the XLSX build path."""
    section:    str         # one of _VALID_SECTIONS
    action_str: str         # column-2 text · starts with 🔴/🟢/🟣
    verdict:    str         # one word: EXIT / ACTIVE / ACTIVE+ / NEW
    bucket:     str         # priority bucket · R/G/F/H/I/A/B/C/D/E
    reason:     str         # plain-English reason · A18-clean
    sortkey:    tuple       # for stable descending-date sort

    def __post_init__(self):
        # I-A17 · section and action MUST agree. A row whose ACTION says
        # "🔴 EXIT" cannot be in the ACTIVE (green) section, ever.
        if self.section not in _VALID_SECTIONS:
            raise ValueError(f"invalid section '{self.section}'")
        if self.action_str.startswith("🔴 EXIT") \
           and self.section == SECTION_ACTIVE:
            raise ValueError(
                f"A17 violation · EXIT action in ACTIVE section · "
                f"action={self.action_str!r} bucket={self.bucket}")
        if self.action_str.startswith("🟣 NEW") \
           and self.section not in (SECTION_NEW, SECTION_ACTION):
            raise ValueError(
                f"A17 violation · NEW action in {self.section} section")
        # I-A18 · plain English · no template jargon in reason
        _bad = ("→", "Xpp", "xpp")
        for tok in _bad:
            if tok in self.reason:
                raise ValueError(
                    f"A18 violation · jargon '{tok}' in reason={self.reason!r}")


# ─────────────────────────────────────────────────────────────────
# Bucket classifier · deterministic priority
# ─────────────────────────────────────────────────────────────────
def classify_bucket(*, status: str, alerts: str, pnl_pct: Optional[float],
                    inv_verdict: str) -> str:
    """Priority bucket · pure function.

    Buckets:
      R · binding-risk signal in Alerts (stop hit today etc.)
      G · quality-avoid OR HOLD with neg P&L and no quality boost
      F · quality-avoid alone
      H · EXIT with high-quality (already-closed winner)
      I · EXIT with low/mid quality (already-closed loser)
      A · STRONG BUY with quality
      B · BUY/STRONG BUY with quality
      C · HOLD with quality and neg P&L
      D · HOLD with quality
      E · everything else
    """
    st = (status or "").upper().strip()
    al = (alerts or "").upper()
    iv = (inv_verdict or "").strip()
    q_high = iv in ("🏆 QUALITY", "✓ OK")
    q_low  = iv == "✗ AVOID"
    pnl_neg = isinstance(pnl_pct, (int, float)) and pnl_pct < 0

    # 1. Binding-risk veto
    if any(sig in al for sig in BINDING_RISK_SIGNALS):
        return "R"
    # 2. EXIT status routes to closed bucket
    if st == "EXIT":
        return "H" if q_high else "I"
    # 3. Structural failure · HOLD + neg P&L + no quality boost
    if st == "HOLD" and pnl_neg and not q_high:
        return "G"
    # 4. Existing rules
    if q_low and pnl_neg: return "G"
    if q_low:             return "F"
    if st == "STRONG BUY" and iv == "🏆 QUALITY": return "A"
    if st in ("BUY", "STRONG BUY") and q_high:   return "B"
    if st == "HOLD" and q_high and pnl_neg:      return "C"
    if st == "HOLD" and q_high:                  return "D"
    return "E"


# ─────────────────────────────────────────────────────────────────
# Section router · bucket → section
# ─────────────────────────────────────────────────────────────────
_SECTION_BY_BUCKET = {
    "R": SECTION_ACTION,
    "G": SECTION_ACTION,
    "F": SECTION_ACTION,
    "H": SECTION_CLOSED,
    "I": SECTION_CLOSED,
    "A": SECTION_ACTIVE,
    "B": SECTION_ACTIVE,
    "C": SECTION_ACTIVE,
    "D": SECTION_ACTIVE,
    "E": SECTION_ACTIVE,
}


def _plain_reason(*, bucket: str, alerts: str, pnl_pct: Optional[float],
                  decision_basis: str, entry_price: Optional[float]) -> str:
    """A18-clean · no jargon · plain English."""
    # Strip jargon from decision_basis if operator-visible
    _basis = str(decision_basis or "")
    for bad in ("→", "Xpp", "xpp", "alpha", "α"):
        _basis = _basis.replace(bad, "").strip()
    # Bucket-specific plain reasons
    if bucket == "R":
        # Binding risk · surface which alert triggered
        for sig in BINDING_RISK_SIGNALS:
            if sig in (alerts or "").upper():
                return f"{sig.replace('_',' ').title()} triggered today"
        return "Risk signal triggered today"
    if bucket == "G":
        pnl_s = f"{pnl_pct*100:+.1f}%" if isinstance(pnl_pct, (int,float)) else "?"
        return f"Position underwater at {pnl_s} · quality avoid or weak"
    if bucket == "F":
        return "Quality gate rejects · avoid list"
    if bucket in ("H", "I"):
        pnl_s = f"{pnl_pct*100:+.1f}%" if isinstance(pnl_pct, (int,float)) else "?"
        return f"Position closed at P&L {pnl_s}"
    if bucket == "A":
        return "Strong buy · high quality"
    if bucket == "B":
        return "Buy signal · quality confirmed"
    if bucket == "C":
        pnl_s = f"{pnl_pct*100:+.1f}%" if isinstance(pnl_pct, (int,float)) else "?"
        return f"Hold quality name · underwater at {pnl_s}"
    if bucket == "D":
        return "Hold quality name · thesis intact"
    return _basis[:80] if _basis else "Under review"


def _action_string(*, bucket: str, section: str, ticker: str,
                   currency_symbol: str, entry_price, current_price,
                   stop_price, t1_price, pnl_pct, alerts, decision_basis):
    """Deterministic ACTION column text · matches vocab v5.0."""
    def _fmt(v):
        if isinstance(v, (int, float)) and v == v:  # not NaN
            return f"{v:,.2f}"
        return "?"
    curr_s  = _fmt(current_price)
    entry_s = _fmt(entry_price)
    stop_s  = _fmt(stop_price)
    t1_s    = _fmt(t1_price)
    pnl_s   = (f"{pnl_pct*100:+.1f}%"
               if isinstance(pnl_pct, (int, float)) else "?")
    c = currency_symbol

    # Bucket-driven · guaranteed section-consistent
    if bucket == "R":
        # Today's urgent EXIT · lives in ACTION section
        _basis_short = str(decision_basis or "")[:40].strip() or "risk signal"
        # A18: strip jargon
        for bad in ("→", "Xpp", "xpp", "alpha", "α"):
            _basis_short = _basis_short.replace(bad, "").strip()
        return f"🔴 EXIT · {_basis_short} · was entry {c}{entry_s}"
    if bucket in ("H", "I"):
        return f"🔴 EXIT · P&L {pnl_s} · exit {c}{curr_s}"
    if bucket == "G":
        return f"🔴 EXIT · P&L {pnl_s} · underwater · exit {c}{curr_s}"
    if bucket == "F":
        return f"🔴 EXIT · quality avoid · exit {c}{curr_s}"

    # Section-driven for BUY/HOLD tiers
    if section == SECTION_NEW:
        return (f"🟣 NEW · {ticker} @ {c}{curr_s} · "
                f"stop {c}{stop_s} · T1 {c}{t1_s}")
    if bucket in ("A", "B"):
        return (f"🟢 ACTIVE+ · @ {c}{curr_s} · "
                f"stop {c}{stop_s} · P&L {pnl_s}")
    # C, D, E · ACTIVE
    return f"🟢 ACTIVE · stop {c}{stop_s} · P&L {pnl_s}"


def _verdict_of(bucket: str, section: str) -> str:
    """One-word verdict · vocab v5.0."""
    if bucket in ("R", "G", "F", "H", "I"):
        return "EXIT"
    if section == SECTION_NEW:
        return "NEW"
    if bucket in ("A", "B"):
        return "ACTIVE+"
    return "ACTIVE"


# ─────────────────────────────────────────────────────────────────
# PUBLIC · one call, one decision
# ─────────────────────────────────────────────────────────────────
def classify_row(
    *,
    ticker: str,
    market: str,
    row_date_iso: str,
    rec_date_iso: str,
    asof_iso: str,
    status: str,
    alerts: str,
    entry_price: Optional[float],
    current_price: Optional[float],
    stop_price: Optional[float],
    t1_price: Optional[float],
    pnl_pct: Optional[float],
    inv_verdict: str,
    decision_basis: str = "",
) -> RowDecision:
    """The ONE row-decision function. Sender must call this per row.

    Returns a RowDecision that guarantees section + action_str + verdict
    are internally consistent. Violates would raise in __post_init__.
    """
    bucket = classify_bucket(
        status=status, alerts=alerts,
        pnl_pct=pnl_pct, inv_verdict=inv_verdict,
    )
    # Section derived from bucket · plus same-day-new override for NEW
    section = _SECTION_BY_BUCKET.get(bucket, SECTION_ACTIVE)
    if bucket == "E":
        # Only E-bucket rows can be same-day NEW · promote to NEW section
        # if the row's rec_date equals today's asof.
        _rd10 = (rec_date_iso or "")[:10]
        _as10 = (asof_iso or "")[:10]
        if _rd10 and _rd10 == _as10 and (status or "").upper() != "EXIT":
            section = SECTION_NEW

    currency_symbol = "$" if (market or "").lower() == "usa" else "₹"
    action_str = _action_string(
        bucket=bucket, section=section, ticker=ticker,
        currency_symbol=currency_symbol,
        entry_price=entry_price, current_price=current_price,
        stop_price=stop_price, t1_price=t1_price,
        pnl_pct=pnl_pct, alerts=alerts, decision_basis=decision_basis,
    )
    verdict = _verdict_of(bucket, section)
    reason = _plain_reason(
        bucket=bucket, alerts=alerts, pnl_pct=pnl_pct,
        decision_basis=decision_basis, entry_price=entry_price,
    )
    # Sort key · newest first · row_date desc
    sortkey = (0 if section == SECTION_ACTION else
               1 if section == SECTION_NEW else
               2 if section == SECTION_ACTIVE else 3,
               -_iso_ord(row_date_iso))

    return RowDecision(
        section=section,
        action_str=action_str,
        verdict=verdict,
        bucket=bucket,
        reason=reason,
        sortkey=sortkey,
    )


def _iso_ord(iso: str) -> int:
    """YYYY-MM-DD → int for desc sort · missing/malformed = 0."""
    s = (iso or "")[:10]
    if not s or len(s) < 10 or s[4] != "-":
        return 0
    try:
        y = int(s[0:4]); m = int(s[5:7]); d = int(s[8:10])
        return y * 10000 + m * 100 + d
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────
# Dedup rule · A22/A24 · runner-aware
# ─────────────────────────────────────────────────────────────────
def is_legit_multi_runner_appearance(
    *, portfolio_runners: set, exit_runners: set,
) -> bool:
    """True when a ticker legitimately appears in BOTH sheets because at
    least one runner is ACTIVE and at least one different runner is CLOSED.

    portfolio_runners: runner labels active for this ticker in Portfolio sheet
    exit_runners: runner labels closed for this ticker in Exit History sheet

    Legit = intersection is empty (different runners) AND at least one on each.
    """
    if not portfolio_runners or not exit_runners:
        return False
    # If the same runner is in both, that's a real bug (double-listing).
    if portfolio_runners & exit_runners:
        return False
    return True
