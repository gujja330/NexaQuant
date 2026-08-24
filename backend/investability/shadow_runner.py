"""Part 26 · Institutional Investability Engine · SHADOW TRACK.

Runs PARALLEL to the live recommender · never touches its output. Every
trading day scores EVERY ticker in the universe against all 11 sub-
engines, then compares what the recommender emitted vs what
investability would filter. Two outputs:

  reports/investability_shadow_{market}.json
    Full 11-sub-engine score for every ticker in the universe.

  reports/context/investability_shadow_diagnostic_{market}.json
    Per-day comparison + gate simulation:
      · N tickers in universe
      · N would pass gate (score >= threshold)
      · N would fail gate (REJECT)
      · Of recommender's picks: N pass + N fail (would-be rejected)
      · Top 5 discoveries · high-scoring tickers NOT in recommender set
      · Top 5 questionable · low-scoring tickers currently held

Enforcement is OFF by default. `enforce_gate: false` in
configs/investability.yaml means the shadow output is INFORMATIONAL ·
recommender continues emitting what it always emitted. Flip to true
after operator reviews shadow output for a few weeks and confirms.

Compute · uses parallel_map (Part 29 Lever B) for yfinance calls · a
229-ticker India universe scores in ~2 minutes vs ~15 min serial.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

from backend.investability import scorer as _inv
from backend.ingest.pipeline_helpers import parallel_map


@dataclass
class ShadowDiagnostic:
    engine:            str = "aegis.investability.shadow.v1"
    generated_utc:     str = ""
    market:            str = ""
    asof:              str = ""
    n_universe:        int = 0
    n_scored:          int = 0
    n_would_pass:      int = 0
    n_would_fail:      int = 0
    threshold:         float = 60.0
    enforce_gate:      bool = False
    verdict_counts:    dict = field(default_factory=dict)
    # Recommender comparison
    n_recs_today:      int = 0
    n_recs_pass_gate:  int = 0
    n_recs_fail_gate:  int = 0
    would_reject_from_recs: list = field(default_factory=list)
    # Discovery
    top_discoveries:   list = field(default_factory=list)
    # Warnings
    warnings:          list = field(default_factory=list)


def _universe(root: Path, market: str) -> list:
    """List of bare tickers in the market's universe (from parquet cache)."""
    d = ((root / "usa" / "data" / "raw" / "us") if market.lower() == "usa"
             else (root / "data" / "raw" / "india"))
    if not d.exists(): return []
    tks = []
    for p in d.glob("*_D1.parquet"):
        tks.append(p.stem.replace("_D1", "").upper())
    return sorted(tks)


def _load_config(root: Path) -> dict:
    p = root / "configs" / "investability.yaml"
    if not p.exists(): return {}
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cfg.get("shadow", {}) or {}
    except Exception:
        return {}


def _load_recs(root: Path, market: str) -> list:
    p = ((root / "usa" / "reports" / "recommendations.json")
             if market == "usa" else (root / "reports" / "recommendations.json"))
    if not p.exists(): return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return [str(r.get("ticker","")).upper().replace(".NS","").replace(".BO","")
                     for r in d.get("recommendations", [])]
    except Exception:
        return []


def score_all(root: Path, market: str) -> list:
    """Score every ticker in the universe. Returns list of Investability dataclass dicts."""
    tickers = _universe(root, market)
    if not tickers: return []
    def _worker(tk):
        try:
            return asdict(_inv.score_ticker(tk, market, root))
        except Exception:
            return None
    # Parallel · 6 workers · 8/s rate limit for yfinance
    results = parallel_map(_worker, tickers, max_workers=6,
                                       rate_per_sec=8.0, max_retries=2, progress_every=25)
    return [r for r in results if r is not None]


