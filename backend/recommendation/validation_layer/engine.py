"""Runner 1 → Validation Layer engine.

Reads the legacy Runner 1 daily CSV (data/aegis_today.csv), maps each
Runner 1 pick to a normalized action, then for every Runner 2 rec computes
the Runner-1 agreement (or absence). Also lists Runner-1-only orphan picks.

Runner 1 CSV schema (columns of interest):
    Generated, Profile, Stock, Sector, Strength, Score /100,
    Current Price, Buy Range, Rec Confidence %, Recommended Holding, Why

Runner 1 strength → normalized action mapping:
    STRONG BUY / ACCUMULATE / BUY  → "BUY"
    WATCH                          → "WATCH"
    HOLD                            → "HOLD"
    SELL / REDUCE / STRONG SELL     → "SELL"

Article 101.2 compliant · pure enrichment · no new predictive model.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.recommendation.validation_layer.runner1.v1.20260729"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.recommendation.validation_layer.runner1.v1"

STRENGTH_TO_ACTION = {
    "STRONG BUY":  "BUY",
    "ACCUMULATE":  "BUY",
    "BUY":         "BUY",
    "WATCH":       "WATCH",
    "HOLD":        "HOLD",
    "REDUCE":      "SELL",
    "SELL":        "SELL",
    "STRONG SELL": "SELL",
    "EXIT":        "SELL",
    "AVOID":       "SELL",
}


@dataclass
class Runner1Pick:
    ticker: str
    action: str            # normalized: BUY / WATCH / HOLD / SELL
    strength: str          # raw Runner 1 strength label
    score: float | None
    confidence: float | None
    current_price: float | None
    buy_range: str
    hist_target: float | None
    expected_range: str
    holding: str
    review_date: str
    valid_until: str
    sector: str
    reason: str


def _normalize_ticker(t: str) -> str:
    """Runner 1 uses bare 'LUPIN' · Runner 2 uses 'LUPIN.NS'. Normalize."""
    if not t:
        return ""
    return str(t).split(".", 1)[0].strip().upper()


def load_runner1_picks(csv_path: Path) -> dict[str, Runner1Pick]:
    """Return {normalized_ticker: Runner1Pick}."""
    picks: dict[str, Runner1Pick] = {}
    if not csv_path.exists():
        return picks
    try:
        with csv_path.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = _normalize_ticker(row.get("Stock", ""))
                if not ticker:
                    continue
                strength = str(row.get("Strength", "")).strip().upper()
                action = STRENGTH_TO_ACTION.get(strength, "HOLD")
                def _num(v):
                    try:
                        return float(v) if v not in (None, "", "—", "-") else None
                    except (TypeError, ValueError):
                        return None
                picks[ticker] = Runner1Pick(
                    ticker=ticker,
                    action=action,
                    strength=strength,
                    score=_num(row.get("Score /100")),
                    confidence=_num(row.get("Rec Confidence %")),
                    current_price=_num(row.get("Current Price")),
                    buy_range=str(row.get("Buy Range", "")).strip(),
                    hist_target=_num(row.get("Hist Target")),
                    expected_range=str(row.get("Expected Range (hist)", "")).strip(),
                    holding=str(row.get("Recommended Holding", "")).strip(),
                    review_date=str(row.get("Review Date", "")).strip(),
                    valid_until=str(row.get("Valid Until", "")).strip(),
                    sector=str(row.get("Sector", "")).strip(),
                    reason=str(row.get("Why", "")).strip(),
                )
    except (OSError, ValueError):
        return {}
    return picks


def compute_agreement(runner2_action: str,
                        runner1_pick: Runner1Pick | None) -> dict:
    """Compare Runner 2's action vs Runner 1's opinion for a single ticker.

    Returns:
      { runner1_action, runner1_strength, runner1_confidence,
        agreement, agreement_label, note }

    Agreement scale:
      +1  strong-agree   (both bullish or both bearish)
       0  neutral        (one active, other not present / neutral)
      -1  disagree       (opposite direction)
    """
    r2 = str(runner2_action or "").upper()
    r2_bullish = r2 in ("BUY", "STRONG_BUY", "ADD")
    r2_bearish = r2 in ("SELL", "STRONG_SELL", "REDUCE", "EXIT", "AVOID")

    if runner1_pick is None:
        return {
            "runner1_action":     None,
            "runner1_strength":   None,
            "runner1_confidence": None,
            "agreement":          0,
            "agreement_label":    "NOT_TRACKED",
            "note":               "Runner 1 does not cover this ticker today",
        }

    r1 = runner1_pick.action
    r1_bullish = r1 == "BUY"
    r1_bearish = r1 == "SELL"

    if r2_bullish and r1_bullish:
        agreement, label = 1, "AGREE (both bullish)"
    elif r2_bearish and r1_bearish:
        agreement, label = 1, "AGREE (both bearish)"
    elif r2_bullish and r1_bearish:
        agreement, label = -1, "DISAGREE (Runner 2 buy · Runner 1 sell)"
    elif r2_bearish and r1_bullish:
        agreement, label = -1, "DISAGREE (Runner 2 sell · Runner 1 buy)"
    else:
        agreement, label = 0, f"NEUTRAL (Runner 1: {runner1_pick.strength})"

    return {
        "runner1_action":     r1,
        "runner1_strength":   runner1_pick.strength,
        "runner1_confidence": runner1_pick.confidence,
        "agreement":          agreement,
        "agreement_label":    label,
        "note":               f"Runner 1 says {runner1_pick.strength} (score {runner1_pick.score}) · {runner1_pick.reason[:80]}",
    }


def build_validation_report(runner2_recs: Sequence[Mapping],
                                runner1_csv: Path) -> dict:
    """Compute full validation report:

    - Per Runner 2 rec: add validation block (agreement · label · note)
    - Cross-market: orphans (Runner 1 tickers NOT in Runner 2)
    - Rollup: agreement summary counts
    """
    r1_picks = load_runner1_picks(runner1_csv)
    r2_tickers_seen: set[str] = set()

    per_rec_validation: dict[str, dict] = {}
    agreement_counts = {"AGREE": 0, "DISAGREE": 0, "NEUTRAL": 0, "NOT_TRACKED": 0}
    for r in runner2_recs:
        raw_ticker = str(r.get("ticker") or "")
        norm = _normalize_ticker(raw_ticker)
        r2_tickers_seen.add(norm)
        r2_action = (r.get("investor_action") or {}).get("entry") or \
                     r.get("percentile_action") or r.get("action") or "HOLD"
        pick = r1_picks.get(norm)
        validation = compute_agreement(r2_action, pick)
        per_rec_validation[raw_ticker] = validation
        # Bucket rollup
        label = validation["agreement_label"]
        if label.startswith("AGREE"):
            agreement_counts["AGREE"] += 1
        elif label.startswith("DISAGREE"):
            agreement_counts["DISAGREE"] += 1
        elif label == "NOT_TRACKED":
            agreement_counts["NOT_TRACKED"] += 1
        else:
            agreement_counts["NEUTRAL"] += 1

    # Runner 1 orphans = tickers Runner 1 picks but Runner 2 didn't include
    orphans: list[dict] = []
    for ticker, pick in r1_picks.items():
        if ticker in r2_tickers_seen:
            continue
        if pick.action not in ("BUY", "WATCH"):
            continue   # only surface active Runner 1 picks
        orphans.append({
            "ticker":         ticker,
            "sector":         pick.sector,
            "action":         pick.action,
            "strength":       pick.strength,
            "score":          pick.score,
            "confidence":     pick.confidence,
            "price":          pick.current_price,
            "buy_range":      pick.buy_range,
            "hist_target":    pick.hist_target,
            "expected_range": pick.expected_range,
            "holding":        pick.holding,
            "valid_until":    pick.valid_until,
            "reason":         pick.reason[:120] + ("..." if len(pick.reason) > 120 else ""),
        })
    orphans.sort(key=lambda o: -(o.get("score") or 0))

    n_r2 = len(runner2_recs)
    consensus_pct = round(100 * agreement_counts["AGREE"] / n_r2, 1) if n_r2 else 0.0

    return {
        "engine":               ENGINE_ID,
        "schema_fingerprint":   SCHEMA_FINGERPRINT,
        "run_utc":              datetime.now(timezone.utc).isoformat(),
        "runner1_csv":          str(csv_path_name(runner1_csv)),
        "n_runner1_picks":      len(r1_picks),
        "n_runner2_recs":       n_r2,
        "consensus_pct":        consensus_pct,
        "agreement_counts":     agreement_counts,
        "per_rec_validation":   per_rec_validation,
        "runner1_orphans":      orphans,
    }


def csv_path_name(p: Path) -> str:
    """Small helper · returns a stable relative path for reporting."""
    try:
        return str(p.name)
    except Exception:
        return str(p)


def enrich_recs_with_validation(runner2_recs: Sequence,
                                    runner1_csv: Path) -> Sequence:
    """Attach `validation` block to each Runner 2 rec in-place."""
    report = build_validation_report(runner2_recs, runner1_csv)
    per_rec = report.get("per_rec_validation", {})
    for r in runner2_recs:
        r["validation"] = per_rec.get(str(r.get("ticker") or ""), {})
    return runner2_recs
