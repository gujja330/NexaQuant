"""AEGIS USA · Macro & Intermarket Intelligence runner (Sprint 6.5, USD)."""
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

import pandas as pd                                                                          # noqa: E402

from backend.canonical.model              import USA_PROFILE                                # noqa: E402
from backend.feature_store                 import schema_fingerprint                        # noqa: E402
from backend.macro_intel                   import MacroIntelligenceEngine                  # noqa: E402
from backend.model_registry.registry      import stamp, register_model, ModelStatus         # noqa: E402
from backend.ai                          import macro_analyst                              # noqa: E402


REPORTS = _USA / "reports"

OUT_COMMOD   = REPORTS / "commodity_intelligence.json"
OUT_CURR     = REPORTS / "currency_intelligence.json"
OUT_BONDS    = REPORTS / "bond_intelligence.json"
OUT_CB       = REPORTS / "central_bank_state.json"
OUT_VOL      = REPORTS / "volatility_intelligence.json"
OUT_ROT      = REPORTS / "sector_rotation.json"
OUT_REGIME   = REPORTS / "macro_regime.json"
OUT_MATRIX   = REPORTS / "commodity_sector_matrix.json"
OUT_KG       = REPORTS / "macro_knowledge_graph.json"
OUT_NARR     = REPORTS / "ai_macro_narrative.json"

HIST_COMMOD  = REPORTS / "commodity_intelligence_history.parquet"
HIST_CURR    = REPORTS / "currency_intelligence_history.parquet"
HIST_BONDS   = REPORTS / "bond_intelligence_history.parquet"
HIST_REGIME  = REPORTS / "macro_regime_history.parquet"
HIST_ROT     = REPORTS / "sector_rotation_history.parquet"


