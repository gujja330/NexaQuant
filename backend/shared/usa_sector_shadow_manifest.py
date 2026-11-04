"""§5 · machine-readable manifest for a USA sector SHADOW build.

CEO 2026-11-04 · Phase 1B.

The manifest describes what a build ACTUALLY produced. Every number is
computed at generation time from the files and the resolver - none is a
hardcoded expectation. That is the point: the previous shadow results
were reported in prose, so a later run could drift from them silently
and nobody would know which figures were measured and which were
remembered.

Shadow only. Generating a manifest wires nothing: the resolver is
injected for the duration of one build and the production feature files
are never written.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA = "aegis.usa_sector_shadow.manifest.v1"
RESOLVER_VERSION = "usa_sector_resolver.v1"
TAXONOMY_VERSION = "_USA_SECTOR_TO_ETF.11sector.v1"


def _sha(p) -> Optional[str]:
    p = Path(p)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _frame_sha(df) -> str:
    """Stable hash of a DataFrame's content, column order included."""
    import pandas as pd
    buf = df.reindex(sorted(df.columns), axis=1)
    return hashlib.sha256(
        pd.util.hash_pandas_object(buf, index=False).values.tobytes()
    ).hexdigest()


def build_manifest(repo_root: Path, asof: date,
                   baseline_df, shadow_df,
                   baseline_scores: dict, shadow_scores: dict,
                   india_isolation: dict,
                   test_refs: Optional[list] = None) -> dict:
    """Assemble the manifest from measured inputs only."""
    import pandas as pd
    from backend.feature_store.features.sector import _USA_SECTOR_TO_ETF
    from backend.shared.usa_sector_resolver import (EXACT, MAPPED,
                                                    REVIEW_REQUIRED, UNKNOWN,
                                                    coverage_report,
                                                    load_store, resolve_many)
    root = Path(repo_root)
    uni = sorted({t["symbol"] for t in json.loads(
        (root / "usa" / "reports" / "universe.json").read_text(encoding="utf-8")
    ).get("tickers", []) if t.get("symbol")})

    store = load_store(root)
    res = resolve_many(root, uni)
    cov = coverage_report(root, uni)

    retrieved = sorted({r.get("retrieved_at_utc") for r in store.values()
                        if r.get("retrieved_at_utc")})
    first_obs = sorted({r.get("first_observed_date") for r in store.values()
                        if r.get("first_observed_date")})

    # feature-level attribution, computed
    cols = sorted(set(baseline_df.columns) | set(shadow_df.columns))
    changed_cols = []
    for c in cols:
        if c not in baseline_df or c not in shadow_df:
            changed_cols.append(c)
        elif not baseline_df[c].equals(shadow_df[c]):
            changed_cols.append(c)

    # model-level attribution, computed
    model_attr = {}
    for m in sorted(set(baseline_scores) | set(shadow_scores)):
        a, b = baseline_scores.get(m), shadow_scores.get(m)
        if a is None or b is None:
            model_attr[m] = {"comparable": False}
            continue
        x, y = a.align(b, join="inner")
        d = (x - y).abs()
        model_attr[m] = {
            "comparable": True,
            "n": int(len(d)),
            "n_changed": int((d > 0).sum()),
            "max_abs_delta": float(d.max()) if len(d) else 0.0,
            "median_abs_delta_where_changed": (
                float(d[d > 0].median()) if (d > 0).any() else 0.0),
        }

    sector_feats = ("sector", "sector_return_1m_pct", "sector_rank",
                    "sector_is_leader", "sector_is_laggard")
    feat_cov = {}
    for f in sector_feats:
        feat_cov[f] = {
            "baseline_populated": int(baseline_df[f].notna().sum())
            if f in baseline_df else 0,
            "shadow_populated": int(shadow_df[f].notna().sum())
            if f in shadow_df else 0,
            "shadow_distinct": int(shadow_df[f].dropna().nunique())
            if f in shadow_df else 0,
        }

    # proxy availability is SEPARATE from classification availability
    proxies = sorted(set(_USA_SECTOR_TO_ETF.values()))

    return {
        "schema": SCHEMA,
        "build_id": "usa-sector-shadow-%s" % datetime.now(timezone.utc)
                    .strftime("%Y%m%dT%H%M%SZ"),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asof": asof.isoformat(),
        "wired_into_production": False,
        "resolver_version": RESOLVER_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy": sorted(_USA_SECTOR_TO_ETF),
        "n_taxonomy_sectors": len(_USA_SECTOR_TO_ETF),
        "sources": {
            "universe": {
                "path": "usa/reports/universe.json",
                "sha256": _sha(root / "usa" / "reports" / "universe.json"),
                "n_symbols": len(uni),
            },
            "sic_mapping": {
                "path": "configs/usa_sic_sector_map.yaml",
                "sha256": _sha(root / "configs" / "usa_sic_sector_map.yaml"),
            },
            "sec_classification_store": {
                "path": "data/classification/sec_sic.json",
                "sha256": _sha(root / "data" / "classification" / "sec_sic.json"),
                "n_companies": len(store),
                "retrieved_at_utc_min": retrieved[0] if retrieved else None,
                "retrieved_at_utc_max": retrieved[-1] if retrieved else None,
            },
        },
        "cik_resolution": {
            "n_universe": len(uni),
            "n_in_store": len(store),
            "n_with_sic": sum(1 for r in store.values() if r.get("sic_code")),
            "n_absent_from_store": len([t for t in uni if t not in store]),
        },
        "classification": {
            "n_classified": cov["n_classified"],
            "classified_pct": cov["classified_pct"],
            "by_mapping_method": cov["by_mapping_method"],
            "by_review_status": cov["by_review_status"],
            "by_sector": cov["by_sector"],
            "n_unclassified": cov["n_unclassified"],
            "unclassified_sample": cov["unclassified"][:20],
        },
        "first_observed": {
            "n_with_first_observed": len([r for r in store.values()
                                          if r.get("first_observed_date")]),
            "earliest": first_obs[0] if first_obs else None,
            "latest": first_obs[-1] if first_obs else None,
            "basis": "FIRST_OBSERVED",
            "note": ("SEC publishes no sicHistory · effective_from equals "
                     "first_observed_date and a query before it returns "
                     "UNAVAILABLE rather than backdating"),
        },
        "proxy_coverage": {
            "note": ("classification availability is SEPARATE from sector "
                     "benchmark availability · a missing ETF observation "
                     "must not erase a valid company classification"),
            "sector_etfs": proxies,
            "n_sector_etfs": len(proxies),
        },
        "feature_output": {
            "n_rows": int(len(shadow_df)),
            "n_columns": int(len(shadow_df.columns)),
            "sha256": _frame_sha(shadow_df),
            "baseline_sha256": _frame_sha(baseline_df),
            "changed_columns": changed_cols,
            "n_changed_columns": len(changed_cols),
            "sector_feature_coverage": feat_cov,
        },
        "model_output": {
            "n_models": len(model_attr),
            "attribution": model_attr,
            "changed_models": sorted(m for m, v in model_attr.items()
                                     if v.get("n_changed")),
            "unchanged_models": sorted(m for m, v in model_attr.items()
                                       if v.get("comparable")
                                       and not v.get("n_changed")),
        },
        "india_isolation": india_isolation,
        "test_references": test_refs or [
            "tests/pipeline/test_usa_sector_resolver.py",
            "tests/pipeline/test_sector_map_contract.py",
        ],
    }


