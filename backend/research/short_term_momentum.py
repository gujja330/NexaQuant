# backend/research/short_term_momentum.py
"""AEGIS · Sprint M · Short-Term Momentum Analysis (quick rise + quick fall).

CEO directive 2026-08-25: "quick rise, quick fall analysis · so that
quick rise in short term can allow us to gain profits".

Scans the universe for tickers showing:

  QUICK RISE       · big up-move in short window · potential momentum play
  QUICK FALL       · big down-move in short window · potential rebound play
  SUSTAINED_UP     · consistent up-trend across multiple windows
  SUSTAINED_DOWN   · consistent down-trend
  REVERSAL_UP      · was down, now bouncing
  REVERSAL_DOWN    · was up, now dropping
  IGNORE           · nothing interesting

Thresholds (configurable):
  1D rise > +4%    · unusual daily move
  3D rise > +8%
  5D rise > +12%
  1D fall < -4%
  3D fall < -8%
  5D fall < -12%

Each candidate gets a quality overlay from investability:
  QUICK_RISE + QUALITY high → surface as potential entry
  QUICK_RISE + QUALITY low  → pump-and-dump risk · flag but don't recommend
  QUICK_FALL + QUALITY high → potential rebound (quality on sale)
  QUICK_FALL + QUALITY low  → structural failure · avoid

Emits reports/research/short_term_momentum_{market}.json ·
Constitutional invariant · READ-ONLY · never feeds R1/R2 automatically.
"""
from __future__ import annotations

import glob
import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.short_term_momentum.v1.20260825"

# Configurable thresholds (deterministic · easy to test)
# 2026-08-25 v2 · thresholds are baseline · adjusted per-ticker by
# realized volatility (high-vol stocks need larger moves to qualify).
THRESHOLDS = {
    "1d_rise_pct":  4.0,
    "3d_rise_pct":  8.0,
    "5d_rise_pct": 12.0,
    "1d_fall_pct": -4.0,
    "3d_fall_pct": -8.0,
    "5d_fall_pct": -12.0,
    "volume_confirm_multiplier": 1.5,  # volume must be ≥ 1.5x 20d avg
    "rsi_overbought":   70,
    "rsi_oversold":     30,
    "vol_adjust_cap":   2.0,   # cap threshold multiplier at 2x
}


@dataclass
class MomentumCandidate:
    ticker: str
    market: str
    category: str          # QUICK_RISE / QUICK_FALL / SUSTAINED_UP / etc.
    sector: str
    quality_band: str
    return_1d_pct: Optional[float]
    return_3d_pct: Optional[float]
    return_5d_pct: Optional[float]
    return_20d_pct: Optional[float]
    close: float
    # Advanced signals
    volume_ratio: Optional[float] = None       # today's / 20d avg
    volume_confirmed: bool = False
    annualized_vol_pct: Optional[float] = None
    vol_adjusted_thresh_mult: float = 1.0
    rsi_14: Optional[float] = None
    rsi_state: str = ""       # OVERBOUGHT / OVERSOLD / NEUTRAL
    sector_status: str = ""   # LEADER / LAGGARD / NEUTRAL
    multi_tf_confirmed: bool = False
    verdict: str = ""         # POTENTIAL_ENTRY / REBOUND_WATCH / PUMP_RISK / AVOID / IGNORE
    reason: str = ""
    signals_fired: list = field(default_factory=list)


