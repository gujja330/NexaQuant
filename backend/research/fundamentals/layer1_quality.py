"""Fundamentals · Layer 1 · Quality (5 signals)

Piotroski F-Score · Beneish M-Score · Altman Z-Score · Sloan Accruals · Interest Coverage.

Every function returns None when the required inputs are missing rather
than a zero value · downstream models must be able to distinguish "quality
is bad" from "we don't know".

Inputs are supplied as a dict of financial statement items pulled from
yfinance / free provider. The keys expected are standardized here; the
provider adapter (backend/research/fundamentals/providers/*) does the
translation.
"""
from __future__ import annotations

from typing import Optional


def piotroski_f_score(fin: dict) -> Optional[int]:
    """F-Score · sum of 9 binary criteria comparing this year vs last.

    Required keys:
      net_income, cfo, roa_now, roa_prev, total_assets_now, total_assets_prev,
      long_term_debt_now, long_term_debt_prev,
      current_ratio_now, current_ratio_prev,
      shares_out_now, shares_out_prev,
      gross_margin_now, gross_margin_prev,
      asset_turnover_now, asset_turnover_prev
    """
    required = [
        "net_income", "cfo", "roa_now", "roa_prev",
        "long_term_debt_now", "long_term_debt_prev",
        "current_ratio_now", "current_ratio_prev",
        "shares_out_now", "shares_out_prev",
        "gross_margin_now", "gross_margin_prev",
        "asset_turnover_now", "asset_turnover_prev",
    ]
    for k in required:
        if k not in fin or fin[k] is None:
            return None
    try:
        score = 0
        # Profitability
        if fin["net_income"] > 0: score += 1                            # 1 Positive NI
        if fin["cfo"] > 0: score += 1                                    # 2 Positive CFO
        if fin["roa_now"] > fin["roa_prev"]: score += 1                  # 3 Improving ROA
        if fin["cfo"] > fin["net_income"]: score += 1                    # 4 CFO > NI (accruals)
        # Leverage / liquidity / source of funds
        if fin["long_term_debt_now"] <= fin["long_term_debt_prev"]: score += 1  # 5 Lower LT debt
        if fin["current_ratio_now"] > fin["current_ratio_prev"]: score += 1     # 6 Improving liquidity
        if fin["shares_out_now"] <= fin["shares_out_prev"]: score += 1          # 7 No dilution
        # Operating efficiency
        if fin["gross_margin_now"] > fin["gross_margin_prev"]: score += 1       # 8 Improving GM
        if fin["asset_turnover_now"] > fin["asset_turnover_prev"]: score += 1   # 9 Improving turnover
        return int(score)
    except (TypeError, ValueError):
        return None


def beneish_m_score(fin: dict) -> Optional[float]:
    """M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
           + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI

    Flag: M > -1.78 → elevated earnings-manipulation risk.

    Required keys:
      dsri, gmi, aqi, sgi, depi, sgai, tata, lvgi
    (each computed by the provider adapter from the raw statements)
    """
    keys = ["dsri", "gmi", "aqi", "sgi", "depi", "sgai", "tata", "lvgi"]
    for k in keys:
        if k not in fin or fin[k] is None:
            return None
    try:
        m = (
            -4.84
            + 0.920 * float(fin["dsri"])
            + 0.528 * float(fin["gmi"])
            + 0.404 * float(fin["aqi"])
            + 0.892 * float(fin["sgi"])
            + 0.115 * float(fin["depi"])
            - 0.172 * float(fin["sgai"])
            + 4.679 * float(fin["tata"])
            - 0.327 * float(fin["lvgi"])
        )
        return round(m, 4)
    except (TypeError, ValueError):
        return None


def altman_z_score(fin: dict) -> Optional[float]:
    """Original Altman Z (manufacturing) ·
        Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
    A = Working_Capital / Total_Assets
    B = Retained_Earnings / Total_Assets
    C = EBIT / Total_Assets
    D = Market_Cap / Total_Liabilities
    E = Sales / Total_Assets

    Zones · > 2.99 safe · 1.81-2.99 grey · < 1.81 distress.
    """
    keys = ["working_capital", "retained_earnings", "ebit",
            "market_cap", "total_liabilities", "sales", "total_assets"]
    for k in keys:
        if k not in fin or fin[k] is None:
            return None
    try:
        ta = float(fin["total_assets"])
        tl = float(fin["total_liabilities"])
        if ta <= 0 or tl <= 0:
            return None
        A = float(fin["working_capital"]) / ta
        B = float(fin["retained_earnings"]) / ta
        C = float(fin["ebit"]) / ta
        D = float(fin["market_cap"]) / tl
        E = float(fin["sales"]) / ta
        return round(1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def sloan_accruals(fin: dict) -> Optional[float]:
    """Sloan accruals ratio · (NI - CFO) / Avg_Total_Assets

    Magnitude · large positive/negative → earnings-quality flag.
    Cutoff usually ~ ±0.10 in the literature.
    """
    for k in ("net_income", "cfo", "total_assets_now", "total_assets_prev"):
        if k not in fin or fin[k] is None:
            return None
    try:
        avg_ta = (float(fin["total_assets_now"]) + float(fin["total_assets_prev"])) / 2.0
        if avg_ta <= 0:
            return None
        acc = (float(fin["net_income"]) - float(fin["cfo"])) / avg_ta
        return round(acc, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def interest_coverage(fin: dict) -> Optional[float]:
    """EBIT / Interest_Expense · < 1.5 solvency flag · > 3 healthy."""
    for k in ("ebit", "interest_expense"):
        if k not in fin or fin[k] is None:
            return None
    try:
        ie = float(fin["interest_expense"])
        if ie <= 0:
            # No interest expense · effectively unlimited coverage
            return 999.0
        return round(float(fin["ebit"]) / ie, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


LAYER1_FUNCTIONS = {
    "piotroski_f":       piotroski_f_score,
    "beneish_m":         beneish_m_score,
    "altman_z":          altman_z_score,
    "sloan_accruals":    sloan_accruals,
    "interest_coverage": interest_coverage,
}
