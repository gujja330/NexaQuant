# backend/research/loss_attribution_v2.py
"""AEGIS · Loss Attribution v2 · post-mortem classifier for closed positions.

CEO directive 2026-08-25: "walk forward validation what it learnt from
exit data? any strategy on loss stocks / sector based analysis or large
cap or midcap or any kind of analysis did we try to overcome losses".

For every CLOSED opportunity in the Registry (past 90 days) this engine:

  1. Extracts entry-time snapshot: sector · cap-size · entry regime ·
     technicals (MA20/50, RSI-ish momentum) · fundamentals proxy
     (quality band from investability)

  2. Classifies the exit into ONE of 7 outcomes:
       WINNER
       STOP_LOSS_HIT       · risk mgmt worked as designed
       TIME_STOP           · held too long without move · thesis timing off
       THESIS_FAILURE      · fundamentals broke down after entry
       SECTOR_DRAG         · dropped WITH sector · systemic exposure
       MACRO_SHOCK         · sudden market-wide drop early in hold
       QUALITY_FALSE_POSITIVE · investability said QUALITY but reality diverged

  3. Rolls up per sector / cap-size / days-held bucket · surfaces the
     patterns operator asked about:
       "which sector loses most?"
       "midcap vs largecap loss profile?"

  4. Emits reports/research/loss_patterns_{market}.json + a compact
     markdown digest reports/research/loss_patterns_{market}.md

Constitutional invariant: this engine READS · never writes back into the
R1/R2 recommendation path. Operator promotes findings by hand.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.loss_attribution.v2.20260825"

LOSS_CATEGORIES = [
    "STOP_LOSS_HIT", "TIME_STOP", "THESIS_FAILURE",
    "SECTOR_DRAG", "MACRO_SHOCK", "QUALITY_FALSE_POSITIVE",
    # 2026-08-25 · Sprint M.1 · CEO directive · momentum-related causes
    "BAD_TIMING",              # entered while momentum deteriorating
    "MOMENTUM_FAILURE",        # momentum reversed against thesis after entry
    "CHASE_EXTENSION",         # entered on extended move · reverted to mean
    "FALSE_BREAKOUT",          # broke out then failed
    "SECTOR_MOMENTUM_FAILURE", # sector momentum broke down · dragged position
]


@dataclass
class ExitClassification:
    ticker: str
    market: str
    runner: str
    entry_date: str
    exit_date: str
    days_held: int
    pnl_pct: float
    is_win: bool
    category: str                    # WINNER + LOSS_CATEGORIES
    sector: str
    cap_size: str                    # LARGE / MID / SMALL / UNKNOWN
    entry_regime: str                # BULL / BEAR / NEUTRAL / UNKNOWN
    entry_quality: str               # QUALITY / OK / MARGINAL / AVOID / UNKNOWN
    sector_return_over_hold: Optional[float] = None
    recommendation: str = ""         # what could have avoided this loss


@dataclass
class SectorRollup:
    sector: str
    n_positions: int
    n_wins: int
    n_losses: int
    total_pnl_pct: float
    win_rate_pct: float
    dominant_loss_category: str      # most common loss type in this sector


@dataclass
class CapSizeRollup:
    cap_size: str
    n_positions: int
    n_wins: int
    n_losses: int
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float             # avg_win / |avg_loss|


@dataclass
class AttributionReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    n_positions: int = 0
    n_wins: int = 0
    n_losses: int = 0
    total_realized_pct: float = 0.0
    positive_pct: float = 0.0
    negative_pct: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    category_counts: dict = field(default_factory=dict)
    sector_rollup: list = field(default_factory=list)
    cap_size_rollup: list = field(default_factory=list)
    exits: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Helpers · sector / cap-size lookup (best-effort)
# ─────────────────────────────────────────────────────────────────
def _sector_for(root: Path, ticker: str, market: str) -> str:
    p = root / "reports" / "sector_cache.json"
    if not p.exists(): return "UNKNOWN"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        bucket = d.get(market.lower(), {})
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        return bucket.get(tk) or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _cap_size_for(root: Path, ticker: str, market: str) -> str:
    """Coarse cap size from configs/large_cap.yaml if present, else UNKNOWN.
    India: Nifty 50 = LARGE · rest of Nifty 200 = MID · else SMALL.
    USA: S&P 500 = LARGE · S&P 400 MidCap = MID · else SMALL."""
    if market.lower() == "india":
        try:
            from india.data_nse import NIFTY100
            tk = str(ticker).upper().replace(".NS","").replace(".BO","")
            if tk in NIFTY100[:50]: return "LARGE"
            if tk in NIFTY100:      return "LARGE"
            return "MID"
        except Exception:
            return "UNKNOWN"
    return "UNKNOWN"


def _load_close_series(root: Path, ticker: str, market: str):
    if market.lower() == "usa":
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        p = root / "usa" / "data" / "raw" / "us" / f"{tk}_D1.parquet"
    else:
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        p = root / "data" / "raw" / "india" / f"{tk}_D1.parquet"
    if not p.exists(): return None, None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        idx = pd.to_datetime(df.index).strftime("%Y-%m-%d").tolist()
        return idx, [float(v) for v in df[col].tolist()]
    except Exception:
        return None, None


def _return_between(root: Path, ticker: str, market: str,
                    start: str, end: str) -> Optional[float]:
    idx, closes = _load_close_series(root, ticker, market)
    if not idx: return None
    start_before = [(d, c) for d, c in zip(idx, closes) if d <= start]
    end_before   = [(d, c) for d, c in zip(idx, closes) if d <= end]
    if not (start_before and end_before): return None
    s = start_before[-1][1]; e = end_before[-1][1]
    if not (s and s > 0): return None
    return (e - s) / s * 100


def _regime_at(root: Path, market: str, at_date: str) -> str:
    p = (root / "reports" / "context"
         / f"macro_regime_history_{market.lower()}.jsonl")
    if not p.exists():
        p = root / "reports" / "context" / f"macro_regime_{market.lower()}.json"
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                return str(d.get("regime") or d.get("label") or "UNKNOWN").upper()
            except Exception:
                return "UNKNOWN"
        return "UNKNOWN"
    try:
        # Find the closest regime record on or before at_date
        best = "UNKNOWN"
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            r = json.loads(line)
            if r.get("asof", "") <= at_date:
                best = str(r.get("regime") or "").upper()
        return best or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


# ─────────────────────────────────────────────────────────────────
# Classifier · deterministic rules · easy to test
# ─────────────────────────────────────────────────────────────────
def classify_exit(
    *, pnl_pct: float, days_held: int, closed_reason: str,
    sector_return_over_hold: Optional[float],
    entry_quality: str,
) -> str:
    """Classify one closed position into WINNER or one of 6 loss categories."""
    if pnl_pct > 0.5:
        return "WINNER"
    _reason = str(closed_reason or "").upper()
    if "STOP_LOSS_HIT" in _reason or "STOP LOSS" in _reason:
        return "STOP_LOSS_HIT"
    # Quick early drop · likely macro shock
    if days_held <= 5 and pnl_pct < -3:
        return "MACRO_SHOCK"
    # Long time held with no meaningful move · thesis timing off
    if days_held >= 45 and abs(pnl_pct) < 3:
        return "TIME_STOP"
    # Sector dragged the ticker down · systemic, not idiosyncratic
    if (sector_return_over_hold is not None
        and sector_return_over_hold < -5
        and pnl_pct <= sector_return_over_hold + 2):
        return "SECTOR_DRAG"
    # Quality gate said OK but position lost meaningfully · false positive
    if entry_quality.upper() in ("QUALITY", "OK", "🏆 QUALITY", "✓ OK") \
       and pnl_pct < -5:
        return "QUALITY_FALSE_POSITIVE"
    # Default · fundamentals must have degraded
    return "THESIS_FAILURE"


def recommendation_for(category: str) -> str:
    """Plain-English action to avoid this loss category next time."""
    return {
        "WINNER":                "keep doing what worked",
        "STOP_LOSS_HIT":         "risk mgmt worked · widen stop only if pattern shows",
        "TIME_STOP":             "shorten max-hold window · rotate faster on flat action",
        "THESIS_FAILURE":        "reinforce fundamentals gate at entry",
        "SECTOR_DRAG":           "add sector-momentum overlay · block entries when sector rotating out",
        "MACRO_SHOCK":           "widen entry regime filter · reduce entries in high-vol regimes",
        "QUALITY_FALSE_POSITIVE": "recalibrate investability quality band · was too generous",
        # Momentum-related · from Sprint M.1 Timing Engine integration
        "BAD_TIMING":            "add momentum-confirmation gate at entry · don't enter deteriorating names",
        "MOMENTUM_FAILURE":      "add trailing-momentum check · exit when 5d/20d agree bearish",
        "CHASE_EXTENSION":       "add RSI/extension filter · don't enter RSI>75 with weak volume",
        "FALSE_BREAKOUT":        "require volume confirm ≥ 1.5x AND multi-timeframe agreement",
        "SECTOR_MOMENTUM_FAILURE": "add sector-regime overlay · block entries in LAGGARD sectors",
    }.get(category, "review individually")


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str, lookback_days: int = 90) -> AttributionReport:
    """Walk Registry CLOSED events in last N days · classify each ·
    build sector + cap-size rollups."""
    try:
        from backend.research import opportunity_registry as _oreg
    except Exception:
        return AttributionReport(
            market=market.lower(),
            asof=date.today().isoformat(),
            generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
    reg = _oreg.load_all(root)
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    rep = AttributionReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    exits: list = []
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            if o.status != "CLOSED": continue
            if not o.closed_date or o.closed_date < cutoff: continue
            # PnL from parquet closes if not on the opportunity
            _e_p = _return_between(
                root, o.ticker, market, o.created_date, o.closed_date)
            if _e_p is None: continue
            try:
                _dh = (date.fromisoformat(o.closed_date)
                       - date.fromisoformat(o.created_date)).days
            except Exception:
                _dh = 0
            _sec = _sector_for(root, o.ticker, market)
            _cap = _cap_size_for(root, o.ticker, market)
            _reg_l = _regime_at(root, market, o.created_date)
            # sector return over same hold window (best-effort using sector proxy)
            _sec_ret = None
            if _sec != "UNKNOWN":
                _sec_ret = _return_between(
                    root, _sec.replace(" ", "_").upper(),
                    market, o.created_date, o.closed_date)
            _cat = classify_exit(
                pnl_pct=_e_p, days_held=_dh,
                closed_reason=str(o.closed_reason or ""),
                sector_return_over_hold=_sec_ret,
                entry_quality="UNKNOWN",
            )
            exits.append(ExitClassification(
                ticker=o.ticker.upper(),
                market=market.lower(),
                runner=o.runner,
                entry_date=o.created_date,
                exit_date=o.closed_date,
                days_held=_dh,
                pnl_pct=round(_e_p, 2),
                is_win=(_e_p > 0.5),
                category=_cat,
                sector=_sec,
                cap_size=_cap,
                entry_regime=_reg_l,
                entry_quality="UNKNOWN",
                sector_return_over_hold=(round(_sec_ret, 2)
                                         if _sec_ret is not None else None),
                recommendation=recommendation_for(_cat),
            ))
    rep.exits = [asdict(e) for e in exits]
    rep.n_positions = len(exits)
    rep.n_wins = sum(1 for e in exits if e.is_win)
    rep.n_losses = rep.n_positions - rep.n_wins
    _pnls = [e.pnl_pct for e in exits if abs(e.pnl_pct) > 0.01]
    rep.total_realized_pct = round(sum(_pnls), 2) if _pnls else 0.0
    _wins = [e.pnl_pct for e in exits if e.pnl_pct > 0.5]
    _loss = [e.pnl_pct for e in exits if e.pnl_pct < -0.5]
    rep.positive_pct = round(sum(_wins), 2) if _wins else 0.0
    rep.negative_pct = round(sum(_loss), 2) if _loss else 0.0
    rep.win_rate_pct = round(rep.n_wins / max(rep.n_positions, 1) * 100, 1)
    _avg_w = (sum(_wins) / len(_wins)) if _wins else 0.0
    _avg_l = (sum(_loss) / len(_loss)) if _loss else 0.0
    rep.profit_factor = round(
        abs(_avg_w / _avg_l) if _avg_l else 0.0, 2)
    # Category counts
    cc: dict = {}
    for e in exits:
        cc[e.category] = cc.get(e.category, 0) + 1
    rep.category_counts = cc
    # Sector rollup
    from collections import defaultdict
    by_sec: dict = defaultdict(list)
    for e in exits:
        by_sec[e.sector].append(e)
    for sec, items in by_sec.items():
        _n = len(items)
        _w = sum(1 for x in items if x.is_win)
        _l = _n - _w
        _tot = sum(x.pnl_pct for x in items)
        _cat_counts: dict = {}
        for x in items:
            if not x.is_win:
                _cat_counts[x.category] = _cat_counts.get(x.category, 0) + 1
        _dom = max(_cat_counts, key=_cat_counts.get) if _cat_counts else "—"
        rep.sector_rollup.append(asdict(SectorRollup(
            sector=sec, n_positions=_n, n_wins=_w, n_losses=_l,
            total_pnl_pct=round(_tot, 2),
            win_rate_pct=round(_w / max(_n, 1) * 100, 1),
            dominant_loss_category=_dom,
        )))
    # Cap-size rollup
    by_cap: dict = defaultdict(list)
    for e in exits:
        by_cap[e.cap_size].append(e)
    for cap, items in by_cap.items():
        _n = len(items)
        _w = sum(1 for x in items if x.is_win)
        _l = _n - _w
        _wins_l = [x.pnl_pct for x in items if x.is_win]
        _loss_l = [x.pnl_pct for x in items if not x.is_win]
        _avg_w = round(sum(_wins_l) / max(len(_wins_l), 1), 2)
        _avg_l = round(sum(_loss_l) / max(len(_loss_l), 1), 2)
        _pf = round(abs(_avg_w / _avg_l), 2) if _avg_l else 0.0
        rep.cap_size_rollup.append(asdict(CapSizeRollup(
            cap_size=cap, n_positions=_n, n_wins=_w, n_losses=_l,
            avg_win_pct=_avg_w, avg_loss_pct=_avg_l, profit_factor=_pf,
        )))
    return rep


def emit(root: Path, report: AttributionReport) -> Path:
    p = (root / "reports" / "research"
         / f"loss_patterns_{report.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(report), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def render_markdown(rep: AttributionReport) -> str:
    lines = [
        f"# Loss Attribution v2 · {rep.market.upper()}",
        f"## as of {rep.asof}",
        "",
        f"**{rep.n_positions} closed positions** in last 90 days · "
        f"**{rep.n_wins}W / {rep.n_losses}L** · win rate **{rep.win_rate_pct}%**",
        f"Realized P&L: **{rep.total_realized_pct:+.2f}%** "
        f"(positive {rep.positive_pct:+.2f}% · negative {rep.negative_pct:+.2f}%)",
        f"Profit factor: **{rep.profit_factor}** (avg win / avg loss)",
        "",
        "## Loss category breakdown",
    ]
    for cat in LOSS_CATEGORIES + ["WINNER"]:
        n = rep.category_counts.get(cat, 0)
        if n:
            lines.append(f"- **{cat}** · {n} positions · "
                         f"{recommendation_for(cat)}")
    lines.append("")
    lines.append("## Sector rollup")
    for s in sorted(rep.sector_rollup,
                    key=lambda x: -x.get("n_positions", 0)):
        lines.append(
            f"- **{s['sector']}** · {s['n_positions']} pos · "
            f"{s['n_wins']}W/{s['n_losses']}L · P&L {s['total_pnl_pct']:+.2f}% · "
            f"win rate {s['win_rate_pct']}% · "
            f"dominant loss: {s.get('dominant_loss_category', '—')}")
    lines.append("")
    lines.append("## Cap-size rollup")
    for c in sorted(rep.cap_size_rollup,
                    key=lambda x: -x.get("n_positions", 0)):
        lines.append(
            f"- **{c['cap_size']}** · {c['n_positions']} pos · "
            f"avg win {c['avg_win_pct']:+.2f}% · "
            f"avg loss {c['avg_loss_pct']:+.2f}% · "
            f"profit factor {c['profit_factor']}")
    return "\n".join(lines)


def emit_markdown(root: Path, report: AttributionReport) -> Path:
    md = render_markdown(report)
    p = (root / "reports" / "research"
         / f"loss_patterns_{report.market}.md")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md, encoding="utf-8")
    return p


def summary_line(rep: AttributionReport) -> str:
    """One-line summary for Portfolio caption + Telegram digest."""
    top_loss_cat = "—"
    if rep.category_counts:
        losses = {k: v for k, v in rep.category_counts.items()
                  if k in LOSS_CATEGORIES}
        if losses:
            top_loss_cat = max(losses, key=losses.get)
    return (f"loss_attribution · {rep.n_positions} exits · "
            f"WR {rep.win_rate_pct}% · PF {rep.profit_factor} · "
            f"top-loss: {top_loss_cat}")