@dataclass
class MomentumReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    n_universe: int = 0
    # CEO 2026-09-07 · TRUTHFUL FUNNEL COUNTERS.
    # `n_universe` is the DECLARED universe · it was previously the only
    # number published, and downstream rendered it as "scanned", implying
    # every ticker had been evaluated. Tickers with an unreadable parquet or
    # <22 bars were skipped SILENTLY. During the 11-day producer outage that
    # made a total data failure indistinguishable from a quiet market.
    # These four counters make the drop-off explicit and must reconcile:
    #     n_universe == n_unreadable + n_insufficient_history + n_evaluated
    #     n_evaluated == n_ignored_no_momentum + len(candidates)
    n_evaluated: int = 0
    n_unreadable: int = 0
    n_insufficient_history: int = 0
    n_ignored_no_momentum: int = 0
    n_quick_rise: int = 0
    n_quick_fall: int = 0
    n_sustained_up: int = 0
    n_sustained_down: int = 0
    n_potential_entry: int = 0
    n_rebound_watch: int = 0
    n_pump_risk: int = 0
    n_avoid: int = 0
    candidates: list = field(default_factory=list)
    thresholds: dict = field(default_factory=dict)


_DATAFRAME_LOAD_ERROR_REPORTED = False


def _dataframe(root: Path, ticker: str, market: str):
    """Full parquet DataFrame (close + tick_volume)."""
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
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        return df
    except Exception as e:
        # CEO 2026-09-07 · this bare-except previously returned None silently.
        # When every load failed the scan emitted 0 candidates and downstream
        # rendered it as "a quiet market" · hiding an 11-day outage. Surface the
        # first failure per process so the cause is visible, then stay quiet.
        global _DATAFRAME_LOAD_ERROR_REPORTED
        if not _DATAFRAME_LOAD_ERROR_REPORTED:
            _DATAFRAME_LOAD_ERROR_REPORTED = True
            import sys as _s
            print(f"[short-term-momentum] _dataframe FAILED for {p} · "
                  f"{type(e).__name__}: {e}", file=_s.stderr)
        return None


def _series(root: Path, ticker: str, market: str):
    """Close series only."""
    df = _dataframe(root, ticker, market)
    if df is None: return None
    col = "close" if "close" in df.columns else "Close"
    return df[col].astype(float)


def _rsi14(series) -> Optional[float]:
    """Standard 14-period RSI."""
    if series is None or len(series) < 15: return None
    try:
        deltas = series.diff()[1:]
        gains  = deltas.where(deltas > 0, 0).tail(14)
        losses = -deltas.where(deltas < 0, 0).tail(14)
        avg_gain = float(gains.mean())
        avg_loss = float(losses.mean())
        if avg_loss <= 0: return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 1)
    except Exception:
        return None


def _annualized_vol(series) -> Optional[float]:
    if series is None or len(series) < 30: return None
    try:
        rets = series.pct_change().tail(30)
        return round(float(rets.std()) * (252 ** 0.5) * 100, 2)
    except Exception:
        return None


def _volume_ratio(df) -> Optional[float]:
    """Today's volume / 20-day average · confirmation signal."""
    if df is None or len(df) < 21: return None
    col = "tick_volume" if "tick_volume" in df.columns else \
          ("volume" if "volume" in df.columns else None)
    if col is None: return None
    try:
        today = float(df[col].iloc[-1])
        avg20 = float(df[col].tail(20).mean())
        if avg20 <= 0: return None
        return round(today / avg20, 2)
    except Exception:
        return None


def _sector_status(root: Path, ticker: str, market: str) -> str:
    """LEADER / LAGGARD / NEUTRAL from sector_context."""
    p = root / "reports" / "context" / f"sector_context_{market.lower()}.json"
    if not p.exists(): return "UNKNOWN"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        sec = _sector_for(root, ticker, market)
        secs = d.get("sectors") or d.get("data") or {}
        if isinstance(secs, dict):
            entry = secs.get(sec) or {}
            if entry.get("is_leader"):  return "LEADER"
            if entry.get("is_laggard"): return "LAGGARD"
            return "NEUTRAL"
    except Exception:
        pass
    return "UNKNOWN"


def _return_over_last(series, days: int):
    if series is None or len(series) < days + 1: return None
    end_p = float(series.iloc[-1])
    start_p = float(series.iloc[-(days + 1)])
    if start_p <= 0: return None
    return round((end_p - start_p) / start_p * 100, 2)


