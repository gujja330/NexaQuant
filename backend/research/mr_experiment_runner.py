"""AEGIS · Sprint M-R · Shadow Experiment Runner.

CEO handover 2026-08-27:
> "Next development task should be to activate the experiment runner /
>  capture — NOT modify the R1/R2 decision logic itself."

For each registered experiment in reports/research/experiments/, reads
today's walk-forward snapshot (production R1/R2 output frozen at capture
time) and applies the experiment's proposed rule as a PARALLEL SHADOW
computation. Emits shadow decisions to:

    reports/research/experiments/{experiment_id}/{date}/shadow.jsonl

Never touches:
    - Production R1 or R2 canonical output
    - Registry position lifecycle
    - XLSX contract or validator
    - Telegram sender
    - Canonical INVESTMENT_ACTIVE JSON emit

Ticker-level shadow output includes original decision + shadow decision +
which rule fired + reason string. Score is deferred to the walk-forward
scorer once forward days accumulate.

Experiments run:
    E1  india_confidence_anti_signal   · confidence 70-85 = WARN
    E2  india_top3_rank_inversion      · MA20-dist filter on top-3
    E3  india_negative_alpha           · compound E1+E2+E4+E5
    E4  india_band_boundary            · OK band re-classification test
    E5  india_stop_policy              · 5-day time-exit advisory

Under M-R sandbox rules. Zero production side effects.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_experiment_runner.v0.1"


def _load(root: Path, name: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _load_jsonl(root: Path, name: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _load_enriched_lookup(root: Path, market: str) -> dict:
    """Build ticker -> latest enriched features lookup from the frozen
    autopsy dataset. This is the feature source for shadow rule evaluation
    when today's snapshot doesn't already carry them."""
    rows = _load_jsonl(root, f"mr_prediction_autopsy_{market.lower()}_enriched.jsonl")
    latest: dict = {}
    for r in rows:
        tk = str(r.get("ticker","")).upper()
        dt = str(r.get("prediction_date",""))
        if not tk: continue
        prev = latest.get(tk)
        if not prev or dt > prev.get("prediction_date",""):
            latest[tk] = r
    return latest


def _snap_today(root: Path, market: str) -> list:
    iso = date.today().isoformat()
    return _load_jsonl(root, f"walkforward/{iso}/{market.lower()}.jsonl")


def _live_features(root: Path, ticker: str, market: str, iso: str) -> dict:
    """Compute RSI/MA20-dist/vol/momentum LIVE from parquet as of `iso`.
    No look-ahead: uses only bars up to and including iso."""
    from backend.research.mr_feature_enricher import (
        _load_parquet_cached, _slice_upto, _rsi14, _ma_dist, _vol_pct, _momentum,
    )
    cache: dict = {}
    pair = _load_parquet_cached(root, ticker, market, cache)
    if pair is None: return {}
    df, col, vol_col = pair
    closes_200 = _slice_upto(df, col, iso, 200) or \
                 _slice_upto(df, col, iso, 60) or \
                 _slice_upto(df, col, iso, 20)
    if not closes_200: return {}
    return {
        "rsi_14":           _rsi14(closes_200[-100:]) if len(closes_200) >= 100 else None,
        "ma20_dist_pct":    _ma_dist(closes_200, 20),
        "ma50_dist_pct":    _ma_dist(closes_200, 50) if len(closes_200) >= 50 else None,
        "ma200_dist_pct":   _ma_dist(closes_200, 200) if len(closes_200) >= 200 else None,
        "vol_20d_pct":      _vol_pct(closes_200, 20),
        "momentum_20d_pct": _momentum(closes_200, 20),
    }


def _enrich_snap(snap: list, lookup: dict, root: Path = None,
                 market: str = None, iso: str = None) -> list:
    """Merge features onto today's snapshot from three sources in order:
       1. Fields already present on the snapshot row (from canonical emit)
       2. LIVE parquet computation (RSI/MA/vol/momentum as of `iso`)
       3. Historical autopsy lookup for ticker-static features (band, sector)
    Also maps `entry_date` -> `recommended_date` so E5 has data."""
    keys = ("rsi_14","ma20_dist_pct","ma50_dist_pct","ma200_dist_pct",
            "vol_20d_pct","momentum_20d_pct","trend","cap_bucket",
            "fund_roe","fund_quality_score","investability_band","sector")
    out = []
    for r in snap:
        tk = str(r.get("ticker","")).upper()
        merged = dict(r)
        # Map entry_date -> recommended_date for E5
        if not merged.get("recommended_date") and merged.get("entry_date"):
            merged["recommended_date"] = str(merged["entry_date"])[:10]
        # 1) live parquet enrichment
        if root and market and iso and tk:
            live = _live_features(root, tk, market, iso)
            for k, v in live.items():
                if merged.get(k) is None: merged[k] = v
        # 2) fallback to historical lookup for ticker-static features
        if tk in lookup:
            for k in keys:
                if merged.get(k) is None:
                    merged[k] = lookup[tk].get(k)
        out.append(merged)
    return out


# ============================================================
# Shadow rules · each rule takes an enriched row and returns
#   (shadow_decision, rule_fired, reason)
# ============================================================


def rule_E1_confidence_anti_signal(r: dict) -> tuple:
    """India confidence 70-85 is anti-signal · demote to WARN."""
    conf = r.get("confidence_pct")
    runner = r.get("runner") or ""
    orig = r.get("status","ACTIVE")
    if str(runner).upper() != "R1":
        return (orig, False, "not_R1_scope")
    if isinstance(conf, (int, float)) and 70 <= conf <= 85:
        return ("WARN", True, f"confidence={conf} in anti-signal band 70-85")
    return (orig, False, "confidence_out_of_anti_band")


def rule_E2_top3_rank_inversion(r: dict) -> tuple:
    """R1 India top-3 · require ma20_dist in +1..+5 · else demote to rank_4_7."""
    runner = r.get("runner") or ""
    rank = r.get("rank")
    ma20 = r.get("ma20_dist_pct")
    orig = r.get("status","ACTIVE")
    if str(runner).upper() != "R1":
        return (orig, False, "not_R1_scope")
    if not isinstance(rank, int) or rank > 3:
        return (orig, False, "not_top3_slot")
    if isinstance(ma20, (int, float)) and 1.0 <= ma20 <= 5.0:
        return ("KEEP_TOP3", True, f"ma20_dist={ma20:.2f} passes +1..+5")
    return ("DEMOTE_TO_4_7", True,
            f"ma20_dist={ma20} outside +1..+5 · demote from top3")


def rule_E4_band_boundary(r: dict) -> tuple:
    """OK band predictions get re-scored under a shadow OK/MARGINAL boundary."""
    band = r.get("investability_band")
    orig = r.get("status","ACTIVE")
    if band != "OK":
        return (orig, False, "not_OK_band")
    conf = r.get("confidence_pct")
    if isinstance(conf, (int, float)) and conf >= 50:
        return ("SHADOW_MARGINAL", True,
                f"OK band with conf={conf} · shadow-reclassify as MARGINAL")
    return ("SHADOW_AVOID", True,
            f"OK band with low conf · shadow-reclassify as AVOID")


def rule_E5_stop_policy(r: dict) -> tuple:
    """Time-exit advisory: if held >=5 sessions from recommended_date, advisory."""
    rec = str(r.get("recommended_date","") or "")[:10]
    if not rec: return ("NO_ADVISORY", False, "no_recommended_date")
    try:
        rec_d = datetime.fromisoformat(rec).date()
    except Exception:
        return ("NO_ADVISORY", False, f"bad_recommended_date_{rec}")
    today = date.today()
    calendar_days = (today - rec_d).days
    if calendar_days < 7:  # ~5 trading days
        return ("HOLDING", False, f"{calendar_days}d held · below 5D trigger")
    return ("TIME_EXIT_ADVISORY", True,
            f"{calendar_days}d held · advisory TIME_STOP_5D exit candidate")


def rule_E3_negative_alpha_compound(r: dict) -> tuple:
    """Compound E1 + E2 + E4 + E5 decisions."""
    decisions = []
    reasons = []
    for name, fn in (("E1", rule_E1_confidence_anti_signal),
                     ("E2", rule_E2_top3_rank_inversion),
                     ("E4", rule_E4_band_boundary),
                     ("E5", rule_E5_stop_policy)):
        d, fired, reason = fn(r)
        if fired:
            decisions.append(f"{name}={d}")
            reasons.append(f"{name}:{reason}")
    if not decisions:
        return ("NO_COMPOUND_FIRED", False, "no_component_rule_fired")
    return ("COMPOUND_APPLIED", True, " | ".join(reasons))


# ============================================================
# CEO v2 close-out · 3 focused shadow experiments
# ============================================================


def rule_X1_r1_r2_ranking(r: dict) -> tuple:
    """India R1/R2 RANKING compound experiment.

    Combines E1 (confidence anti-signal) + E2 (top-3 rank inversion) into
    ONE ranking-scope decision:
       - If R1 top-3 AND ma20_dist outside +1..+5 → DEMOTE_TO_4_7
       - If R1 AND confidence 70-85 (anti-signal band) → WARN
       - Otherwise → KEEP
    """
    runner = str(r.get("runner","") or "").upper()
    if runner != "R1":
        return ("KEEP", False, "not_R1_scope")
    rank = r.get("rank")
    ma20 = r.get("ma20_dist_pct")
    conf = r.get("confidence_pct")
    fires = []
    decision = "KEEP"
    if isinstance(rank, int) and rank <= 3:
        if isinstance(ma20, (int, float)) and not (1.0 <= ma20 <= 5.0):
            decision = "DEMOTE_TO_4_7"
            fires.append(f"top3_ma20={ma20} outside +1..+5")
        elif ma20 is None:
            fires.append("top3_ma20_missing")
    if isinstance(conf, (int, float)) and 70 <= conf <= 85:
        if decision == "KEEP":
            decision = "WARN_CONFIDENCE"
        fires.append(f"conf={conf} in anti-signal band 70-85")
    if not fires:
        return ("KEEP", False, "no_R1_ranking_signal")
    return (decision, True, " | ".join(fires))


def rule_X2_stop_loss_time_5d(r: dict) -> tuple:
    """India TIME_STOP_5D advisory · same behavior as E5."""
    return rule_E5_stop_policy(r)


def rule_E1_india_r1_filter(r: dict) -> tuple:
    """CEO-FINAL E1 · India R1 negative filter.

    Weakest R1 cohort per 30D corpus:
      R1 top-3 with ma20_dist outside +1..+5     → 5D WR 14.5% (was 82 preds)
      R1 confidence 70-85 anti-signal band        → 5D WR 13.16% (was 103)

    Shadow rule: for India R1 rows, tag with REJECT_R1_WEAK when either
    weak-cohort condition is present. Otherwise KEEP_R1.
    """
    runner = str(r.get("runner","") or "").upper()
    if runner != "R1":
        return ("NOT_R1_SCOPE", False, "e1_targets_R1_only")
    fires = []
    rank = r.get("rank")
    ma20 = r.get("ma20_dist_pct")
    conf = r.get("confidence_pct")
    if isinstance(rank, int) and rank <= 3 and isinstance(ma20, (int, float)) \
       and not (1.0 <= ma20 <= 5.0):
        fires.append(f"top3_ma20={ma20:.2f} outside +1..+5 (14.5% WR cohort)")
    if isinstance(conf, (int, float)) and 70 <= conf <= 85:
        fires.append(f"conf={conf} in 70-85 anti-signal (13.16% WR cohort)")
    if not fires:
        return ("KEEP_R1", False, "R1_not_in_weak_cohort")
    return ("REJECT_R1_WEAK", True, " | ".join(fires))


def rule_E2_india_r2_rank_4_7_boost(r: dict) -> tuple:
    """CEO-FINAL E2 · India R2 rank_4_7 + RSI STRONG positive-boost.

    Best conditional 3-way per 30D corpus:
      runner=R2 · rank_4_7 · rsi=STRONG → 5D WR 72.73% (n=22, +46.96pp edge, sig+)

    Shadow rule: for India R2 rows in rank 4-7 with RSI in STRONG band
    (55-70), tag BOOST_R2_STRONG. Otherwise HOLD.
    """
    runner = str(r.get("runner","") or "").upper()
    if runner != "R2":
        return ("NOT_R2_SCOPE", False, "e2_targets_R2_only")
    rank = r.get("rank")
    rsi = r.get("rsi_14")
    if not isinstance(rank, int) or not (4 <= rank <= 7):
        return ("HOLD", False, f"rank={rank}_outside_4_7")
    if not isinstance(rsi, (int, float)):
        return ("HOLD", False, "rsi_missing")
    if 55 <= rsi < 70:
        return ("BOOST_R2_STRONG", True,
                f"R2 rank={rank} RSI={rsi:.1f} STRONG · matches 72.73% WR cohort")
    return ("HOLD", False, f"R2 rank={rank} RSI={rsi:.1f} outside 55-70 STRONG band")


def rule_E3_stop_loss_cross_market(r: dict) -> tuple:
    """CEO-FINAL E3 · Stop-loss cross-market.

    INDIA · TIME_STOP_5D advisory (n=500 historical replay: +0.273% expectancy,
    0.00% catastrophic vs CURRENT 0.20%). Fires on any position aged >=5
    sessions.
    USA · TRAILING_10 armed advisory (n=625 historical replay: +0.921%
    expectancy, PF 1.309 vs 0.645). Fires when position exists; the
    walk-forward scorer computes actual trailing-stop outcome
    retrospectively against parquet.
    """
    market_hint = str(r.get("market","")).upper()
    if "USA" in market_hint:
        # USA · arm TRAILING_10 advisory
        return ("TRAILING_10_ARMED", True,
                "USA TRAILING_10 advisory · scorer computes retrospectively")
    # India (default): existing TIME_STOP_5D behavior
    return rule_E5_stop_policy(r)


def rule_X3_usa_mid_cap_tilt(r: dict) -> tuple:
    """USA MID-cap tilt · CEO priority experiment.

    30D evidence (locked corpus):
       USA MID cap n=622  5D WR=46.60%  avg=+0.10%  (only USA positive-avg cohort)
       USA LARGE  cap n=459  5D WR=35.96%  avg=-0.84%

    Shadow rule for USA predictions:
      cap=MID     → BOOST_TO_MID_TILT        (accept + up-weight)
      cap=LARGE   → DEMOTE_FROM_LARGE_TILT   (accept but down-weight)
      cap=SMALL   → HOLD (existing behavior)
      cap=UNKNOWN → no shadow decision
    """
    market_hint = str(r.get("market","")).upper()
    if market_hint and "USA" not in market_hint:
        return ("NOT_USA_SCOPE", False, "usa_only_experiment")
    cap = r.get("cap_bucket")
    if cap == "MID":
        return ("BOOST_TO_MID_TILT", True,
                "USA cap=MID · 30D evidence 46.6% WR beats LARGE 36% by 10.6pp")
    if cap == "LARGE":
        return ("DEMOTE_FROM_LARGE_TILT", True,
                "USA cap=LARGE · 30D evidence 36% WR trails MID by 10.6pp")
    if cap == "SMALL":
        return ("HOLD_SMALL", False, "cap=SMALL · outside experiment scope")
    return ("NO_CAP_INFO", False, "cap_bucket_missing")


def rule_XA_technical_filter(r: dict) -> tuple:
    """Technical filter · combines RSI + MA20 evidence-backed edges.

    India evidence (30D corpus):
       - OVERSOLD_lt30 RSI: 43.75% WR (baseline 25.77%)
       - above_+1_+5 ma20_dist: 37.17% WR (baseline 25.77%)
    USA evidence:
       - near_-1_+1 ma20_dist: 51.61% WR (baseline 41.67%)
       - below_-5_-1 ma20_dist: 51.06% WR

    Shadow rule: apply POSITIVE_FILTER when technical setup passes at
    least ONE known-good bucket; apply NEGATIVE_FILTER when it hits a
    known-bad bucket (India: WEAK 30-45 RSI, below_-5_-1 ma20, or
    OVERBOUGHT>=70).
    """
    rsi = r.get("rsi_14")
    ma20 = r.get("ma20_dist_pct")
    market_hint = r.get("market","") or ""
    positive = []
    negative = []
    if isinstance(rsi, (int, float)):
        if rsi < 30:
            positive.append(f"RSI={rsi:.1f} OVERSOLD (India edge)")
        elif rsi >= 70:
            negative.append(f"RSI={rsi:.1f} OVERBOUGHT")
        elif 30 <= rsi < 45:
            negative.append(f"RSI={rsi:.1f} WEAK band (India edge -7pp)")
    if isinstance(ma20, (int, float)):
        if 1.0 <= ma20 <= 5.0:
            positive.append(f"ma20_dist={ma20:.2f} in +1..+5 (India edge +11pp)")
        elif -5.0 <= ma20 < -1.0:
            # In India this is bad; in USA it's a positive
            if "USA" in market_hint.upper():
                positive.append(f"ma20_dist={ma20:.2f} in -5..-1 (USA edge)")
            else:
                negative.append(f"ma20_dist={ma20:.2f} in -5..-1 (India edge -8pp)")
    if positive and not negative:
        return ("POSITIVE_FILTER", True, " · ".join(positive))
    if negative and not positive:
        return ("NEGATIVE_FILTER", True, " · ".join(negative))
    if positive and negative:
        return ("MIXED_FILTER", True,
                "POS: " + " · ".join(positive) + " | NEG: " + " · ".join(negative))
    return ("NO_FILTER_FIRED", False, "no_technical_edge_at_entry")


EXPERIMENT_RULES = {
    # ── CEO FINAL · 3 focused shadow experiments (frozen 2026-08-27) ──
    "aegis_mr_experiment_20260827_e1_india_r1_filter":
        (rule_E1_india_r1_filter, "india"),
    "aegis_mr_experiment_20260827_e2_india_r2_rank_4_7_boost":
        (rule_E2_india_r2_rank_4_7_boost, "india"),
    "aegis_mr_experiment_20260827_e3_stop_loss_cross_market":
        (rule_E3_stop_loss_cross_market, "india"),
    # ── Archived · earlier X-series retained for evidence continuity ──
    "aegis_mr_experiment_20260827_x1_india_r1_r2_ranking":
        (rule_X1_r1_r2_ranking, "india"),
    "aegis_mr_experiment_20260827_x2_stop_loss_time_5d":
        (rule_X2_stop_loss_time_5d, "india"),
    "aegis_mr_experiment_20260827_x3_usa_mid_cap_tilt":
        (rule_X3_usa_mid_cap_tilt, "usa"),
    "aegis_mr_experiment_20260827_x3_technical_filter":
        (rule_XA_technical_filter, "india"),
    # ── Superseded · kept for evidence continuity but marked ARCHIVED ──
    # (These continue to write shadow rows so historical experiment JSON
    # remains reproducible.)
    "aegis_mr_experiment_20260827_india_confidence_anti_signal":
        (rule_E1_confidence_anti_signal, "india"),
    "aegis_mr_experiment_20260827_india_top3_rank_inversion":
        (rule_E2_top3_rank_inversion, "india"),
    "aegis_mr_experiment_20260827_india_band_boundary":
        (rule_E4_band_boundary, "india"),
    "aegis_mr_experiment_20260827_india_stop_policy":
        (rule_E5_stop_policy, "india"),
    "aegis_mr_experiment_20260827_india_negative_alpha":
        (rule_E3_negative_alpha_compound, "india"),
}

FOCUSED_EXPERIMENTS = [
    "aegis_mr_experiment_20260827_e1_india_r1_filter",
    "aegis_mr_experiment_20260827_e2_india_r2_rank_4_7_boost",
    "aegis_mr_experiment_20260827_e3_stop_loss_cross_market",
]

SUPERSEDED_EXPERIMENTS = {
    "aegis_mr_experiment_20260827_india_confidence_anti_signal":
        "aegis_mr_experiment_20260827_x1_india_r1_r2_ranking",
    "aegis_mr_experiment_20260827_india_top3_rank_inversion":
        "aegis_mr_experiment_20260827_x1_india_r1_r2_ranking",
    "aegis_mr_experiment_20260827_india_band_boundary": None,   # ARCHIVED_LOW_PRIORITY
    "aegis_mr_experiment_20260827_india_negative_alpha":
        "aegis_mr_experiment_20260827_x1_india_r1_r2_ranking",
    "aegis_mr_experiment_20260827_india_stop_policy":
        "aegis_mr_experiment_20260827_x2_stop_loss_time_5d",
}


def run_experiment(root: Path, experiment_id: str, rule_fn, market: str,
                   iso: str) -> dict:
    snap = _snap_today(root, market)
    if not snap:
        return {"experiment_id": experiment_id, "status": "NO_SNAPSHOT",
                "market": market.upper(), "iso": iso, "n_rows": 0}
    lookup = _load_enriched_lookup(root, market)
    enriched = _enrich_snap(snap, lookup, root=root, market=market, iso=iso)
    dst_dir = root / ALLOWED_WRITE_ROOT / "experiments" / experiment_id / iso
    dst_dir.mkdir(parents=True, exist_ok=True)
    # For cross-market experiments, distinguish per-market files
    suffix = f"_{market.lower()}" if "e3_stop_loss_cross_market" in experiment_id else ""
    dst = dst_dir / f"shadow{suffix}.jsonl"
    n_scored = 0
    n_fired = 0
    with dst.open("w", encoding="utf-8") as f:
        for r in enriched:
            shadow_decision, rule_fired, reason = rule_fn(r)
            if rule_fired: n_fired += 1
            row = {
                "iso":              iso,
                "experiment_id":    experiment_id,
                "market":           market.upper(),
                "ticker":           r.get("ticker"),
                "runner":           r.get("runner"),
                "rank":             r.get("rank"),
                "confidence_pct":   r.get("confidence_pct"),
                "investability_band": r.get("investability_band"),
                "original_decision": r.get("status"),
                "shadow_decision":   shadow_decision,
                "rule_fired":        rule_fired,
                "reason":            reason,
                "engine":            ENGINE_ID,
            }
            f.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
            n_scored += 1
    return {"experiment_id": experiment_id, "status": "OK",
            "market": market.upper(), "iso": iso,
            "n_rows": n_scored, "n_fired": n_fired,
            "output": str(dst.relative_to(root))}


def _update_experiment_status(root: Path, experiment_id: str, iso: str,
                              n_rows: int) -> None:
    p = root / ALLOWED_WRITE_ROOT / "experiments" / f"{experiment_id}.json"
    if not p.exists(): return
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception: return
    current = d.get("current_status", "")
    # Preserve terminal statuses · do NOT flip SUPERSEDED / ARCHIVED back to ACTIVE_SHADOW
    if current in ("SUPERSEDED_BY", "ARCHIVED_LOW_PRIORITY", "ARCHIVED_FOR_LATER"):
        pass  # leave status as is · still record attempt for evidence continuity
    elif current == "NOT_STARTED" and n_rows > 0:
        d["current_status"] = "ACTIVE_SHADOW"
    if not d.get("first_snapshot_date"):
        d["first_snapshot_date"] = iso
    d["days_of_evidence"] = int(d.get("days_of_evidence", 0)) + (1 if n_rows > 0 else 0)
    attempts = d.get("attempts") or []
    attempts.append({
        "iso":       iso,
        "n_rows":    n_rows,
        "runner":    ENGINE_ID,
    })
    d["attempts"] = attempts
    d["updated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False, default=str),
                 encoding="utf-8")


def run_all(root: Path) -> dict:
    iso = date.today().isoformat()
    results = []
    for exp_id, (rule_fn, market) in EXPERIMENT_RULES.items():
        # E3 cross-market · runs BOTH India and USA snapshots
        markets = ("india","usa") if "e3_stop_loss_cross_market" in exp_id else (market,)
        for mkt in markets:
            r = run_experiment(root, exp_id, rule_fn, mkt, iso)
            if r.get("status") == "OK":
                _update_experiment_status(root, exp_id, iso, r["n_rows"])
            results.append(r)
    # Refresh experiment INDEX after status flips
    _refresh_index(root)
    manifest = {
        "engine":         ENGINE_ID,
        "generated_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "iso":            iso,
        "n_experiments": len(results),
        "results":        results,
    }
    p = root / ALLOWED_WRITE_ROOT / "experiments" / f"runner_{iso}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def _refresh_index(root: Path) -> None:
    exp_dir = root / ALLOWED_WRITE_ROOT / "experiments"
    if not exp_dir.exists(): return
    tickets = []
    for p in sorted(exp_dir.glob("aegis_mr_experiment_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        tickets.append({
            "experiment_id":         d.get("experiment_id"),
            "source_ticket_id":      d.get("source_ticket_id"),
            "market":                d.get("market"),
            "current_status":        d.get("current_status"),
            "min_sample_size":       d.get("min_sample_size"),
            "observation_window_days": d.get("observation_window_days"),
            "metric":                d.get("metric"),
            "first_snapshot_date":   d.get("first_snapshot_date"),
            "days_of_evidence":      d.get("days_of_evidence"),
        })
    idx = {
        "engine":       "aegis.mr_experiment_runner.index.v0.1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_experiments": len(tickets),
        "experiments":  tickets,
    }
    (exp_dir / "INDEX.json").write_text(
        json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")


def render_console(manifest: dict):
    print(f"\n======== SHADOW EXPERIMENT RUNNER · {manifest['iso']} ========")
    for r in manifest["results"]:
        if r["status"] == "OK":
            print(f"  [OK] {r['experiment_id']}")
            print(f"       market={r['market']} n_rows={r['n_rows']} "
                  f"n_fired={r['n_fired']}")
            print(f"       output: {r['output']}")
        else:
            print(f"  [{r['status']}] {r['experiment_id']}")


if __name__ == "__main__":
    root = Path(".").resolve()
    manifest = run_all(root)
    render_console(manifest)
    print(f"\n[experiment_runner] wrote runner_{manifest['iso']}.json + "
          f"per-experiment shadow.jsonl files")