def emit_scores(root: Path, market: str, scored: list) -> Path:
    """Write reports/investability_shadow_{market}.json."""
    market = market.lower()
    p = root / "reports" / f"investability_shadow_{market}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "engine":       "aegis.investability.shadow.v1",
        "market":       market,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_scored":     len(scored),
        "results":      scored,
    }
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def compute_diagnostic(root: Path, market: str, asof: str,
                                    scored: list) -> ShadowDiagnostic:
    market = market.lower(); asof = asof[:10]
    cfg = _load_config(root)
    threshold = float(cfg.get("gate_threshold", 60.0))
    enforce = bool(cfg.get("enforce_gate", False))
    d = ShadowDiagnostic(
        market=market, asof=asof, threshold=threshold, enforce_gate=enforce,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    d.n_universe = len(scored)   # approximation · scored subset of universe
    d.n_scored = len(scored)
    if not scored: return d

    by_ticker = {r["ticker"].upper(): r for r in scored if r.get("ticker")}
    counts: dict = {}
    for r in scored:
        v = r.get("verdict", "?")
        counts[v] = counts.get(v, 0) + 1
        if (r.get("score") or 0) >= threshold:
            d.n_would_pass += 1
        else:
            d.n_would_fail += 1
    d.verdict_counts = counts

    # Recommender comparison
    rec_tickers = _load_recs(root, market)
    d.n_recs_today = len(rec_tickers)
    for tk in rec_tickers:
        r = by_ticker.get(tk)
        if r is None: continue
        if (r.get("score") or 0) >= threshold:
            d.n_recs_pass_gate += 1
        else:
            d.n_recs_fail_gate += 1
            d.would_reject_from_recs.append({
                "ticker": tk, "score": r.get("score"),
                "verdict": r.get("verdict"),
                "bottom_engines": sorted(
                    (r.get("sub_scores") or {}).items(), key=lambda kv: kv[1])[:3],
            })

    # Top discoveries · high-score tickers NOT in recommender set
    rec_set = set(rec_tickers)
    hi_scored = sorted(
        [r for r in scored if r["ticker"].upper() not in rec_set
             and (r.get("score") or 0) >= threshold + 10],
        key=lambda r: -(r.get("score") or 0),
    )
    d.top_discoveries = [
        {"ticker": r["ticker"], "score": r.get("score"),
         "verdict": r.get("verdict"),
         "top_engines": sorted(
             (r.get("sub_scores") or {}).items(), key=lambda kv: -kv[1])[:3]}
        for r in hi_scored[:5]
    ]

    # Warnings
    if d.n_recs_fail_gate > 0:
        d.warnings.append(
            f"{d.n_recs_fail_gate}/{d.n_recs_today} recommender picks would fail "
            f"investability gate at threshold {threshold}")
    if d.n_would_pass < d.n_recs_today:
        d.warnings.append(
            f"only {d.n_would_pass} of {d.n_universe} universe tickers pass gate · "
            f"expanding universe (Nifty 200 → 500) may unlock more discoveries")
    if enforce:
        d.warnings.append(
            "ENFORCE MODE ACTIVE · investability shadow is now GATING the recommender · "
            "monitor NEW opportunity flow closely")

    return d


def emit_diagnostic(root: Path, d: ShadowDiagnostic) -> Path:
    p = (root / "reports" / "context"
             / f"investability_shadow_diagnostic_{d.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(d), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def summary_line(d: ShadowDiagnostic) -> str:
    mode = "ENFORCE" if d.enforce_gate else "SHADOW"
    return (f"invest [{mode}] · scored={d.n_scored} · pass={d.n_would_pass} · "
                f"fail={d.n_would_fail} · recs_fail={d.n_recs_fail_gate}/{d.n_recs_today} · "
                f"discoveries={len(d.top_discoveries)}")


def run(root: Path, market: str, asof: str) -> tuple:
    """One-shot · score all + write both files + return (scored, diagnostic)."""
    scored = score_all(root, market)
    emit_scores(root, market, scored)
    diag = compute_diagnostic(root, market, asof, scored)
    emit_diagnostic(root, diag)
    return (scored, diag)
