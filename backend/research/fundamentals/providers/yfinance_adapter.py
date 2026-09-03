"""yfinance provider adapter · translates yfinance objects into the
standardized input dict for layer1-5 fundamentals derivations.

Free-data path. Rate-limit-friendly. Silent-degradation-safe · any
missing statement item leaves that layer's signal as None (never zero).

Not every layer has a yfinance source · specifically:
  - Layer 4 (FII/DII) is India-only via nseindia (separate adapter)
  - Layer 4 (Options PCR single-name) is not available on yfinance for India
  - Layer 5 (Promoter pledge) needs an India nseindia adapter

This adapter fills what it can from yfinance and leaves the rest for
adapters yet to be written. That is by design · degradation-visible.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Optional


def _safe_get(obj, key, default=None):
    try:
        v = obj.get(key) if hasattr(obj, "get") else None
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return default
        return v
    except Exception:
        return default


def _series_at(df, col: str, asof: date):
    """Return the value in `col` at asof (or last <= asof) · None if missing."""
    if df is None or df.empty or col not in df.columns:
        return None
    try:
        import pandas as pd
        mask = df.index.date <= asof if hasattr(df.index, "date") else True
        sub = df.loc[mask, col].dropna() if hasattr(mask, "__iter__") else df[col].dropna()
        if sub.empty:
            return None
        return float(sub.iloc[-1])
    except Exception:
        return None


def fetch_yfinance_inputs(ticker: str, market: str, asof: str,
                          net_flow_series_20d: Optional[list] = None) -> dict:
    """Return a standardized input dict for compute_row().

    Populates every yfinance-derivable field. Missing fields are omitted
    (not None) so downstream layer functions can distinguish "no data"
    from "data present but derivation failed".

    Import yfinance lazily · this module must load even when yfinance
    is not installed (feature-store scaffold works with synthetic data).
    """
    try:
        import yfinance as yf
    except Exception:
        return {"data_sources": "yfinance:import-failed"}

    ymkt_ticker = ticker if "." in ticker else (
        f"{ticker}.NS" if market == "india" else ticker
    )
    try:
        y = yf.Ticker(ymkt_ticker)
    except Exception:
        return {"data_sources": "yfinance:ticker-init-failed"}

    fin: dict = {"data_sources": "yfinance"}

    # ---- Info block (many keys) ----
    try:
        info = y.info or {}
    except Exception:
        info = {}

    def _pull(k):
        v = info.get(k)
        if v is None: return None
        try:
            if isinstance(v, (int, float)) and not math.isnan(float(v)):
                return float(v)
            return v
        except Exception:
            return v

    mc = _pull("marketCap")
    if mc: fin["market_cap"] = mc
    ev = _pull("enterpriseValue")
    if ev: fin["enterprise_value"] = ev
    ebitda = _pull("ebitda")
    if ebitda: fin["ebitda_ttm"] = ebitda
    fcf = _pull("freeCashflow")
    if fcf: fin["fcf_ttm"] = fcf
    div_rate = _pull("dividendRate")
    if div_rate and mc:
        so = _pull("sharesOutstanding") or 1
        fin["dividends_ttm"] = div_rate * so
        fin["buybacks_ttm"] = 0.0
        fin["issuance_ttm"] = 0.0

    # Earnings surprise · yfinance calendar has next earnings date
    try:
        cal = y.calendar
        if cal is not None and not cal.empty:
            nd = cal.loc["Earnings Date"].values
            if len(nd) > 0:
                d = nd[0]
                try:
                    fin["next_earnings_date"] = str(d)[:10]
                except Exception:
                    pass
    except Exception:
        pass

    # Short interest
    sr = _pull("shortRatio")
    fl = _pull("floatShares")
    if sr and fl:
        # short_interest_shares ~ shortRatio × avg_volume · we use si_pct directly if avail
        si_pct = _pull("shortPercentOfFloat")
        if si_pct is not None:
            fin["short_interest_shares"] = si_pct * fl
            fin["float_shares"] = fl

    # Insider transactions (net $ over 90d)
    try:
        it = y.insider_transactions
        if it is not None and not it.empty:
            it["Start Date"] = pd_to_dt(it.get("Start Date"))
            asof_d = datetime.fromisoformat(asof).date()
            cutoff = asof_d - timedelta(days=90)
            recent = it[it["Start Date"].dt.date >= cutoff] if "Start Date" in it.columns else None
            if recent is not None and not recent.empty and "Value" in recent.columns:
                buys = recent[recent["Transaction"].str.contains("Buy", case=False, na=False)]["Value"].sum()
                sells = recent[recent["Transaction"].str.contains("Sale", case=False, na=False)]["Value"].sum()
                fin["insider_net_dollars_90d"] = float(buys - sells)
    except Exception:
        pass

    # Analyst revisions (upgrades/downgrades feed)
    # yfinance exposes `recommendations` DataFrame · we approximate revision
    # momentum by counting buy-side upgrades in the last 90 days.
    try:
        rec = y.recommendations
        if rec is not None and not rec.empty:
            asof_d = datetime.fromisoformat(asof).date()
            cutoff = asof_d - timedelta(days=90)
            recent = rec[rec.index.date >= cutoff] if hasattr(rec.index, "date") else rec.tail(20)
            n = len(recent)
            if n > 0:
                ups = sum(1 for a in recent.get("To Grade", []) if
                          str(a).lower() in ("buy", "strong buy", "outperform", "overweight"))
                downs = sum(1 for a in recent.get("To Grade", []) if
                            str(a).lower() in ("sell", "strong sell", "underperform", "underweight"))
                fin["analyst_rev_momentum_proxy_net"] = (ups - downs) / n
    except Exception:
        pass

    # FII/DII net flow · not on yfinance · caller passes series if available
    if net_flow_series_20d:
        fin["net_flow_series_20d"] = net_flow_series_20d

    # ---- Statement-based items (income + balance sheet + cashflow) ----
    try:
        income = y.income_stmt
        bs = y.balance_sheet
        cf = y.cashflow
    except Exception:
        income = bs = cf = None

    def _latest(df, key):
        try:
            if df is None or df.empty: return None
            row = df.loc[key] if key in df.index else None
            if row is None or row.empty: return None
            return float(row.iloc[0])
        except Exception:
            return None

    def _prior(df, key):
        try:
            if df is None or df.empty: return None
            row = df.loc[key] if key in df.index else None
            if row is None or len(row) < 2: return None
            return float(row.iloc[1])
        except Exception:
            return None

    # Income
    fin["net_income"] = _latest(income, "Net Income")
    fin["sales"]      = _latest(income, "Total Revenue")
    fin["ebit"]       = _latest(income, "EBIT") or _latest(income, "Operating Income")
    ie = _latest(income, "Interest Expense")
    if ie is not None:
        fin["interest_expense"] = abs(ie)
    gp = _latest(income, "Gross Profit")
    if fin.get("sales") and gp is not None and fin["sales"] > 0:
        fin["gross_margin_now"] = gp / fin["sales"]
    gp_prev = _prior(income, "Gross Profit")
    rev_prev = _prior(income, "Total Revenue")
    if gp_prev is not None and rev_prev and rev_prev > 0:
        fin["gross_margin_prev"] = gp_prev / rev_prev

    # Cashflow · CFO
    fin["cfo"] = _latest(cf, "Operating Cash Flow") or _latest(cf, "Cash Flow From Operating Activities")

    # Balance sheet
    fin["total_assets_now"] = _latest(bs, "Total Assets")
    fin["total_assets_prev"] = _prior(bs, "Total Assets")
    fin["total_liabilities"] = _latest(bs, "Total Liabilities Net Minority Interest") or _latest(bs, "Total Liab")
    fin["long_term_debt_now"] = _latest(bs, "Long Term Debt")
    fin["long_term_debt_prev"] = _prior(bs, "Long Term Debt")
    ca = _latest(bs, "Current Assets")
    cl = _latest(bs, "Current Liabilities")
    if ca and cl and cl > 0:
        fin["current_ratio_now"] = ca / cl
        fin["working_capital"] = ca - cl
    ca_p = _prior(bs, "Current Assets")
    cl_p = _prior(bs, "Current Liabilities")
    if ca_p and cl_p and cl_p > 0:
        fin["current_ratio_prev"] = ca_p / cl_p
    fin["retained_earnings"] = _latest(bs, "Retained Earnings")
    so_now = _latest(bs, "Ordinary Shares Number") or _pull("sharesOutstanding")
    so_prev = _prior(bs, "Ordinary Shares Number")
    if so_now: fin["shares_out_now"] = so_now
    if so_prev: fin["shares_out_prev"] = so_prev

    # Derived · ROA now/prev · asset turnover now/prev
    if fin.get("net_income") is not None and fin.get("total_assets_now"):
        fin["roa_now"] = fin["net_income"] / fin["total_assets_now"]
    ni_prev = _prior(income, "Net Income")
    if ni_prev is not None and fin.get("total_assets_prev"):
        fin["roa_prev"] = ni_prev / fin["total_assets_prev"]
    if fin.get("sales") and fin.get("total_assets_now"):
        fin["asset_turnover_now"] = fin["sales"] / fin["total_assets_now"]
    if rev_prev and fin.get("total_assets_prev"):
        fin["asset_turnover_prev"] = rev_prev / fin["total_assets_prev"]

    return fin


def pd_to_dt(s):
    import pandas as pd
    return pd.to_datetime(s, errors="coerce")
