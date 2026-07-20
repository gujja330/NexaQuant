"""AEGIS USA · Feature Store snapshot runner (Sprint 2.5). USD.

Mirror of india/feature_store/run.py using USA_PROFILE.
"""
from __future__ import annotations

import io
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.canonical.model            import USA_PROFILE                                # noqa: E402
from backend.feature_store              import (                                           # noqa: E402
    build_and_persist, FEATURE_REGISTRY, schema_fingerprint,
)
from backend.feature_store.feature_history  import read_snapshot                          # noqa: E402
from backend.feature_store.feature_validation import validate_snapshot                    # noqa: E402
from backend.ai import (                                                                   # noqa: E402
    feature_anomaly, feature_quality, feature_importance, feature_conflict,
)


OUT_SUMMARY   = _USA / "reports" / "feature_store_summary.json"
OUT_NARRATIVE = _USA / "reports" / "ai_feature_narrative.json"


def _stringify(v):
    if isinstance(v, dict):    return {k: _stringify(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [_stringify(x) for x in v]
    if isinstance(v, (date, datetime)): return v.isoformat()
    return v


def _as_dict(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _stringify(v) for k, v in asdict(obj).items()}
    return _stringify(obj)


def main() -> int:
    now = datetime.now(timezone.utc)
    asof = now.date()

    print("=" * 70)
    print("  AEGIS USA · Feature Store snapshot (Sprint 2.5 · USD)")
    print("=" * 70)
    print(f"  schema:   v{schema_fingerprint()}  ({len(FEATURE_REGISTRY)} features)")
    print(f"  asof:     {asof.isoformat()}")

    summary = build_and_persist(_ROOT, USA_PROFILE, asof=asof)
    print(f"  snapshot: {summary.get('path', '—')}")
    print(f"  rows:     {summary.get('n_rows', 0)} · features: {summary.get('n_features', 0)}")
    print(f"  verdict:  {summary.get('verdict', '?')} · null%: {summary.get('null_pct_overall', 0):.1%}")

    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text(json.dumps({
        "engine":  "feature_store",
        "version": "v1.0",
        "market":  "usa",
        "run_utc": now.isoformat(timespec="seconds"),
        **summary,
    }, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_SUMMARY.relative_to(_ROOT)}")

    df = read_snapshot(_ROOT, "usa", asof)
    if df is None or df.empty:
        print("  no snapshot to narrate — skipping AI agents")
        return 0

    val = validate_snapshot(df, FEATURE_REGISTRY)
    ai_out = {
        "anomaly":    feature_anomaly.run(df, "usa", asof),
        "quality":    feature_quality.run(val, "usa", asof),
        "importance": feature_importance.run(df, "usa", asof),
        "conflict":   feature_conflict.run(df, "usa", asof),
    }
    OUT_NARRATIVE.write_text(json.dumps({
        "engine":  "ai_feature_narrative",
        "version": "v1.0",
        "market":  "usa",
        "run_utc": now.isoformat(timespec="seconds"),
        "asof":    asof.isoformat(),
        "agents":  {k: _as_dict(v) for k, v in ai_out.items()},
    }, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_NARRATIVE.relative_to(_ROOT)}")
    for name, out in ai_out.items():
        print(f"    · {name:<12}: {out.headline[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
