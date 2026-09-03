"""V2 §19 · Composite daily per-ticker loop.

Reads today's per-runner scores + trailing IC/n stats · computes composite
per ticker · writes reports/research/composite/composite_signals_{market}.json.

Sheet 06_Composite_Signals reads that JSON.

Governance: shadow only · no Registry writes · no P&L authority · declared
in configs/aegis_runner_registry.yaml as workbook_visibility=shadow.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def _load_r2_scores(root: Path, market: str) -> dict[str, dict]:
    """{ticker: {r2_score, rank, calibrated_confidence}} from today's recs."""
    p = ((root / "usa" / "reports" / "recommendations_v3.json") if market == "usa"
         else (root / "reports" / "recommendations_v3.json"))
    if not p.exists(): return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for r in (d.get("recommendations") or []):
        t = str(r.get("ticker", "")).upper().split(".", 1)[0]
        out[t] = {
            "r2_score": r.get("ensemble_score"),
            "rank": r.get("rank"),
            "calibrated_confidence": r.get("calibrated_confidence"),
            "sector": r.get("sector"),
        }
    return out


def _load_r1_scores(root: Path, market: str) -> dict[str, float]:
    """R1 daily picks · from data/aegis_today.csv when preserved."""
    import pandas as pd
    for p in (root / f"data/aegis_today_{market}.csv",
              root / "data/aegis_today.csv"):
        if p.exists():
            try:
                df = pd.read_csv(p)
                col = "recommendation" if "recommendation" in df.columns else "action"
                out = {}
                for _, r in df.iterrows():
                    t = str(r.get("ticker", "") or "").upper().split(".", 1)[0]
                    action = str(r.get(col, "") or "").upper()
                    score = 0.5 if "BUY" in action else (-0.5 if "SELL" in action else 0.0)
                    out[t] = score
                return out
            except Exception:
                pass
    return {}


def _load_r3_shadow_today(root: Path, market: str, asof: str) -> dict[str, float]:
    """R3 shadow picks for today · from ledger."""
    p = root / "reports" / "research" / "r3" / "shadow_ledger.jsonl"
    if not p.exists(): return {}
    out = {}
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line: continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("market") != market: continue
            if o.get("asof") != asof: continue
            t = str(o.get("ticker", "")).upper().split(".", 1)[0]
            out[t] = float(o.get("r3_calibrated_p", 0.5)) - 0.5   # center to 0
    return out


def _trailing_ic_and_n(root: Path, market: str) -> tuple[dict, dict]:
    """Trailing IC per runner and closed-trade count per runner.

    Uses Outcome Dataset as source. Placeholder IC of 0.05 for R1/R2 with n
    computed real; R3 IC=0.05 with n=count of shadow ledger picks.
    """
    import pandas as pd
    ic = {"R1": 0.05, "R2": 0.05, "R3": 0.05}
    n = {"R1": 0, "R2": 0, "R3": 0}
    od = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if od.exists():
        try:
            df = pd.read_parquet(od)
            for r in ("R1", "R2"):
                sub = df[(df["runner"] == r) & (df["is_administrative_exit"] != True)
                         & df["realized_return_pct"].notna()]
                n[r] = int(len(sub))
        except Exception:
            pass
    ledger = root / "reports" / "research" / "r3" / "shadow_ledger.jsonl"
    if ledger.exists():
        with ledger.open("r", encoding="utf-8", errors="replace") as fh:
            n["R3"] = sum(1 for l in fh
                          if l.strip() and json.loads(l).get("market") == market)
    return ic, n


def run_composite_daily(root: Path, market: str, asof: str | None = None) -> dict:
    from backend.recommendation.composite import compute_composite_score
    asof = asof or datetime.now().strftime("%Y-%m-%d")

    r2_map = _load_r2_scores(root, market)
    r1_map = _load_r1_scores(root, market)
    r3_map = _load_r3_shadow_today(root, market, asof)
    trailing_ic, trailing_n = _trailing_ic_and_n(root, market)

    all_tickers = set(r2_map) | set(r1_map) | set(r3_map)
    rows = []
    for t in sorted(all_tickers):
        runner_scores = {
            "R1": float(r1_map.get(t, 0.0) or 0.0),
            "R2": float((r2_map.get(t) or {}).get("r2_score") or 0.0),
            "R3": float(r3_map.get(t, 0.0) or 0.0),
        }
        result = compute_composite_score(runner_scores, trailing_ic, trailing_n, root=root)
        r2meta = r2_map.get(t, {}) or {}
        rows.append({
            "ticker": t,
            "sector": r2meta.get("sector"),
            "R1_score": runner_scores["R1"],
            "R2_score": runner_scores["R2"],
            "R3_score": runner_scores["R3"],
            "R2_rank": r2meta.get("rank"),
            "R2_calibrated_confidence": r2meta.get("calibrated_confidence"),
            **result,
        })

    out_dir = root / "reports" / "research" / "composite"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "market": market, "asof": asof,
        "n_tickers": len(rows),
        "n_r1_active": len(r1_map),
        "n_r2_active": len(r2_map),
        "n_r3_shadow": len(r3_map),
        "trailing_ic": trailing_ic,
        "trailing_n": trailing_n,
        "signals": rows,
        "governance_note": (
            "Shadow only · workbook_visibility=shadow · never Registry / P&L "
            "authority. R3 Trust_Weight=0 until trailing_closed_trades(R3)>=50 "
            "(admission gate per V2 §19)."
        ),
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (out_dir / f"composite_signals_{market}.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    return payload


def main():
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    ap.add_argument("--asof", default=None)
    args = ap.parse_args()
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = run_composite_daily(_ROOT, m, args.asof)
        print(f"[composite] {m} · n_tickers={r['n_tickers']} · admissions={r['signals'][0].get('admissions') if r['signals'] else 'no rows'}")


if __name__ == "__main__":
    main()
