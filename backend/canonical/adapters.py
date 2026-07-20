"""Market-agnostic adapters — raw market data → canonical rows.

For every raw dataset (India or USA) the pipeline ingests in Sprint 1B,
there is one adapter here that reads the parquet / JSON off disk and
yields a `CanonicalDataset`. Downstream engines read canonical only.

**Determinism:** adapters are pure functions of (market_root, asof).
They never touch the network. Reading the same raw files always yields
the same canonical rows — that's what makes walk-forward replay valid.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from backend.canonical.model import MarketProfile, INDIA_PROFILE, USA_PROFILE
from backend.canonical.schemas import (
    CanonicalBar, CanonicalFundamentals, CanonicalNews, CanonicalFlow,
    CanonicalCorporateAction, CanonicalEarnings, CanonicalMacro,
    CanonicalFlowProxy, CanonicalHolding, CanonicalDataset,
)

# Every adapter takes the repo root (Path) + the MarketProfile + optional
# asof cutoff (for walk-forward: "only include rows on or before this date").
# Returns a CanonicalDataset.

# ─── helpers ─────────────────────────────────────────────────────────
def _parse_date(x) -> date | None:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, pd.Timestamp):
        return x.date()
    try:
        s = str(x).split()[0]
        return datetime.fromisoformat(s).date()
    except Exception:
        try: return datetime.strptime(str(x)[:10], "%Y-%m-%d").date()
        except Exception: return None


def _f(x) -> float | None:
    if x is None: return None
    try:
        f = float(x)
        if pd.isna(f): return None
        return f
    except Exception:
        return None


def _within(dt: date | None, cutoff: date | None) -> bool:
    """Walk-forward filter: keep row only if its date ≤ cutoff (or no cutoff)."""
    if cutoff is None: return True
    if dt is None: return True   # asof-less rows always allowed (adapters set market-level asof)
    return dt <= cutoff


# ─── PRICE / BAR ─────────────────────────────────────────────────────
def adapt_prices(repo_root: Path, market: MarketProfile,
                  symbols: Iterable[str] | None = None,
                  cutoff: date | None = None,
                  lookback_days: int = 90) -> CanonicalDataset:
    """Read raw OHLCV parquets and yield CanonicalBar rows.

    India:  data/raw/india/{SYMBOL}_D1.parquet
    USA:    usa/data/raw/us/{SYMBOL}_D1.parquet
    """
    if market.name == "india":
        raw_dir = repo_root / "data" / "raw" / "india"
    else:
        raw_dir = repo_root / "usa" / "data" / "raw" / "us"

    if not raw_dir.exists():
        return CanonicalDataset(kind="bar", market=market.name,
                                  asof=cutoff or date.today(), n_rows=0, source=str(raw_dir))

    files = sorted(raw_dir.glob("*_D1.parquet"))
    if symbols:
        symset = set(symbols)
        files = [f for f in files if f.stem.replace("_D1", "") in symset]

    rows: list[CanonicalBar] = []
    for f in files:
        sym = f.stem.replace("_D1", "").lstrip("_")
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue
        if df.empty:
            continue
        # normalize column names + index
        df.columns = [c.lower() for c in df.columns]
        if df.index.name and df.index.name.lower() in ("date", "time", "datetime"):
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
        # find date column
        date_col = next((c for c in df.columns if c in ("date", "time", "datetime")), None)
        # normalize field aliases
        vol_col = next((c for c in df.columns if c in ("volume", "tick_volume")), None)
        for _, r in df.tail(lookback_days).iterrows():
            d = _parse_date(r.get(date_col)) if date_col else None
            if cutoff is not None and d is not None and d > cutoff:
                continue
            rows.append(CanonicalBar(
                market=market.name, symbol=sym, date=d or (cutoff or date.today()),
                open=_f(r.get("open")) or 0.0,
                high=_f(r.get("high")) or 0.0,
                low=_f(r.get("low")) or 0.0,
                close=_f(r.get("close")) or 0.0,
                volume=_f(r.get(vol_col)) or 0.0 if vol_col else 0.0,
                currency=market.currency,
            ))
    return CanonicalDataset(kind="bar", market=market.name,
                              asof=cutoff or date.today(), n_rows=len(rows),
                              rows=rows, source=str(raw_dir))


# ─── FUNDAMENTALS ────────────────────────────────────────────────────
def adapt_fundamentals(repo_root: Path, market: MarketProfile,
                        cutoff: date | None = None) -> CanonicalDataset:
    if market.name == "india":
        p = repo_root / "data" / "raw" / "india" / "fundamentals.parquet"
        source = "india.fundamentals_nse"
        symbol_col = None    # india parquet uses the index as ticker
    else:
        p = repo_root / "usa" / "reports" / "fundamentals.json"
        source = "usa.research.fundamentals"

    rows: list[CanonicalFundamentals] = []
    if not p.exists():
        return CanonicalDataset(kind="fundamentals", market=market.name,
                                  asof=cutoff or date.today(), n_rows=0, source=str(p))

    if p.suffix == ".parquet":
        df = pd.read_parquet(p).reset_index()
        # india fundamentals: index = symbol
        sym_col = df.columns[0]
        asof = cutoff or date.today()   # india parquet has no asof column — use ingestion date
        for _, r in df.iterrows():
            rows.append(CanonicalFundamentals(
                market=market.name, symbol=str(r[sym_col]), asof=asof,
                roe=_f(r.get("returnOnEquity")),
                debt_to_equity=_f(r.get("debtToEquity")),
                profit_margin=_f(r.get("profitMargins")),
                earnings_growth=_f(r.get("earningsGrowth")),
                trailing_pe=_f(r.get("trailingPE")),
                price_to_book=_f(r.get("priceToBook")),
                quality_score=_f(r.get("quality_score")),
                market_cap=None,
                currency=market.currency,
                source=source,
            ))
    else:
        # USA fundamentals.json — `tickers` is a DICT keyed by symbol
        data = json.loads(p.read_text(encoding="utf-8"))
        asof = _parse_date(data.get("run_utc")) or cutoff or date.today()
        tickers = data.get("tickers", {})
        # be tolerant of either dict-of-dicts or list-of-dicts
        rows_iter = tickers.values() if isinstance(tickers, dict) else tickers
        for t in rows_iter:
            if not isinstance(t, dict):
                continue
            rows.append(CanonicalFundamentals(
                market=market.name, symbol=t.get("symbol") or t.get("ticker") or "",
                asof=asof,
                roe=_f(t.get("roe")),
                debt_to_equity=_f(t.get("debt_to_equity")),
                profit_margin=_f(t.get("profit_margin")),
                earnings_growth=_f(t.get("earnings_growth")),
                trailing_pe=_f(t.get("pe_ratio")),
                price_to_book=_f(t.get("price_to_book")),
                quality_score=_f(t.get("fundamental_score")),
                market_cap=_f(t.get("market_cap")),
                currency=market.currency,
                source=source,
            ))
    return CanonicalDataset(kind="fundamentals", market=market.name,
                              asof=cutoff or date.today(), n_rows=len(rows),
                              rows=rows, source=str(p))


# ─── NEWS ────────────────────────────────────────────────────────────
def adapt_news(repo_root: Path, market: MarketProfile,
                cutoff: date | None = None) -> CanonicalDataset:
    if market.name == "india":
        p = repo_root / "data" / "raw" / "india" / "news_sentiment.parquet"
        source = "india.news_sentiment"
    else:
        p = repo_root / "usa" / "data" / "raw" / "us" / "news_sentiment.parquet"
        source = "usa.research.news"

    if not p.exists():
        return CanonicalDataset(kind="news", market=market.name,
                                  asof=cutoff or date.today(), n_rows=0, source=str(p))
    df = pd.read_parquet(p)
    rows: list[CanonicalNews] = []
    for _, r in df.iterrows():
        d = _parse_date(r.get("asof"))
        if not _within(d, cutoff): continue
        rows.append(CanonicalNews(
            market=market.name,
            symbol=str(r.get("symbol") or ""),
            asof=d or (cutoff or date.today()),
            sentiment=_f(r.get("news_sent")) or 0.0,
            n_headlines=int(_f(r.get("n_headlines")) or 0),
            n_positive=int(_f(r.get("pos")) or 0),
            n_negative=int(_f(r.get("neg")) or 0),
            source=source,
        ))
    return CanonicalDataset(kind="news", market=market.name,
                              asof=cutoff or date.today(), n_rows=len(rows),
                              rows=rows, source=str(p))


# ─── FLOWS (institutional) ───────────────────────────────────────────
def adapt_flows(repo_root: Path, market: MarketProfile,
                 cutoff: date | None = None) -> CanonicalDataset:
    rows: list[CanonicalFlow] = []
    if market.name == "india":
        p = repo_root / "data" / "raw" / "india" / "fii_dii.parquet"
        source = "india.fii_dii"
        if p.exists():
            df = pd.read_parquet(p)
            for _, r in df.iterrows():
                d = _parse_date(r.get("date") or r.get("ts"))
                if not _within(d, cutoff): continue
                fii = _f(r.get("FII_net"))
                dii = _f(r.get("DII_net"))
                if fii is not None:
                    rows.append(CanonicalFlow(
                        market=market.name, asof=d or (cutoff or date.today()),
                        kind="foreign_institutional", scope="market", symbol=None,
                        value_native=fii, currency=market.currency, source=source))
                if dii is not None:
                    rows.append(CanonicalFlow(
                        market=market.name, asof=d or (cutoff or date.today()),
                        kind="domestic_institutional", scope="market", symbol=None,
                        value_native=dii, currency=market.currency, source=source))
    else:
        p = repo_root / "usa" / "data" / "raw" / "us" / "insider_transactions.parquet"
        source = "usa.research.insider"
        if p.exists():
            df = pd.read_parquet(p)
            for _, r in df.iterrows():
                d = _parse_date(r.get("date"))
                if not _within(d, cutoff): continue
                txn = str(r.get("transaction") or "").lower()
                if "buy" in txn or "purchase" in txn:
                    kind = "insider_buy"
                elif "sale" in txn or "sell" in txn:
                    kind = "insider_sell"
                else:
                    continue
                val = _f(r.get("value_usd"))
                if val is None: continue
                rows.append(CanonicalFlow(
                    market=market.name, asof=d or (cutoff or date.today()),
                    kind=kind, scope="ticker", symbol=str(r.get("ticker") or ""),
                    value_native=val, currency=market.currency, source=source))
    return CanonicalDataset(kind="flow", market=market.name,
                              asof=cutoff or date.today(), n_rows=len(rows),
                              rows=rows, source=source)


# ─── CORPORATE ACTIONS ───────────────────────────────────────────────
def adapt_corporate_actions(repo_root: Path, market: MarketProfile,
                              cutoff: date | None = None) -> CanonicalDataset:
    if market.name == "india":
        p = repo_root / "data" / "raw" / "india" / "corporate_actions.parquet"
        source = "india.corporate_actions"
        div_col = "dividend"
    else:
        p = repo_root / "usa" / "data" / "raw" / "us" / "corporate_actions.parquet"
        source = "usa.research.corporate_actions"
        div_col = "dividend_usd"

    rows: list[CanonicalCorporateAction] = []
    if p.exists():
        df = pd.read_parquet(p)
        for _, r in df.iterrows():
            d = _parse_date(r.get("action_date"))
            if not _within(d, cutoff): continue
            rows.append(CanonicalCorporateAction(
                market=market.name,
                symbol=str(r.get("ticker") or ""),
                action_date=d or (cutoff or date.today()),
                dividend=_f(r.get(div_col)) or 0.0,
                split_ratio=_f(r.get("split_ratio")) or 0.0,
                currency=market.currency,
                source=source,
            ))
    return CanonicalDataset(kind="corporate_action", market=market.name,
                              asof=cutoff or date.today(), n_rows=len(rows),
                              rows=rows, source=str(p))


# ─── EARNINGS ────────────────────────────────────────────────────────
def adapt_earnings(repo_root: Path, market: MarketProfile,
                    cutoff: date | None = None) -> CanonicalDataset:
    if market.name == "india":
        # India earnings live inside the fundamentals parquet as `next_earnings`
        p = repo_root / "data" / "raw" / "india" / "fundamentals.parquet"
        source = "india.fundamentals_nse"
        rows: list[CanonicalEarnings] = []
        if p.exists():
            df = pd.read_parquet(p).reset_index()
            sym_col = df.columns[0]
            asof = cutoff or date.today()
            for _, r in df.iterrows():
                rows.append(CanonicalEarnings(
                    market=market.name, symbol=str(r[sym_col]), asof=asof,
                    next_earnings_date=_parse_date(r.get("next_earnings")),
                    last_report_date=None, last_reported_eps=None,
                    last_eps_estimate=None, last_surprise_pct=None,
                    source=source,
                ))
        return CanonicalDataset(kind="earnings", market=market.name,
                                  asof=cutoff or date.today(), n_rows=len(rows),
                                  rows=rows, source=str(p))
    else:
        p = repo_root / "usa" / "data" / "raw" / "us" / "earnings.parquet"
        source = "usa.research.earnings"
        rows = []
        if p.exists():
            df = pd.read_parquet(p)
            for _, r in df.iterrows():
                rows.append(CanonicalEarnings(
                    market=market.name, symbol=str(r.get("ticker") or ""),
                    asof=_parse_date(r.get("asof")) or (cutoff or date.today()),
                    next_earnings_date=_parse_date(r.get("next_earnings_date")),
                    last_report_date=_parse_date(r.get("last_report_date")),
                    last_reported_eps=_f(r.get("last_reported_eps")),
                    last_eps_estimate=_f(r.get("last_eps_estimate")),
                    last_surprise_pct=_f(r.get("last_surprise_pct")),
                    source=source,
                ))
        return CanonicalDataset(kind="earnings", market=market.name,
                                  asof=cutoff or date.today(), n_rows=len(rows),
                                  rows=rows, source=str(p))


# ─── MACRO ───────────────────────────────────────────────────────────
def adapt_macro(repo_root: Path, market: MarketProfile,
                 cutoff: date | None = None) -> CanonicalDataset:
    """India has no dedicated macro parquet yet — return empty for India.
    USA uses usa/data/raw/us/macro.parquet."""
    rows: list[CanonicalMacro] = []
    if market.name != "usa":
        return CanonicalDataset(kind="macro", market=market.name,
                                  asof=cutoff or date.today(), n_rows=0,
                                  source="not-yet-ingested-for-india")
    p = repo_root / "usa" / "data" / "raw" / "us" / "macro.parquet"
    source = "usa.research.macro"
    if not p.exists():
        return CanonicalDataset(kind="macro", market=market.name,
                                  asof=cutoff or date.today(), n_rows=0, source=str(p))
    # summary file has richer per-symbol trend fields
    sp = repo_root / "usa" / "reports" / "macro_summary.json"
    per_sym = {}
    if sp.exists():
        try:
            per_sym = {x["symbol"]: x for x in
                        json.loads(sp.read_text(encoding="utf-8")).get("per_symbol", [])
                        if "symbol" in x}
        except Exception:
            per_sym = {}
    df = pd.read_parquet(p)
    # last row per symbol
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["symbol", "date"])
    for sym, g in df.groupby("symbol", sort=True):
        latest = g.iloc[-1]
        d = _parse_date(latest["date"])
        if not _within(d, cutoff): continue
        trend = per_sym.get(sym, {})
        rows.append(CanonicalMacro(
            market=market.name, symbol=str(sym),
            label=str(latest.get("label") or trend.get("label") or ""),
            asof=d or (cutoff or date.today()),
            close=_f(latest.get("close")) or 0.0,
            chg_1d_pct=_f(trend.get("chg_1d_pct")),
            chg_1w_pct=_f(trend.get("chg_1w_pct")),
            chg_1m_pct=_f(trend.get("chg_1m_pct")),
            source=source,
        ))
    return CanonicalDataset(kind="macro", market=market.name,
                              asof=cutoff or date.today(), n_rows=len(rows),
                              rows=rows, source=str(p))


# ─── FLOW PROXY (ETF for USA, sector composite for India) ────────────
def adapt_flow_proxy(repo_root: Path, market: MarketProfile,
                      cutoff: date | None = None) -> CanonicalDataset:
    rows: list[CanonicalFlowProxy] = []
    if market.name == "usa":
        summary = repo_root / "usa" / "reports" / "etf_flows_summary.json"
        source = "usa.research.etf_flows"
        if summary.exists():
            data = json.loads(summary.read_text(encoding="utf-8"))
            asof = _parse_date(data.get("asof")) or (cutoff or date.today())
            for e in data.get("per_etf", []):
                if "return_pct" not in e: continue
                rows.append(CanonicalFlowProxy(
                    market=market.name, symbol=e.get("ticker", ""),
                    label=e.get("label", ""),
                    asof=asof,
                    period_days=int(e.get("period_days", 0)),
                    return_pct=_f(e.get("return_pct")) or 0.0,
                    avg_dollar_volume=_f(e.get("avg_dollar_volume_usd")),
                    currency=market.currency,
                    source=source,
                ))
    else:
        # India: sector_context.json — frozen but present
        p = repo_root / "reports" / "sector_context.json"
        source = "research.sector_intelligence"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                asof = _parse_date(data.get("asof_utc")) or (cutoff or date.today())
                sectors = data.get("sectors", {})
                if isinstance(sectors, dict):
                    for name, s in sectors.items():
                        if isinstance(s, dict):
                            rows.append(CanonicalFlowProxy(
                                market=market.name, symbol=str(name),
                                label=str(name), asof=asof,
                                period_days=int(s.get("window_days", 0) or 0),
                                return_pct=_f(s.get("return_pct") or s.get("mean_return_pct")) or 0.0,
                                avg_dollar_volume=None,
                                currency=market.currency,
                                source=source))
            except Exception:
                pass
    return CanonicalDataset(kind="flow_proxy", market=market.name,
                              asof=cutoff or date.today(), n_rows=len(rows),
                              rows=rows, source="")


# ─── HOLDINGS (SEC 13F view for USA) ────────────────────────────────
def adapt_holdings(repo_root: Path, market: MarketProfile,
                    cutoff: date | None = None) -> CanonicalDataset:
    rows: list[CanonicalHolding] = []
    if market.name != "usa":
        return CanonicalDataset(kind="holding", market=market.name,
                                  asof=cutoff or date.today(), n_rows=0,
                                  source="not-yet-available-india")
    p = repo_root / "usa" / "data" / "raw" / "us" / "institutional_holders.parquet"
    source = "usa.research.sec_13f"
    if p.exists():
        df = pd.read_parquet(p)
        for _, r in df.iterrows():
            d = _parse_date(r.get("date_reported"))
            if not _within(d, cutoff): continue
            rows.append(CanonicalHolding(
                market=market.name,
                symbol=str(r.get("ticker") or ""),
                holder=str(r.get("holder") or ""),
                shares=_f(r.get("shares")),
                pct_out=_f(r.get("pct_out")),
                value_native=_f(r.get("value_usd")),
                date_reported=d,
                currency=market.currency,
                source=source,
            ))
    return CanonicalDataset(kind="holding", market=market.name,
                              asof=cutoff or date.today(), n_rows=len(rows),
                              rows=rows, source=str(p))


# ─── Top-level runner ────────────────────────────────────────────────
def adapt_all(repo_root: Path, market: MarketProfile,
                cutoff: date | None = None,
                include: list[str] | None = None) -> dict[str, CanonicalDataset]:
    """Run every adapter and return a dict keyed by canonical kind.

    `include` lets a caller restrict to specific kinds (e.g. for Market
    Intelligence which only needs bar+macro+flow_proxy).
    `cutoff` is the walk-forward freeze date — every row on or after
    cutoff+1 is silently dropped, so the same repo checkout can be
    replayed at any historical asof.
    """
    all_kinds = {
        "bar":               lambda: adapt_prices(repo_root, market, cutoff=cutoff),
        "fundamentals":      lambda: adapt_fundamentals(repo_root, market, cutoff),
        "news":              lambda: adapt_news(repo_root, market, cutoff),
        "flow":              lambda: adapt_flows(repo_root, market, cutoff),
        "corporate_action":  lambda: adapt_corporate_actions(repo_root, market, cutoff),
        "earnings":          lambda: adapt_earnings(repo_root, market, cutoff),
        "macro":             lambda: adapt_macro(repo_root, market, cutoff),
        "flow_proxy":        lambda: adapt_flow_proxy(repo_root, market, cutoff),
        "holding":           lambda: adapt_holdings(repo_root, market, cutoff),
    }
    if include:
        all_kinds = {k: v for k, v in all_kinds.items() if k in include}
    return {k: fn() for k, fn in all_kinds.items()}