def _sector_for(root: Path, ticker: str, market: str) -> str:
    p = root / "reports" / "sector_cache.json"
    if not p.exists(): return "UNKNOWN"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get(market.lower(), {}).get(ticker.upper()) or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _quality_band(root: Path, ticker: str, market: str) -> str:
    """Quality-band lookup for momentum candidates.

    Momentum runs across the FULL parquet universe (India ~230 · USA ~900)
    but plain `investability_{market}.json` only scores the narrow R1/R2
    universe (~42 India · ~30 USA). Prefer `investability_shadow_{market}.json`
    (full-universe scoring) with fallback to the narrow file. Prevents
    100%-UNKNOWN misclassification that pushes every momentum candidate
    to CHASE_RISK/NO_ACTION in the timing engine.
    """
    tk = ticker.upper()
    for fname in (f"investability_shadow_{market.lower()}.json",
                  f"investability_{market.lower()}.json"):
        p = root / "reports" / fname
        if not p.exists(): continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            for r in (d.get("results") or []):
                if str(r.get("ticker","")).upper() == tk:
                    _v = str(r.get("verdict","")).upper()
                    if "QUALITY" in _v: return "QUALITY"
                    if "OK" in _v:      return "OK"
                    if "MARGINAL" in _v: return "MARGINAL"
                    if "AVOID" in _v:   return "AVOID"
                    return _v or "UNKNOWN"
        except Exception:
            continue
    return "UNKNOWN"


def _universe(root: Path, market: str) -> list:
    if market.lower() == "usa":
        pat = str(root / "usa" / "data" / "raw" / "us" / "*_D1.parquet")
    else:
        pat = str(root / "data" / "raw" / "india" / "*_D1.parquet")
    return sorted(Path(f).stem.replace("_D1","") for f in glob.glob(pat))


# ─────────────────────────────────────────────────────────────────
# Categorizer · deterministic ladder · VOLATILITY-ADJUSTED
# ─────────────────────────────────────────────────────────────────
def _vol_adjustment(ann_vol_pct: Optional[float]) -> float:
    """High-vol stocks need bigger moves to qualify · adjust threshold."""
    if ann_vol_pct is None: return 1.0
    # Baseline vol ~25% annualized · 1x threshold
    # 50% vol → 2x threshold (capped)
    mult = max(1.0, min(THRESHOLDS["vol_adjust_cap"], ann_vol_pct / 25.0))
    return round(mult, 2)


def categorize(r1: Optional[float], r3: Optional[float],
               r5: Optional[float], r20: Optional[float],
               vol_adjust: float = 1.0) -> str:
    t = THRESHOLDS
    quick_rise = ((r1 is not None and r1 > t["1d_rise_pct"] * vol_adjust) or
                  (r3 is not None and r3 > t["3d_rise_pct"] * vol_adjust) or
                  (r5 is not None and r5 > t["5d_rise_pct"] * vol_adjust))
    quick_fall = ((r1 is not None and r1 < t["1d_fall_pct"] * vol_adjust) or
                  (r3 is not None and r3 < t["3d_fall_pct"] * vol_adjust) or
                  (r5 is not None and r5 < t["5d_fall_pct"] * vol_adjust))
    if r20 is not None and r5 is not None:
        if r5 > 5 and r20 > 15:  return "SUSTAINED_UP"
        if r5 < -5 and r20 < -15: return "SUSTAINED_DOWN"
        if r20 < -10 and r5 > 5:  return "REVERSAL_UP"
        if r20 > 10 and r5 < -5:  return "REVERSAL_DOWN"
    if quick_rise: return "QUICK_RISE"
    if quick_fall: return "QUICK_FALL"
    return "IGNORE"


