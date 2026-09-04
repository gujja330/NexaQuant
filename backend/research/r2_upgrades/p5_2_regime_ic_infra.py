"""P5.2 · Regime-conditional Ensemble Weights · ENGINEERING INFRASTRUCTURE ONLY.

Builds the per-regime IC (Information Coefficient) accumulator so that when
each regime bucket reaches n≥30 samples (V2 §P5.2 acceptance criterion), the
weights can be computed.

CEO 2026-09-05: engineering permitted · evidence gate absolute.
Fall back to global weights when any bucket has n<30.

Reads:
  reports/research/opportunity_registry.jsonl (closed R2 positions + regime)
  reports/research/macro_regime_history.parquet (regime label per date)

Writes (research-only):
  reports/research/r2_upgrades/p5_2_regime_ic_infra_{market}.json
"""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


MIN_N_PER_BUCKET = 30    # V2 §P5.2 · locked


def _load_regime_label(root: Path, market: str, asof: str) -> str | None:
    """Return regime label at asof · or None if missing."""
    try:
        import pandas as pd
        p = (root / market / "reports" / "macro_regime_history.parquet"
             if market.lower() == "usa"
             else root / "reports" / "macro_regime_history.parquet")
        if not p.exists(): return None
        df = pd.read_parquet(p)
        if "asof" not in df.columns or "regime" not in df.columns: return None
        df["asof_d"] = pd.to_datetime(df["asof"]).dt.date
        target = pd.Timestamp(asof).date()
        matches = df[df["asof_d"] <= target]
        if matches.empty: return None
        return str(matches.iloc[-1]["regime"])
    except Exception:
        return None


def build_per_regime_ic(root: Path, market: str) -> dict:
    """Compute IC per regime bucket · report readiness for P5.2 wiring."""
    import pandas as pd
    reg_p = root / "reports" / "research" / "opportunity_registry.jsonl"
    if not reg_p.exists():
        return {"status": "NO_REGISTRY"}

    # Extract closed R2 with initial score + realized return
    per_regime_pairs: dict[str, list[tuple[float, float]]] = defaultdict(list)
    unknown_regime_count = 0
    total_r2_closed = 0
    with open(reg_p, "r", encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception: continue
            if d.get("runner") != "R2": continue
            if str(d.get("market","")).lower() != market.lower(): continue
            if d.get("status") != "CLOSED": continue
            total_r2_closed += 1
            entry = d.get("created_date")
            exit_d = d.get("closed_date")
            score = d.get("initial_score")
            if not entry or not exit_d or score is None: continue
            # Realized return · need entry+exit prices
            try:
                from backend.research._paths import price_parquet_path
                pth = price_parquet_path(root, market, str(d.get("ticker","")).upper().split(".",1)[0])
                if not pth or not pth.exists(): continue
                df = pd.read_parquet(pth)
                df.index = pd.to_datetime(df.index)
                ent_ts = pd.Timestamp(entry); ext_ts = pd.Timestamp(exit_d)
                ent_slice = df[df.index >= ent_ts]
                ext_slice = df[df.index >= ext_ts]
                if ent_slice.empty or ext_slice.empty: continue
                ent_price = float(ent_slice.iloc[0]["close"])
                ext_price = float(ext_slice.iloc[0]["close"])
                if ent_price <= 0: continue
                ret = (ext_price / ent_price - 1.0) * 100.0
            except Exception:
                continue
            regime = _load_regime_label(root, market, entry) or "UNKNOWN"
            if regime == "UNKNOWN": unknown_regime_count += 1
            per_regime_pairs[regime].append((float(score), ret))

    # Compute IC per regime · Pearson corr between score and realized return
    def _pearson(pairs):
        if len(pairs) < 3: return None
        import math
        xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
        mx = sum(xs)/len(xs); my = sum(ys)/len(ys)
        cov = sum((x-mx)*(y-my) for x,y in zip(xs,ys)) / max(1, len(pairs)-1)
        sx = math.sqrt(sum((x-mx)**2 for x in xs)/max(1, len(xs)-1))
        sy = math.sqrt(sum((y-my)**2 for y in ys)/max(1, len(ys)-1))
        if sx == 0 or sy == 0: return None
        return cov / (sx * sy)

    per_regime = {}
    for regime, pairs in per_regime_pairs.items():
        ic = _pearson(pairs)
        per_regime[regime] = {
            "n": len(pairs),
            "ic_pearson": round(ic, 4) if ic is not None else None,
            "meets_p52_gate_n_ge_30": len(pairs) >= MIN_N_PER_BUCKET,
        }

    # Overall readiness · P5.2 requires ALL populated buckets to be n≥30
    ready = all(v["meets_p52_gate_n_ge_30"] for v in per_regime.values()) if per_regime else False

    return {
        "status": "OK",
        "market": market,
        "total_r2_closed_scanned": total_r2_closed,
        "n_with_unknown_regime": unknown_regime_count,
        "min_n_per_bucket_gate": MIN_N_PER_BUCKET,
        "per_regime": per_regime,
        "p52_wiring_ready": ready,
        "if_not_ready": "fall back to global weights per V2 §P5.2 (DATA_WAIT)",
        "governance": ("V2 §P5.2 · ENGINEERING INFRA ONLY · IC computer built · "
                        "wiring to R2 ensemble weights DEFERRED until per-bucket n≥30 · "
                        "R2 production weights NEVER modified by this module"),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def emit_report(root: Path, market: str) -> Path:
    r = build_per_regime_ic(root, market)
    out = root / "reports" / "research" / "r2_upgrades" / f"p5_2_regime_ic_infra_{market}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    return out
