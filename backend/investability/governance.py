"""Governance sub-engine · 15% weight of Investability Score.

Wave 1 (lite · this file) · signals derivable from yfinance ticker.info:
    Beta reasonable       · beta < 1.5 · not speculative-vol
    Held by insiders     · heldPercentInsiders > 5% · skin in game
    Held by institutions · heldPercentInstitutions > 20% · institutional quality
    Short interest       · shortRatio < 5 · not heavily shorted
    Audit quality proxy  · auditRisk (if present · yfinance ESG-adjacent)
    Board quality proxy  · boardRisk (if present)
    Compensation risk    · compensationRisk (if present)
    Governance flag      · overallRisk composite

Wave 2 (Sprint K Part 26 · Nov 11-17):
    Full SEBI/BSE announcement RSS scraper
    Promoter pledging % (from shareholding pattern)
    Auditor changes (from company reports)
    Related-party transaction ratio
    Independent director %
    ESG controversies
"""
from __future__ import annotations


def score(info: dict) -> tuple[float, dict]:
    signals = {}
    hits = 0
    total = 0

    def check(name, value, ok_fn, weight=1.0):
        """Fixed 2026-08-08: missing signal = neutral (not counted in total).
        Previously all missing ESG scores penalized Indian tickers to ~27."""
        nonlocal hits, total
        if value is None:
            signals[name] = {"value": None, "ok": None, "weight": weight}
            return
        try:
            ok = bool(ok_fn(value))
            total += weight
            signals[name] = {"value": value, "ok": ok, "weight": weight}
            if ok: hits += weight
        except (TypeError, ValueError):
            signals[name] = {"value": value, "ok": None, "weight": weight}

    # Volatility / speculative check
    check("beta_reasonable",         info.get("beta"),                    lambda v: v < 1.5, 1.5)

    # Ownership quality
    check("insider_holding_healthy", info.get("heldPercentInsiders"),     lambda v: v >= 0.05, 1.5)
    check("institutional_holding",   info.get("heldPercentInstitutions"), lambda v: v >= 0.20, 1.5)

    # Short interest (bearish signal · high = bad)
    short_ratio = info.get("shortRatio")
    check("short_interest_low",      short_ratio,                          lambda v: v < 5, 1.0)

    # yfinance ESG-adjacent risk scores (LOWER = better · scale 1-10)
    # Present only for stocks with sustainability data
    check("audit_risk_low",          info.get("auditRisk"),                lambda v: v <= 5, 1.5)
    check("board_risk_low",          info.get("boardRisk"),                lambda v: v <= 5, 1.0)
    check("compensation_risk_low",   info.get("compensationRisk"),         lambda v: v <= 5, 0.5)
    check("shareholder_rights_ok",   info.get("shareHolderRightsRisk"),    lambda v: v <= 5, 0.5)
    check("overall_governance_ok",   info.get("overallRisk"),              lambda v: v <= 5, 2.0)

    score_0_100 = round(hits / total * 100, 1) if total else 50.0
    return score_0_100, {
        "engine":     "governance.v1_lite",
        "score":      score_0_100,
        "hits":       round(hits, 2),
        "total":      round(total, 2),
        "signals":    signals,
        "note":       "Wave 1 lite · Wave 2 adds SEBI + pledge + auditor + RPT",
    }