def verdict_for(category: str, quality: str) -> tuple:
    """Return (verdict, reason)."""
    q_high = quality in ("QUALITY", "OK")
    q_low  = quality in ("MARGINAL", "AVOID")
    if category == "IGNORE":
        return ("IGNORE", "no notable move")
    if category in ("QUICK_RISE", "SUSTAINED_UP"):
        if q_high:
            return ("POTENTIAL_ENTRY",
                    "quality-confirmed momentum · consider entry with tight stop")
        if q_low:
            return ("PUMP_RISK",
                    "big move on low-quality name · pump-and-dump risk · avoid")
        return ("MOMENTUM_WATCH",
                "unknown quality · watch but don't act blind")
    if category in ("QUICK_FALL", "SUSTAINED_DOWN"):
        if q_high:
            return ("REBOUND_WATCH",
                    "quality on sale · watch for reversal signal")
        if q_low:
            return ("AVOID",
                    "low quality + falling · structural failure · stay away")
        return ("AVOID",
                "unknown quality + falling · not a value play")
    if category == "REVERSAL_UP":
        if q_high:
            return ("POTENTIAL_ENTRY",
                    "quality reversal · early trend change · scale in cautiously")
        return ("MOMENTUM_WATCH", "reversal signal · unknown quality")
    if category == "REVERSAL_DOWN":
        return ("AVOID", "reversal down · momentum breaking")
    return ("IGNORE", "")


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str) -> MomentumReport:
    universe = _universe(root, market)
    rep = MomentumReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        thresholds=dict(THRESHOLDS),
    )
    rep.n_universe = len(universe)
    candidates: list = []
    for tk in universe:
        df = _dataframe(root, tk, market)
        if df is None:
            rep.n_unreadable += 1
            continue
        if len(df) < 22:
            rep.n_insufficient_history += 1
            continue
        rep.n_evaluated += 1
        col = "close" if "close" in df.columns else "Close"
        s = df[col].astype(float)
        r1  = _return_over_last(s, 1)
        r3  = _return_over_last(s, 3)
        r5  = _return_over_last(s, 5)
        r20 = _return_over_last(s, 20)
        # Volatility adjustment
        ann_vol = _annualized_vol(s)
        vol_adj = _vol_adjustment(ann_vol)
        cat = categorize(r1, r3, r5, r20, vol_adjust=vol_adj)
        if cat == "IGNORE":
            rep.n_ignored_no_momentum += 1
            continue
        # Advanced signals
        vol_ratio = _volume_ratio(df)
        vol_conf = (vol_ratio is not None
                    and vol_ratio >= THRESHOLDS["volume_confirm_multiplier"])
        rsi = _rsi14(s)
        rsi_state = "NEUTRAL"
        if rsi is not None:
            if rsi >= THRESHOLDS["rsi_overbought"]: rsi_state = "OVERBOUGHT"
            elif rsi <= THRESHOLDS["rsi_oversold"]:  rsi_state = "OVERSOLD"
        ss = _sector_status(root, tk, market)
        # Multi-timeframe · 5d + 20d agree in direction
        mtf = False
        if r5 is not None and r20 is not None:
            mtf = ((cat in ("QUICK_RISE","SUSTAINED_UP") and r20 > 0)
                   or (cat in ("QUICK_FALL","SUSTAINED_DOWN") and r20 < 0))
        q = _quality_band(root, tk, market)
        sec = _sector_for(root, tk, market)
        # Upgraded verdict considering advanced signals
        v, why = verdict_for(cat, q)
        signals = []
        # Boost/downgrade based on confirming signals
        if v == "POTENTIAL_ENTRY":
            if not vol_conf and vol_ratio is not None:
                v = "MOMENTUM_WATCH"
                signals.append(f"volume {vol_ratio}x avg · below {THRESHOLDS['volume_confirm_multiplier']}x confirm")
                why = "quality-confirmed momentum · BUT weak volume · watch not enter"
            elif rsi_state == "OVERBOUGHT":
                v = "MOMENTUM_WATCH"
                signals.append(f"RSI {rsi} · overbought")
                why = "quality + momentum · BUT overbought · wait for pullback"
            elif ss == "LAGGARD":
                signals.append(f"{sec} sector LAGGARD")
                why = "quality entry but in weak sector · smaller size"
            else:
                if vol_conf: signals.append(f"volume {vol_ratio}x avg · confirmed")
                if mtf: signals.append("multi-timeframe agree")
                if ss == "LEADER": signals.append(f"{sec} sector LEADER")
        if v == "REBOUND_WATCH":
            if rsi_state == "OVERSOLD":
                signals.append(f"RSI {rsi} · oversold · bounce setup")
                why = "quality + oversold · strong rebound candidate"
        if v == "PUMP_RISK":
            if vol_ratio and vol_ratio > 3:
                signals.append(f"volume {vol_ratio}x avg · classic pump signature")
        candidates.append(MomentumCandidate(
            ticker=tk.upper(), market=market.lower(),
            category=cat, sector=sec, quality_band=q,
            return_1d_pct=r1, return_3d_pct=r3,
            return_5d_pct=r5, return_20d_pct=r20,
            close=round(float(s.iloc[-1]), 2),
            volume_ratio=vol_ratio, volume_confirmed=vol_conf,
            annualized_vol_pct=ann_vol,
            vol_adjusted_thresh_mult=vol_adj,
            rsi_14=rsi, rsi_state=rsi_state,
            sector_status=ss, multi_tf_confirmed=mtf,
            verdict=v, reason=why, signals_fired=signals,
        ))
    # Sort candidates · POTENTIAL_ENTRY first · then REBOUND_WATCH · then others
    _priority = {"POTENTIAL_ENTRY": 0, "REBOUND_WATCH": 1,
                 "MOMENTUM_WATCH": 2, "PUMP_RISK": 3, "AVOID": 4, "IGNORE": 5}
    candidates.sort(key=lambda c: (_priority.get(c.verdict, 9),
                                    -(c.return_5d_pct or 0)))
    rep.candidates = [asdict(c) for c in candidates]
    # Counts
    for c in candidates:
        if c.category == "QUICK_RISE":     rep.n_quick_rise += 1
        elif c.category == "QUICK_FALL":   rep.n_quick_fall += 1
        elif c.category == "SUSTAINED_UP": rep.n_sustained_up += 1
        elif c.category == "SUSTAINED_DOWN": rep.n_sustained_down += 1
        if c.verdict == "POTENTIAL_ENTRY": rep.n_potential_entry += 1
        elif c.verdict == "REBOUND_WATCH": rep.n_rebound_watch += 1
        elif c.verdict == "PUMP_RISK":     rep.n_pump_risk += 1
        elif c.verdict == "AVOID":         rep.n_avoid += 1
    return rep


