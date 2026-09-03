"""B1 · Regime enricher · Sprint A · Batch B
CEO 2026-09-03 · highest-fan-out substrate task.

Populates `regime_at_entry` on every Outcome Dataset row from the PIT
mr_market_regime source. This unlocks:
  - P0 regime segmentation (mandatory per PDF · P0-EXTENSION-01 gated on it)
  - P2 sector/regime α,β lift measurement
  - P5.2 regime-conditional ensemble weights

## Vocabulary

PDF-locked target vocabulary (Sec 2 · pasted-plan Sec 26):
    NORMAL · WEAKENING · RISK_OFF · CRASH · RECOVERY · UNKNOWN

Source vocabulary (reports/research/mr_market_regime_{market}.json):
    BULL · BEAR · HIGH_VOL · NEUTRAL

## Mapping (documented, transparent, additive-only)

    MR         →  PDF
    ─────────────────
    BULL       →  NORMAL
    NEUTRAL    →  NORMAL
    HIGH_VOL   →  RISK_OFF
    BEAR       →  WEAKENING

CRASH and RECOVERY are NOT emitted by this enricher · they require
additional event-detectors:
    CRASH    · WEAKENING + market 1-day return < -3σ (declared: CRASH_DETECTOR_01)
    RECOVERY · NORMAL/BULL trailing 20d after a CRASH date
                (declared: RECOVERY_DETECTOR_01)

Both declared as ADDITIVE detectors in the Evidence Log · not yet run.
This enricher covers 4 of the 6 PDF states; the other 2 layer on top later.

## No fabrication

- Dates missing from the source → `regime_at_entry = UNKNOWN`, `regime_source = "missing"`, `regime_confidence = 0.0`
- Dates before source start date → same
- Dates after source last-updated → same
- Non-mapped source labels → `regime_at_entry = UNKNOWN`, `regime_source = "unmapped:<label>"`
- Every row carries provenance in `regime_source` + `regime_asof_source_date` columns.

## PIT rule

For each Outcome Dataset row with `entry_date = D`, we look up the source
regime on the largest date ≤ D that exists in the source. If none exists,
UNKNOWN. Never look forward.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]

REGIME_VOCAB = ["NORMAL", "WEAKENING", "RISK_OFF", "CRASH", "RECOVERY", "UNKNOWN"]

MR_TO_PDF_MAP = {
    "BULL":     "NORMAL",
    "NEUTRAL":  "NORMAL",
    "HIGH_VOL": "RISK_OFF",
    "BEAR":     "WEAKENING",
}


def _load_source(root: Path, market: str) -> Optional[dict]:
    """Load reports/research/mr_market_regime_{market}.json regime map.

    Returns {date_str: raw_label} or None if source missing.
    """
    p = root / "reports" / "research" / f"mr_market_regime_{market}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    regimes = d.get("regimes") or {}
    if not isinstance(regimes, dict):
        return None
    return regimes


def _pit_lookup(source: dict, entry_date: str) -> tuple[Optional[str], Optional[str]]:
    """Return (raw_label, source_date) for the largest date <= entry_date
    that exists in source. None if none exists.
    """
    if not entry_date or not source:
        return None, None
    dates = sorted(k for k in source.keys() if k <= entry_date)
    if not dates:
        return None, None
    d = dates[-1]
    return str(source[d]), d


def _map(raw: Optional[str]) -> tuple[str, str]:
    """Return (pdf_label, source_tag). No fabrication."""
    if raw is None:
        return "UNKNOWN", "missing"
    mapped = MR_TO_PDF_MAP.get(str(raw).upper())
    if mapped is None:
        return "UNKNOWN", f"unmapped:{raw}"
    return mapped, f"mr_market_regime:{raw}"


def enrich_regime(root: Path, market: str) -> dict:
    """Enrich Outcome Dataset with regime_at_entry column · in-place merge.

    Returns summary dict. Idempotent · safe to re-run.
    """
    import pandas as pd

    od_path = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if not od_path.exists():
        return {"market": market, "status": "OUTCOME_DATASET_MISSING"}
    df = pd.read_parquet(od_path)
    if df.empty:
        return {"market": market, "status": "OUTCOME_DATASET_EMPTY"}

    source = _load_source(root, market)
    if source is None:
        return {"market": market, "status": "REGIME_SOURCE_MISSING",
                "expected_path": f"reports/research/mr_market_regime_{market}.json"}

    # Ensure new columns exist
    if "regime_source" not in df.columns:
        df["regime_source"] = None
    if "regime_asof_source_date" not in df.columns:
        df["regime_asof_source_date"] = None

    dist_before: dict = {}
    if "regime_at_entry" in df.columns:
        dist_before = df["regime_at_entry"].fillna("null").value_counts().to_dict()

    n_updated = 0
    n_unknown = 0
    n_unmapped = 0
    from collections import Counter
    new_dist: Counter = Counter()

    for i in df.index:
        entry_date = str(df.at[i, "entry_date"]) if pd.notna(df.at[i, "entry_date"]) else ""
        raw, source_date = _pit_lookup(source, entry_date)
        pdf_label, source_tag = _map(raw)
        df.at[i, "regime_at_entry"] = pdf_label
        df.at[i, "regime_source"] = source_tag
        df.at[i, "regime_asof_source_date"] = source_date
        new_dist[pdf_label] += 1
        n_updated += 1
        if pdf_label == "UNKNOWN":
            n_unknown += 1
            if source_tag.startswith("unmapped:"):
                n_unmapped += 1

    df.to_parquet(od_path, index=False)

    summary = {
        "market": market,
        "status": "ENRICHED",
        "n_rows_updated": n_updated,
        "regime_distribution_after": dict(new_dist),
        "regime_distribution_before": dist_before,
        "n_unknown": n_unknown,
        "n_unmapped_source_labels": n_unmapped,
        "source_file": f"reports/research/mr_market_regime_{market}.json",
        "source_date_range": [
            min(source.keys()) if source else None,
            max(source.keys()) if source else None,
        ],
        "mapping_used": MR_TO_PDF_MAP,
        "note_missing_states": (
            "CRASH and RECOVERY are NOT emitted by this enricher · declared "
            "as CRASH_DETECTOR_01 and RECOVERY_DETECTOR_01 (additive · not "
            "yet run). This enricher covers 4 of the 6 PDF regime states."
        ),
        "pit_rule": "For entry_date D, use largest source date <= D. Never look forward.",
        "no_fabrication": "Missing dates → UNKNOWN. Unmapped labels → UNKNOWN with source_tag.",
        "enriched_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out_dir = root / "reports" / "research" / "enrichers"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"regime_{market}.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    return summary


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa", "both"), default="both")
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    markets = ["india", "usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = enrich_regime(root, m)
        print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()
