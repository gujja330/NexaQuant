"""Market Intelligence Engine v1.0 — deterministic, cross-market.

Consumes canonical data only. Emits a market-level snapshot:

  regime           bull / bear / neutral / stress
  breadth          % of universe above 20-day MA, % at 52W high, adv/decl proxy
  volatility       VIX / MOVE levels + trend
  liquidity        aggregate volume trend
  macro            rates + dollar + gold + oil (USA only)
  sector_rotation  ETF flow proxy (USA) or sector composites (India)
  news_pulse       market-wide average sentiment
  flow_pulse       FII/DII balance (India) or insider net (USA)
  composite_score  0-100 Market Health
  regime_label     human-readable string

Every output field carries its **evidence** — the exact numbers that
produced the classification — so the downstream AI Market Analyst can
narrate the "why" without duplicating math.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from statistics import mean, median

import pandas as pd

from backend.canonical.model import MarketProfile
from backend.canonical.adapters import adapt_all, adapt_prices
from backend.canonical.schemas import CanonicalDataset


# ── Result shape ──────────────────────────────────────────────────
@dataclass
class MarketSignal:
    key:        str          # "regime", "breadth", etc.
    value:      float | str
    label:      str          # human-readable
    evidence:   dict = field(default_factory=dict)


@dataclass
class MarketIntelligenceResult:
    market:            str
    asof:              date
    engine_version:    str = "v1.0"
    signals:           dict[str, MarketSignal] = field(default_factory=dict)
    composite_score:   float = 0.0        # 0-100 Market Health
    regime:            str = "unknown"    # bull / bear / neutral / stress
    regime_label:      str = ""
    n_inputs:          int = 0
    notes:             list[str] = field(default_factory=list)


# ── Metric helpers (deterministic, no random_state anywhere) ─────
def _pct_above_ma(bars_by_symbol: dict[str, pd.DataFrame], window: int = 20) -> tuple[float, dict]:
    n_total = 0; n_above = 0
    for sym, df in bars_by_symbol.items():
        if len(df) < window + 1: continue
        ma = df["close"].tail(window).mean()
        n_total += 1
        if df["close"].iloc[-1] > ma:
            n_above += 1
    if n_total == 0:
        return 0.0, {"n_symbols": 0}
    return round(100.0 * n_above / n_total, 2), {"n_symbols": n_total, "n_above": n_above}


def _pct_at_52w_high(bars_by_symbol: dict[str, pd.DataFrame], threshold: float = 0.98) -> tuple[float, dict]:
    n_total = 0; n_at = 0
    for sym, df in bars_by_symbol.items():
        if len(df) < 60: continue
        window = df["close"].tail(252)
        high = window.max()
        last = df["close"].iloc[-1]
        n_total += 1
        if high > 0 and last / high >= threshold:
            n_at += 1
    if n_total == 0:
        return 0.0, {"n_symbols": 0}
    return round(100.0 * n_at / n_total, 2), {"n_symbols": n_total, "n_at_high": n_at,
                                                 "threshold": threshold}


def _volume_trend_pct(bars_by_symbol: dict[str, pd.DataFrame]) -> tuple[float, dict]:
    """Median trailing-5 vs trailing-20 volume ratio across universe."""
    ratios: list[float] = []
    for _, df in bars_by_symbol.items():
        if len(df) < 25 or df["volume"].tail(20).sum() == 0: continue
        r5 = df["volume"].tail(5).mean()
        r20 = df["volume"].tail(20).mean()
        if r20 > 0:
            ratios.append(r5 / r20)
    if not ratios:
        return 0.0, {"n_symbols": 0}
    med = median(ratios)
    return round((med - 1.0) * 100, 2), {"n_symbols": len(ratios), "median_ratio": round(med, 3)}


# ── Engine ─────────────────────────────────────────────────────────
class MarketIntelligenceEngine:
    def __init__(self, repo_root: Path, market: MarketProfile):
        self.repo_root = Path(repo_root)
        self.market = market

    def run(self, cutoff: date | None = None) -> MarketIntelligenceResult:
        result = MarketIntelligenceResult(
            market=self.market.name,
            asof=cutoff or date.today(),
        )
        canon = adapt_all(self.repo_root, self.market, cutoff=cutoff,
                            include=["bar", "macro", "flow_proxy", "flow", "news"])
        result.n_inputs = sum(ds.n_rows for ds in canon.values())

        # ── Prepare per-symbol bar frames (dedupe + sort) ────────
        bars = canon.get("bar")
        bars_by_sym: dict[str, pd.DataFrame] = {}
        if bars and bars.rows:
            df = pd.DataFrame([{"symbol": b.symbol, "date": b.date,
                                  "close": b.close, "volume": b.volume}
                                 for b in bars.rows])
            df["date"] = pd.to_datetime(df["date"])
            for sym, g in df.groupby("symbol", sort=True):
                g = g.drop_duplicates(subset=["date"], keep="last").sort_values("date")
                bars_by_sym[sym] = g.reset_index(drop=True)

        # ── Breadth ──────────────────────────────────────────────
        pct20, ev20 = _pct_above_ma(bars_by_sym, window=20)
        pct52, ev52 = _pct_at_52w_high(bars_by_sym, threshold=0.95)
        result.signals["breadth_above_20ma"] = MarketSignal(
            key="breadth_above_20ma", value=pct20,
            label=f"{pct20:.1f}% of universe above 20-day MA",
            evidence=ev20,
        )
        result.signals["breadth_at_52w_high"] = MarketSignal(
            key="breadth_at_52w_high", value=pct52,
            label=f"{pct52:.1f}% within 5% of 52W high",
            evidence=ev52,
        )

        # ── Liquidity ────────────────────────────────────────────
        vt, evv = _volume_trend_pct(bars_by_sym)
        result.signals["liquidity_5v20"] = MarketSignal(
            key="liquidity_5v20", value=vt,
            label=("volume rising" if vt > 5 else "volume falling" if vt < -5 else "volume flat")
                   + f" ({vt:+.1f}%)",
            evidence=evv,
        )

        # ── Benchmark trend (short-term regime) ──────────────────
        # For USA: ^GSPC (via _IDX_GSPC_D1). For India: ^NSEI (NSEI_D1).
        bench_symbol = self.market.benchmark.lstrip("^").replace("GSPC", "_IDX_GSPC") \
                                              .replace("NSEI", "NSEI")
        bench_bars = None
        # try direct filename lookup — market has different conventions
        if self.market.name == "usa":
            p = self.repo_root / "usa" / "data" / "raw" / "us" / "_IDX_GSPC_D1.parquet"
        else:
            p = self.repo_root / "data" / "raw" / "india" / "NSEI_D1.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                if df.index.name and df.index.name.lower() in ("date", "time", "datetime"):
                    df = df.reset_index()
                    df.columns = [c.lower() for c in df.columns]
                if cutoff is not None and "date" in df.columns:
                    df = df[pd.to_datetime(df["date"]) <= pd.Timestamp(cutoff)]
                elif cutoff is not None and "time" in df.columns:
                    df = df[pd.to_datetime(df["time"]) <= pd.Timestamp(cutoff)]
                if not df.empty and "close" in df.columns:
                    bench_bars = df.tail(60).reset_index(drop=True)
            except Exception:
                bench_bars = None

        bench_change_5d = 0.0; bench_change_1m = 0.0
        if bench_bars is not None and len(bench_bars) >= 21:
            last = float(bench_bars["close"].iloc[-1])
            d5 = float(bench_bars["close"].iloc[-6])
            d20 = float(bench_bars["close"].iloc[-21])
            if d5 > 0:  bench_change_5d = round((last / d5 - 1.0) * 100, 2)
            if d20 > 0: bench_change_1m = round((last / d20 - 1.0) * 100, 2)

        result.signals["benchmark_5d_pct"] = MarketSignal(
            key="benchmark_5d_pct", value=bench_change_5d,
            label=f"{self.market.benchmark} 5-day: {bench_change_5d:+.2f}%",
            evidence={"symbol": self.market.benchmark, "window_days": 5},
        )
        result.signals["benchmark_1m_pct"] = MarketSignal(
            key="benchmark_1m_pct", value=bench_change_1m,
            label=f"{self.market.benchmark} 1-month: {bench_change_1m:+.2f}%",
            evidence={"symbol": self.market.benchmark, "window_days": 21},
        )

        # ── Volatility (USA has ^VIX + ^MOVE via canonical macro; India has INDIAVIX) ─
        vix_last = None; move_last = None
        if self.market.name == "usa":
            macro = canon.get("macro")
            if macro:
                for m in macro.rows:
                    if m.symbol == "^VIX":   vix_last = m.close
                    if m.symbol == "^MOVE":  move_last = m.close
        else:
            p = self.repo_root / "data" / "raw" / "india" / "INDIAVIX_D1.parquet"
            if p.exists():
                try:
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    if "close" in df.columns and len(df) > 0:
                        vix_last = float(df["close"].iloc[-1])
                except Exception: pass

        if vix_last is not None:
            vol_label = ("elevated" if vix_last > 25 else "moderate" if vix_last > 18 else "calm")
            result.signals["vix"] = MarketSignal(
                key="vix", value=round(vix_last, 2),
                label=f"VIX {vix_last:.2f} ({vol_label})",
                evidence={"symbol": "^VIX" if self.market.name == "usa" else "INDIAVIX"},
            )
        if move_last is not None:
            result.signals["move"] = MarketSignal(
                key="move", value=round(move_last, 2),
                label=f"MOVE {move_last:.2f}",
                evidence={"symbol": "^MOVE"},
            )

        # ── Macro (USA only for now) ─────────────────────────────
        macro_summary = {}
        if self.market.name == "usa":
            macro = canon.get("macro")
            if macro:
                for m in macro.rows:
                    macro_summary[m.symbol] = {
                        "label": m.label, "last": round(m.close, 3),
                        "chg_1d_pct": m.chg_1d_pct, "chg_1m_pct": m.chg_1m_pct,
                    }
            if macro_summary:
                result.signals["macro"] = MarketSignal(
                    key="macro", value=len(macro_summary),
                    label=f"{len(macro_summary)} macro indicators ingested",
                    evidence=macro_summary,
                )

        # ── Sector rotation / flow proxy ─────────────────────────
        fp = canon.get("flow_proxy")
        if fp and fp.rows:
            top = sorted(fp.rows, key=lambda r: r.return_pct, reverse=True)[:3]
            bot = sorted(fp.rows, key=lambda r: r.return_pct)[:3]
            result.signals["sector_rotation"] = MarketSignal(
                key="sector_rotation", value=len(fp.rows),
                label=(f"top: {top[0].label} {top[0].return_pct:+.1f}%; "
                       f"bottom: {bot[0].label} {bot[0].return_pct:+.1f}%") if top and bot else "",
                evidence={
                    "top_3": [{"symbol": r.symbol, "label": r.label,
                                 "return_pct": r.return_pct} for r in top],
                    "bottom_3": [{"symbol": r.symbol, "label": r.label,
                                    "return_pct": r.return_pct} for r in bot],
                },
            )

        # ── News pulse (market-wide avg sentiment) ───────────────
        news = canon.get("news")
        if news and news.rows:
            avg_sent = mean([n.sentiment for n in news.rows]) if news.rows else 0.0
            n_pos = sum(1 for n in news.rows if n.sentiment > 0.1)
            n_neg = sum(1 for n in news.rows if n.sentiment < -0.1)
            result.signals["news_pulse"] = MarketSignal(
                key="news_pulse", value=round(avg_sent, 3),
                label=f"news pulse {avg_sent:+.2f} (pos={n_pos} · neg={n_neg})",
                evidence={"n_tickers": len(news.rows), "n_positive": n_pos, "n_negative": n_neg},
            )

        # ── Flow pulse (institutional net) ───────────────────────
        flows = canon.get("flow")
        if flows and flows.rows:
            if self.market.name == "india":
                latest_by_kind = {}
                for f in flows.rows:
                    latest_by_kind.setdefault(f.kind, []).append(f)
                fii = sum(f.value_native for f in latest_by_kind.get("foreign_institutional", []))
                dii = sum(f.value_native for f in latest_by_kind.get("domestic_institutional", []))
                result.signals["flow_pulse"] = MarketSignal(
                    key="flow_pulse", value=round(fii + dii, 2),
                    label=(f"FII net ₹{fii:,.0f} Cr · DII net ₹{dii:,.0f} Cr"),
                    evidence={"fii_net": round(fii, 2), "dii_net": round(dii, 2),
                                "n_rows": len(flows.rows)},
                )
            else:
                buy = sum(f.value_native for f in flows.rows if f.kind == "insider_buy")
                sell = sum(f.value_native for f in flows.rows if f.kind == "insider_sell")
                net = buy - sell
                result.signals["flow_pulse"] = MarketSignal(
                    key="flow_pulse", value=round(net, 2),
                    label=f"insider net ${net:+,.0f} (buys ${buy:,.0f} / sells ${sell:,.0f})",
                    evidence={"insider_buy": round(buy, 2), "insider_sell": round(sell, 2),
                                "net": round(net, 2)},
                )

        # ── Composite Market Health (0-100) — deterministic weights ─
        # breadth 30% · benchmark_1m 25% · liquidity 15% · vol 15% · news 10% · flow 5%
        components: list[tuple[float, float]] = []   # (score, weight)
        components.append((_clamp01(pct20 / 100.0) * 100, 0.30))
        components.append((_clamp01((bench_change_1m + 10) / 20.0) * 100, 0.25))
        components.append((_clamp01((vt + 20) / 40.0) * 100, 0.15))
        if vix_last is not None:
            # invert: high VIX bad
            components.append((_clamp01((35 - vix_last) / 25.0) * 100, 0.15))
        news_sig = result.signals.get("news_pulse")
        if news_sig:
            components.append((_clamp01((float(news_sig.value) + 1.0) / 2.0) * 100, 0.10))
        flow_sig = result.signals.get("flow_pulse")
        if flow_sig:
            # sign-only heuristic — positive net is good
            components.append((70.0 if float(flow_sig.value) > 0 else 30.0, 0.05))

        total_w = sum(w for _, w in components) or 1.0
        composite = sum(s * w for s, w in components) / total_w
        result.composite_score = round(composite, 2)

        # ── Regime classification ────────────────────────────────
        if result.composite_score >= 65 and pct20 > 55:
            result.regime = "bull"
            result.regime_label = "Bullish · broad participation"
        elif result.composite_score <= 35 or (vix_last and vix_last > 30):
            result.regime = "bear" if result.composite_score <= 30 else "stress"
            result.regime_label = ("Bearish · defensive stance" if result.regime == "bear"
                                    else "Stressed · risk-off signals")
        elif result.composite_score < 45:
            result.regime = "neutral"
            result.regime_label = "Neutral · leaning cautious"
        else:
            result.regime = "neutral"
            result.regime_label = "Neutral · constructive"

        result.notes.append(f"engine v{result.engine_version} · deterministic · "
                             f"{len(components)} weighted components")
        return result


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))