def emit(root: Path, rep: MomentumReport) -> Path:
    p = (root / "reports" / "research"
         / f"short_term_momentum_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: MomentumReport) -> str:
    return (f"short_term_momentum · {rep.n_universe} universe · "
            f"RISE {rep.n_quick_rise} · FALL {rep.n_quick_fall} · "
            f"ENTRY {rep.n_potential_entry} · REBOUND {rep.n_rebound_watch} · "
            f"PUMP-RISK {rep.n_pump_risk} · AVOID {rep.n_avoid}")


# ── CLI entry · CEO 2026-09-07 · P0 orphaned-producer fix ────────────────
# This module previously had NO __main__ block, so it could not be invoked
# as a pipeline step. `momentum_ledger.py` CONSUMES its output daily but
# nothing PRODUCED it · leaving short_term_momentum_{market}.json frozen at
# asof=2026-08-27 (India) / 2026-08-26 (USA) while the ledger faithfully
# re-derived the same stale answer every day.
#
# Governance preserved · thresholds unchanged · classification logic
# unchanged · still READ-ONLY · still never feeds R1/R2 automatically.
def main() -> int:
    import argparse
    import sys as _sys

    ap = argparse.ArgumentParser(
        description="Produce short_term_momentum_{market}.json for the current as-of date")
    ap.add_argument("--market", choices=("india", "usa", "both"), default="both")
    ap.add_argument("--root", default=None, help="repo root (default: auto-detect)")
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parents[2]
    markets = ["india", "usa"] if args.market == "both" else [args.market]

    rc = 0
    for m in markets:
        try:
            rep = compute(root, m)

            # CEO 2026-09-07 · SILENT-ZERO GUARD.
            # A 0-candidate emit on a non-empty universe is indistinguishable
            # downstream from "a genuinely quiet market". momentum_ledger.py
            # consumes this file and renders it as "Today's scan" either way.
            # Refuse to emit silently · self-diagnose and fail loudly instead.
            if rep.n_universe > 0 and not rep.candidates:
                probe = _zero_candidate_probe(root, m)
                print(f"[short-term-momentum] {m}: SILENT-ZERO GUARD TRIPPED · "
                      f"universe={rep.n_universe} candidates=0", file=_sys.stderr)
                for line in probe:
                    print(f"[short-term-momentum] {m}:   {line}", file=_sys.stderr)
                if probe and probe[0].startswith("DATA_UNREADABLE"):
                    print(f"[short-term-momentum] {m}: REFUSING TO EMIT · "
                          f"would overwrite good data with an artifact of a "
                          f"data-access failure", file=_sys.stderr)
                    rc = 1
                    continue

            out = emit(root, rep)
            print(f"[short-term-momentum] {m}: {summary_line(rep)}")
            print(f"[short-term-momentum] {m}: asof={rep.asof} -> {out}")
        except Exception as e:
            print(f"[short-term-momentum] {m}: ERROR {type(e).__name__}: {e}",
                  file=_sys.stderr)
            rc = 1
    return rc


def _zero_candidate_probe(root: Path, market: str) -> list:
    """Diagnose WHY a scan produced zero candidates · data problem vs quiet market.

    Returns human-readable diagnosis lines. Distinguishes:
      DATA_UNREADABLE · price frames not loading (real failure)
      QUIET_MARKET    · frames load, no ticker crossed thresholds (legitimate)
    """
    uni = _universe(root, market)
    if not uni:
        return ["UNIVERSE_EMPTY · no *_D1.parquet found under the market data root"]
    sample = uni[:25]
    n_none = n_short = n_ok = 0
    best_r1 = best_r5 = None
    for tk in sample:
        df = _dataframe(root, tk, market)
        if df is None:
            n_none += 1
            continue
        if len(df) < 22:
            n_short += 1
            continue
        n_ok += 1
        col = "close" if "close" in df.columns else "Close"
        s = df[col].astype(float)
        r1 = _return_over_last(s, 1)
        r5 = _return_over_last(s, 5)
        if r1 is not None: best_r1 = r1 if best_r1 is None else max(best_r1, r1)
        if r5 is not None: best_r5 = r5 if best_r5 is None else max(best_r5, r5)

    lines = [f"probe sample={len(sample)} readable={n_ok} unreadable={n_none} "
             f"too_few_bars={n_short}"]
    if n_ok == 0:
        lines.insert(0, "DATA_UNREADABLE · every sampled ticker failed to load a "
                        "usable price frame")
    else:
        lines.insert(0, "QUIET_MARKET · price frames load fine")
        lines.append(f"best 1d move in sample={best_r1}% (rise threshold "
                     f"{THRESHOLDS['1d_rise_pct']}% before vol-adjust)")
        lines.append(f"best 5d move in sample={best_r5}% (rise threshold "
                     f"{THRESHOLDS['5d_rise_pct']}% before vol-adjust)")
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
