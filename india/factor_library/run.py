"""AEGIS India · Factor Library runner (Sprint 7.5).

Reads Sprint 6.5 macro outputs from reports/ and emits ONE row per factor:
  reports/factor_library.json        (today's daily snapshot)
  reports/factor_library.parquet     (today's daily table)
  reports/factor_library_history.parquet   (append-only)

Free-data substrate only — piggy-backs on the Sprint 6.5 readers.
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

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd

from backend.factor_library import build_factor_library, ENGINE_ID, ENGINE_VERSION
from backend.feature_store import schema_fingerprint
from backend.model_registry.registry import stamp, register_model, ModelStatus
from backend.persistence import append_snapshot_row

REPORTS = _ROOT / "reports"
CFG     = _ROOT / "configs" / "factor_library_config.yaml"
OUT_JSON = REPORTS / "factor_library.json"
OUT_PARQUET = REPORTS / "factor_library.parquet"
OUT_HISTORY = REPORTS / "factor_library_history.parquet"


def _as_dict(obj):
    if obj is None: return None
    if hasattr(obj, "__dataclass_fields__"):
        d = asdict(obj)
        for k, v in list(d.items()):
            if hasattr(v, "isoformat"): d[k] = v.isoformat()
        return d
    return obj


def main() -> int:
    now = datetime.now(timezone.utc)
    print(f"[AEGIS India · Factor Library · {now.isoformat(timespec='seconds')}]")

    result = build_factor_library(
        market="india", reports_dir=REPORTS,
        asof=date.today(), config_path=CFG,
    )

    register_model(_ROOT,
        model_id=ENGINE_ID, engine="factor_library",
        market="india", version=ENGINE_VERSION,
        feature_set_version=schema_fingerprint(),
        schema_version=schema_fingerprint(),
        approval_status=ModelStatus.EXPERIMENTAL,
        notes="registered by india/factor_library on " + date.today().isoformat(),
    )
    model_stamp = stamp(_ROOT, ENGINE_ID)

    factors_dicts = [_as_dict(f) for f in result.factors]

    payload = {
        "engine": result.engine, "version": result.version,
        "market": result.market,
        "run_utc": now.isoformat(timespec="seconds"),
        "asof": result.asof.isoformat(),
        "currency": "INR",
        "n_factors": result.n_factors,
        "factors": factors_dicts,
        "model_stamp": model_stamp,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    df = pd.DataFrame(factors_dicts)
    if not df.empty:
        df["asof"] = result.asof.isoformat()
        df["market"] = "india"
        df["run_utc"] = now.isoformat(timespec="seconds")
        df.to_parquet(OUT_PARQUET, index=False)

        try:
            if OUT_HISTORY.exists():
                existing = pd.read_parquet(OUT_HISTORY)
                keep = ~((existing["market"] == "india") & (existing["asof"] == result.asof.isoformat()))
                combined = pd.concat([existing[keep], df], ignore_index=True)
            else:
                combined = df
            combined = combined.sort_values(["asof", "factor"], kind="stable").reset_index(drop=True)
            combined.to_parquet(OUT_HISTORY, index=False)
            print(f"  history rows: {len(combined)}")
        except Exception as exc:
            print(f"  history append warning (non-fatal): {exc}")

    print(f"  wrote {OUT_JSON.relative_to(_ROOT)}")
    print(f"  wrote {OUT_PARQUET.relative_to(_ROOT)}")
    print(f"  n_factors={result.n_factors} confident={sum(1 for f in result.factors if f.confidence >= 1.0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
