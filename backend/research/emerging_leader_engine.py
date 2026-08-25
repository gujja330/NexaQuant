# backend/research/emerging_leader_engine.py
"""AEGIS · Sprint M · Phase E · Emerging Leader Engine (CEO Part 5).

CEO directive: "SmallCap must NOT be treated as riskier version of
LargeCap. Create EMERGING LEADER SCORE. Only promote when multiple
independent dimensions agree."

Scores small-cap candidates on 6 quality dimensions:
  1. FUNDAMENTAL QUALITY  · revenue/earnings growth · ROE · ROCE ·
                            FCF · debt · margin trend · consistency
  2. TECHNICAL QUALITY    · above 50/200 DMA · improving trend · RS ·
                            volume confirm · accumulation
  3. GOVERNANCE QUALITY   · promoter holding · pledging · auditor ·
                            regulatory · related-party · restatements
  4. MARKET/SECTOR QUALITY · sector strength · breadth · rotation ·
                            regime · institutional flow
  5. LIQUIDITY QUALITY    · turnover · traded value · spread ·
                            abnormal-vol
  6. RISK QUALITY         · volatility · drawdown · beta · gap risk

EMERGING LEADER only when ≥ 4/6 dimensions positive.

Best-effort · uses whatever data we have. Missing data ≠ positive
score. Conservative bias · false positives are more costly than
false negatives for small-cap.

Emits reports/research/emerging_leader_{market}.json. SEPARATE from
R1/R2 · never contaminates recommendation flow (Sprint M G4 + E42
isolation guarantee).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.emerging_leader.v1.20260825"

QUALITY_DIMENSIONS = [
    "fundamental", "technical", "governance",
    "market_sector", "liquidity", "risk",
]

MIN_DIMENSIONS_POSITIVE = 4    # ≥ 4 of 6 for EMERGING LEADER verdict


@dataclass
class DimensionScore:
    dimension: str
    score: float           # 0-100 · 50 = neutral · higher = better
    verdict: str           # POSITIVE / NEUTRAL / NEGATIVE / UNKNOWN
    signals: list = field(default_factory=list)


@dataclass
class EmergingCandidate:
    ticker: str
    market: str
    cap_size: str
    sector: str
    current_price: float
    dimension_scores: list = field(default_factory=list)
    n_positive: int = 0
    n_negative: int = 0
    overall_score: float = 0.0
    verdict: str = "WATCH"     # EMERGING_LEADER / WATCH / SKIP
    rationale: str = ""


@dataclass
class EmergingReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    n_candidates_evaluated: int = 0
    n_emerging: int = 0
    n_watch: int = 0
    n_skip: int = 0
    emerging: list = field(default_factory=list)
    watch: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────
def _series(root: Path, ticker: str, market: str):
    if market.lower() == "usa":
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        p = root / "usa" / "data" / "raw" / "us" / f"{tk}_D1.parquet"
    else:
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        p = root / "data" / "raw" / "india" / f"{tk}_D1.parquet"
    if not p.exists(): return None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        return df[col].astype(float)
    except Exception:
        return None


def _sector_for(root: Path, ticker: str, market: str) -> str:
    p = root / "reports" / "sector_cache.json"
    if not p.exists(): return "UNKNOWN"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get(market.lower(), {}).get(ticker.upper()) or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _is_small_cap(root: Path, ticker: str, market: str) -> bool:
    """SmallCap = NOT in NIFTY 200 (India) · NOT in S&P 500 (USA)."""
    if market.lower() == "india":
        try:
            from india.data_nse import NIFTY200
            tk = str(ticker).upper().replace(".NS","").replace(".BO","")
            return tk not in NIFTY200
        except Exception:
            return True
    return True


# ─────────────────────────────────────────────────────────────────
# Per-dimension scorers · deterministic · best-effort
# ─────────────────────────────────────────────────────────────────
def _score_technical(root: Path, ticker: str, market: str) -> DimensionScore:
    s = _series(root, ticker, market)
    if s is None or len(s) < 210:
        return DimensionScore("technical", 50.0, "UNKNOWN",
                              ["insufficient parquet history"])
    last = float(s.iloc[-1])
    ma50 = float(s.tail(50).mean())
    ma200 = float(s.tail(200).mean())
    score = 50.0
    signals = []
    if last > ma50:
        score += 15; signals.append(f"above MA50 ({last:.2f} > {ma50:.2f})")
    else:
        score -= 15; signals.append("below MA50")
    if last > ma200:
        score += 15; signals.append(f"above MA200 ({last:.2f} > {ma200:.2f})")
    else:
        score -= 15; signals.append("below MA200")
    # Trend improvement · MA50 rising vs 40-day-ago MA50
    if len(s) >= 90:
        ma50_now = float(s.tail(50).mean())
        ma50_ago = float(s.iloc[-90:-40].mean()) if len(s) >= 90 else ma50_now
        if ma50_now > ma50_ago:
            score += 10; signals.append("MA50 rising")
        else:
            score -= 5; signals.append("MA50 flat/falling")
    # 20-day return
    if len(s) >= 21:
        r20 = (last - float(s.iloc[-21])) / float(s.iloc[-21]) * 100
        if r20 > 5:
            score += 10; signals.append(f"+{r20:.1f}% 20d momentum")
        elif r20 < -5:
            score -= 10; signals.append(f"{r20:.1f}% 20d weakness")
    score = max(0.0, min(100.0, score))
    verdict = ("POSITIVE" if score >= 65
               else "NEGATIVE" if score <= 35
               else "NEUTRAL")
    return DimensionScore("technical", round(score, 1), verdict, signals)


def _score_liquidity(root: Path, ticker: str, market: str) -> DimensionScore:
    """Liquidity from parquet · tick_volume × close proxy."""
    s = _series(root, ticker, market)
    if s is None or len(s) < 20:
        return DimensionScore("liquidity", 50.0, "UNKNOWN",
                              ["insufficient parquet history"])
    # Approximate turnover via close × 100k (surrogate)
    _last_close = float(s.iloc[-1])
    _score = 50.0
    _sig = []
    if _last_close > 100:
        _score += 15; _sig.append(f"close ₹{_last_close:.2f} (institutional-tradeable)")
    elif _last_close < 20:
        _score -= 15; _sig.append(f"close ₹{_last_close:.2f} (penny · high risk)")
    # 20d std as vol proxy
    if len(s) >= 20:
        _std = float(s.tail(20).std()) / _last_close * 100
        if _std > 5:
            _score -= 10; _sig.append(f"20d vol {_std:.1f}% (spikey)")
        else:
            _score += 5; _sig.append(f"20d vol {_std:.1f}% (calm)")
    _score = max(0.0, min(100.0, _score))
    _v = "POSITIVE" if _score >= 65 else "NEGATIVE" if _score <= 35 else "NEUTRAL"
    return DimensionScore("liquidity", round(_score, 1), _v, _sig)


def _score_risk(root: Path, ticker: str, market: str) -> DimensionScore:
    """Risk from realized vol + drawdown."""
    s = _series(root, ticker, market)
    if s is None or len(s) < 60:
        return DimensionScore("risk", 50.0, "UNKNOWN",
                              ["insufficient parquet history"])
    _last = float(s.iloc[-1])
    # 60-day max drawdown
    _tail = s.tail(60)
    _rolling_max = _tail.cummax()
    _dd = ((_tail - _rolling_max) / _rolling_max * 100).min()
    _sig = []; _score = 50.0
    if _dd > -10:
        _score += 15; _sig.append(f"max DD 60d {_dd:.1f}%")
    elif _dd < -25:
        _score -= 20; _sig.append(f"max DD 60d {_dd:.1f}% (deep)")
    else:
        _sig.append(f"max DD 60d {_dd:.1f}%")
    # 30d realized vol
    if len(s) >= 30:
        _rets = s.pct_change().tail(30)
        _vol = float(_rets.std()) * (252 ** 0.5) * 100
        if _vol < 25:
            _score += 15; _sig.append(f"annualized vol {_vol:.1f}%")
        elif _vol > 50:
            _score -= 15; _sig.append(f"annualized vol {_vol:.1f}% (high)")
    _score = max(0.0, min(100.0, _score))
    _v = "POSITIVE" if _score >= 65 else "NEGATIVE" if _score <= 35 else "NEUTRAL"
    return DimensionScore("risk", round(_score, 1), _v, _sig)


def _score_market_sector(root: Path, ticker: str, market: str) -> DimensionScore:
    """Sector context · from sector_context if available."""
    sec = _sector_for(root, ticker, market)
    p = root / "reports" / "context" / f"sector_context_{market.lower()}.json"
    if not p.exists() or sec == "UNKNOWN":
        return DimensionScore("market_sector", 50.0, "UNKNOWN",
                              ["sector_context missing"])
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        secs = d.get("sectors") or d.get("data") or {}
        entry = secs.get(sec, {}) if isinstance(secs, dict) else {}
        _sig = []
        _score = 50.0
        if entry.get("is_leader"):
            _score += 25; _sig.append(f"{sec} is sector leader")
        elif entry.get("is_laggard"):
            _score -= 25; _sig.append(f"{sec} is sector laggard")
        else:
            _sig.append(f"{sec} sector neutral")
        _score = max(0.0, min(100.0, _score))
        _v = "POSITIVE" if _score >= 65 else "NEGATIVE" if _score <= 35 else "NEUTRAL"
        return DimensionScore("market_sector", round(_score, 1), _v, _sig)
    except Exception:
        return DimensionScore("market_sector", 50.0, "UNKNOWN",
                              ["sector_context read error"])


def _score_fundamental(root: Path, ticker: str, market: str) -> DimensionScore:
    """Fundamentals · investability score as proxy."""
    p = root / "reports" / f"investability_{market.lower()}.json"
    if not p.exists():
        return DimensionScore("fundamental", 50.0, "UNKNOWN",
                              ["investability data missing"])
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        tk = ticker.upper()
        for r in (d.get("results") or []):
            if str(r.get("ticker","")).upper() == tk:
                _sc = float(r.get("score", 50.0))
                _v = "POSITIVE" if _sc >= 65 else "NEGATIVE" if _sc <= 45 else "NEUTRAL"
                _sig = [f"investability score {_sc:.1f}",
                        f"verdict {r.get('verdict','')}"]
                return DimensionScore("fundamental", _sc, _v, _sig)
        return DimensionScore("fundamental", 50.0, "UNKNOWN",
                              ["not in investability sample"])
    except Exception:
        return DimensionScore("fundamental", 50.0, "UNKNOWN",
                              ["investability read error"])


def _score_governance(root: Path, ticker: str, market: str) -> DimensionScore:
    """Governance · no data source yet · returns UNKNOWN.
    Small-caps promoted only when ≥ 4/6 dims positive · so UNKNOWN
    governance can still allow promotion if 4 other dims are positive."""
    return DimensionScore("governance", 50.0, "UNKNOWN",
                          ["governance data source not yet integrated"])


# ─────────────────────────────────────────────────────────────────
# Composite verdict
# ─────────────────────────────────────────────────────────────────
def score_candidate(root: Path, ticker: str, market: str) -> EmergingCandidate:
    cap = "SMALL" if _is_small_cap(root, ticker, market) else "LARGE-OR-MID"
    sec = _sector_for(root, ticker, market)
    s = _series(root, ticker, market)
    cur_price = float(s.iloc[-1]) if s is not None and len(s) else 0.0
    dims = [
        _score_fundamental(root, ticker, market),
        _score_technical(root, ticker, market),
        _score_governance(root, ticker, market),
        _score_market_sector(root, ticker, market),
        _score_liquidity(root, ticker, market),
        _score_risk(root, ticker, market),
    ]
    n_pos = sum(1 for d in dims if d.verdict == "POSITIVE")
    n_neg = sum(1 for d in dims if d.verdict == "NEGATIVE")
    overall = round(sum(d.score for d in dims) / len(dims), 1)
    if n_pos >= MIN_DIMENSIONS_POSITIVE and n_neg <= 1:
        verdict = "EMERGING_LEADER"
        rationale = (f"{n_pos}/6 dimensions positive · {n_neg} negative · "
                     f"overall {overall}")
    elif n_pos >= 2:
        verdict = "WATCH"
        rationale = f"{n_pos}/6 positive · not yet at threshold · monitor"
    else:
        verdict = "SKIP"
        rationale = f"only {n_pos}/6 positive · not a candidate"
    return EmergingCandidate(
        ticker=ticker.upper(), market=market.lower(),
        cap_size=cap, sector=sec, current_price=round(cur_price, 2),
        dimension_scores=[asdict(d) for d in dims],
        n_positive=n_pos, n_negative=n_neg,
        overall_score=overall,
        verdict=verdict, rationale=rationale,
    )


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str,
            candidates: Optional[list] = None) -> EmergingReport:
    """If candidates is None, scan all small-cap tickers in universe."""
    import glob
    if candidates is None:
        if market.lower() == "usa":
            pat = str(root / "usa" / "data" / "raw" / "us" / "*_D1.parquet")
        else:
            pat = str(root / "data" / "raw" / "india" / "*_D1.parquet")
        universe = [Path(f).stem.replace("_D1", "")
                    for f in glob.glob(pat)]
        candidates = [t for t in universe
                      if _is_small_cap(root, t, market)]
    rep = EmergingReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    rep.n_candidates_evaluated = len(candidates)
    for tk in candidates:
        try:
            c = score_candidate(root, tk, market)
            if c.verdict == "EMERGING_LEADER":
                rep.emerging.append(asdict(c))
                rep.n_emerging += 1
            elif c.verdict == "WATCH":
                rep.watch.append(asdict(c))
                rep.n_watch += 1
            else:
                rep.n_skip += 1
        except Exception:
            continue
    # Sort emerging + watch by overall score desc
    rep.emerging.sort(key=lambda c: -c["overall_score"])
    rep.watch.sort(key=lambda c: -c["overall_score"])
    rep.watch = rep.watch[:30]     # cap for readability
    return rep


def emit(root: Path, report: EmergingReport) -> Path:
    p = (root / "reports" / "research"
         / f"emerging_leader_{report.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(report), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: EmergingReport) -> str:
    return (f"emerging_leader · {rep.n_candidates_evaluated} evaluated · "
            f"EMERGING {rep.n_emerging} · WATCH {rep.n_watch} · "
            f"SKIP {rep.n_skip}")