def verdict(manifest: dict) -> dict:
    """Validation verdict, derived from the manifest's own numbers."""
    c = manifest["classification"]
    f = manifest["feature_output"]
    m = manifest["model_output"]
    india = manifest.get("india_isolation") or {}
    checks = {
        "taxonomy_is_11_sectors": manifest["n_taxonomy_sectors"] == 11,
        "no_sector_outside_taxonomy":
            set(c["by_sector"]) <= set(manifest["taxonomy"]),
        "classified_matches_sector_feature":
            c["n_classified"]
            == f["sector_feature_coverage"]["sector"]["shadow_populated"],
        "classified_matches_sector_rank":
            c["n_classified"]
            == f["sector_feature_coverage"]["sector_rank"]["shadow_populated"],
        "no_proxy_mapping_used": c["by_mapping_method"].get("PROXY", 0) == 0,
        "unclassified_are_review_required":
            c["by_review_status"].get("REVIEW_REQUIRED", 0)
            == c["n_unclassified"],
        "india_unchanged": india.get("n_changed_columns") == 0
                           and india.get("n_changed_models") == 0,
        "not_wired": manifest["wired_into_production"] is False,
        "only_sector_columns_changed":
            all(col.startswith("sector") for col in f["changed_columns"]),
    }
    return {"checks": checks,
            "failed": [k for k, v in checks.items() if not v],
            "verdict": "VALID" if all(checks.values()) else "INVALID"}