def _stringify(v):
    if isinstance(v, dict):    return {k: _stringify(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [_stringify(x) for x in v]
    if isinstance(v, (date, datetime)): return v.isoformat()
    if hasattr(v, "value"):    return v.value
    return v


def _as_dict(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _stringify(v) for k, v in asdict(obj).items()}
    return _stringify(obj)


def _append_history(path: Path, rows: list[dict], keys: list[str]) -> tuple[Path, int]:
    if not rows: return path, 0
    path.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame(rows)
    if path.exists():
        try:
            df_old = pd.read_parquet(path)
            combined = pd.concat([df_old, df_new], ignore_index=True) \
                          .drop_duplicates(subset=keys, keep="last") \
                          .sort_values(keys).reset_index(drop=True)
            combined.to_parquet(path, index=False)
            return path, int(len(combined) - len(df_old))
        except Exception:
            df_new.to_parquet(path, index=False)
            return path, int(len(df_new))
    df_new.to_parquet(path, index=False)
    return path, int(len(df_new))


def main() -> int:
    now = datetime.now(timezone.utc)
    print("=" * 70); print("  AEGIS USA · Macro & Intermarket Intelligence v1 (Sprint 6.5, USD)"); print("=" * 70)

    model_id = "aegis.macro_intel.v1"
    register_model(_ROOT,
        model_id=model_id, engine="macro_intel",
        market="usa", version="1.0.0",
        feature_set_version=schema_fingerprint(),
        schema_version=schema_fingerprint(),
        approval_status=ModelStatus.EXPERIMENTAL,
        notes=f"registered by usa/macro_intel on {now.date().isoformat()}",
    )
    model_stamp = stamp(_ROOT, model_id)

    engine = MacroIntelligenceEngine(
        repo_root=_ROOT, market="usa",
        schema_fingerprint=schema_fingerprint(),
        feature_set_version=schema_fingerprint(),
        model_stamp=model_stamp,
    )
    r = engine.run(asof=now.date())

    print(f"  commodities:     {len(r.commodities)}   (labels: {[c.label for c in r.commodities[:3]]}...)")
    print(f"  currencies:      {len(r.currencies)}")
    print(f"  bonds:           {len(r.bonds)}   (labels: {[b.label for b in r.bonds[:3]]}...)")
    print(f"  volatility:      {r.volatility.regime if r.volatility else '—'} "
          f"(VIX={r.volatility.last if r.volatility else '—'})")
    print(f"  central bank:    {r.central_bank.bank if r.central_bank else '—'} · "
          f"cycle={r.central_bank.rate_cycle if r.central_bank else '—'} · "
          f"inversion={r.central_bank.inversion if r.central_bank else False}")
    if r.sector_rotation and r.sector_rotation.leaders:
        print(f"  sector leaders:  {[l.get('sector') for l in r.sector_rotation.leaders]}")
        print(f"  sector laggards: {[l.get('sector') for l in r.sector_rotation.laggards]}")
    print(f"  macro regime:    {r.macro_regime.primary_regime if r.macro_regime else '—'} · "
          f"secondary={r.macro_regime.secondary_regime if r.macro_regime else '—'} · "
          f"score={r.macro_regime.macro_score if r.macro_regime else 0.0}")
    print(f"  active impacts:  {len(r.active_impacts)}")
    if r.active_impacts:
        for imp in r.active_impacts:
            print(f"      · {imp.commodity} {imp.direction} → +{imp.positive_sectors[:2]} · -{imp.negative_sectors[:2]}")
    print(f"  knowledge graph: {len(r.knowledge_graph)} entries")

    REPORTS.mkdir(parents=True, exist_ok=True)
    common = {
        "engine":  engine.ENGINE_ID, "version": engine.ENGINE_VERSION,
        "market":  "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof":    r.asof.isoformat(),
        "currency": USA_PROFILE.currency,
        "model_stamp": model_stamp,
    }

    OUT_COMMOD.write_text(json.dumps({**common, "n": len(r.commodities),
        "commodities": [_as_dict(c) for c in r.commodities]}, indent=2, default=str), encoding="utf-8")
    OUT_CURR.write_text(json.dumps({**common, "n": len(r.currencies),
        "currencies": [_as_dict(c) for c in r.currencies]}, indent=2, default=str), encoding="utf-8")
    OUT_BONDS.write_text(json.dumps({**common, "n": len(r.bonds),
        "bonds": [_as_dict(b) for b in r.bonds]}, indent=2, default=str), encoding="utf-8")
    OUT_CB.write_text(json.dumps({**common, **(_as_dict(r.central_bank) if r.central_bank else {})},
                                     indent=2, default=str), encoding="utf-8")
    OUT_VOL.write_text(json.dumps({**common, **(_as_dict(r.volatility) if r.volatility else {})},
                                       indent=2, default=str), encoding="utf-8")
    OUT_ROT.write_text(json.dumps({**common, **(_as_dict(r.sector_rotation) if r.sector_rotation else {})},
                                       indent=2, default=str), encoding="utf-8")
    OUT_REGIME.write_text(json.dumps({**common, **(_as_dict(r.macro_regime) if r.macro_regime else {})},
                                          indent=2, default=str), encoding="utf-8")
    OUT_MATRIX.write_text(json.dumps({**common, "n_active_impacts": len(r.active_impacts),
        "active_impacts": [_as_dict(i) for i in r.active_impacts]}, indent=2, default=str), encoding="utf-8")
    OUT_KG.write_text(json.dumps({**common, "n_entries": len(r.knowledge_graph),
        "entries": [_as_dict(e) for e in r.knowledge_graph]}, indent=2, default=str), encoding="utf-8")

    # Append-only histories
    asof_iso = r.asof.isoformat()
    commod_rows = [{"asof": asof_iso, "market": "usa", **_as_dict(c)} for c in r.commodities]
    _, n_c = _append_history(HIST_COMMOD, commod_rows, ["market", "asof", "symbol"])

    curr_rows = [{"asof": asof_iso, "market": "usa", **_as_dict(c)} for c in r.currencies]
    _, n_cur = _append_history(HIST_CURR, curr_rows, ["market", "asof", "symbol"])

    bond_rows = [{"asof": asof_iso, "market": "usa", **_as_dict(b)} for b in r.bonds]
    _, n_b = _append_history(HIST_BONDS, bond_rows, ["market", "asof", "symbol"])

    if r.macro_regime:
        _, _ = _append_history(HIST_REGIME,
            [{"asof": asof_iso, "market": "usa", **_as_dict(r.macro_regime)}],
            ["market", "asof"])

    if r.sector_rotation and r.sector_rotation.sector_returns:
        rot_rows = [{"asof": asof_iso, "market": "usa", "sector": s, "return_pct": v}
                     for s, v in r.sector_rotation.sector_returns.items()]
        _, _ = _append_history(HIST_ROT, rot_rows, ["market", "asof", "sector"])

    print(f"  history appended: commodities+{n_c} · currencies+{n_cur} · bonds+{n_b}")

    ai = macro_analyst.run(r, "usa", r.asof)
    OUT_NARR.write_text(json.dumps({
        "engine":  "ai_macro_narrative", "version": "v1.0",
        "market":  "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof":    r.asof.isoformat(),
        "output":  _as_dict(ai),
    }, indent=2, default=str), encoding="utf-8")

    print(f"  ai headline: {ai.headline}")
    print(f"  wrote 10 daily JSONs + 5 append-only history parquets under usa/reports/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
