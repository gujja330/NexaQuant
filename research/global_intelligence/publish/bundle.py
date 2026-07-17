"""DEV017 v0.1 publish — produce global_context.json (and .parquet mirror).

Output matches ARCH017 §9.1 shape (subset for v0.1).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..lib.schema import as_dict

ROOT = Path(__file__).resolve().parents[3]
PUBLISH_DIR = ROOT / "reports"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_bundle(derived, normalized, classifications, composites, code_sha: str = "nogit") -> dict:
    now_utc = _now_utc_iso()
    if composites:
        asof = list(composites.values())[0].asof_utc
    elif normalized:
        asof = normalized[0].asof_utc
    else:
        asof = now_utc

    # Composites map
    comp_map = {}
    for key, c in composites.items():
        short_key = key.replace("composite.", "")
        comp_map[short_key] = {
            "value_0_100": c.value_0_100,
            "classification": c.classification,
            "confidence": c.confidence,
            "weighting_version": c.weighting_version,
        }

    # Classifications map
    cls_map = {c.key: {"label": c.label, "confidence": c.confidence}
                for c in classifications}

    # Top contributors (for global_risk if available)
    contributions = {}
    if "composite.global_risk" in composites:
        gr = composites["composite.global_risk"]
        ranked = sorted(gr.component_indicators,
                          key=lambda x: x["contribution_to_composite"], reverse=True)
        contributions["global_risk_top5"] = [
            {"indicator": x["indicator_key"],
             "contribution": x["contribution_to_composite"],
             "value_0_100": x["value_0_100"],
             "weight": x["weight"]}
            for x in ranked[:5]
        ]

    warnings = []
    for c in classifications:
        if c.label == "Unknown":
            warnings.append(f"{c.key} classification is Unknown (confidence={c.confidence:.2f})")

    return {
        "asof_date_ist":            _asof_ist_date(asof),
        "asof_utc":                 asof,
        "published_at_utc":         now_utc,
        "code_sha":                 code_sha,
        "schema_version":           "ARCH017A v1.0-draft",
        "weighting_version":        "ARCH017 v1.0-draft",
        "dev_version":              "DEV017 v0.1",
        "composites":               comp_map,
        "classifications":          cls_map,
        "contributions":            contributions,
        "warnings":                 warnings,
        "summary_counts": {
            "derived_metrics":       len(derived),
            "normalized_indicators": len(normalized),
            "classifications":       len(classifications),
            "composites":            len(composites),
        },
    }


def _asof_ist_date(asof_utc_iso: str) -> str:
    from datetime import timedelta
    utc = datetime.fromisoformat(asof_utc_iso.replace("Z", "+00:00"))
    ist = utc + timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d")


def write_bundle(bundle: dict) -> tuple[Path, Path]:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
    json_path = PUBLISH_DIR / "global_context.json"
    parquet_path = PUBLISH_DIR / "global_context.parquet"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2)

    # Flatten to a single-row DataFrame for parquet mirror
    flat = {
        "asof_date_ist": bundle["asof_date_ist"],
        "asof_utc": bundle["asof_utc"],
        "published_at_utc": bundle["published_at_utc"],
        "code_sha": bundle["code_sha"],
        "dev_version": bundle["dev_version"],
    }
    for k, c in bundle["composites"].items():
        flat[f"composite.{k}.value"] = c["value_0_100"]
        flat[f"composite.{k}.classification"] = c["classification"]
        flat[f"composite.{k}.confidence"] = c["confidence"]
    for k, cl in bundle["classifications"].items():
        flat[f"classification.{k}.label"] = cl["label"]
        flat[f"classification.{k}.confidence"] = cl["confidence"]

    pd.DataFrame([flat]).to_parquet(parquet_path, index=False)
    return json_path, parquet_path
