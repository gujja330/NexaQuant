"""R3-G Wave 1C · RUNNER · CEO 2026-09-08.

Runs the full contender matrix over the multi-horizon exit targets and
emits one verdict per sequence model per target: KEEP or KILL.

> "If the Transformer/GRU/TCN adds nothing, we kill it. If a simpler model
>  wins, we keep the simpler model."

Two fold sets are evaluated for every target:

  ticker-disjoint  a name never appears in train and test
  date-disjoint    an entry DATE never appears in both

The second exists because this cohort has 547 episodes across 15 dates.
Ticker-disjoint folds cannot stop a model learning "August 11th was bad"
and reporting it as skill. If a model's advantage evaporates under
date-disjoint folds, it was reading the calendar.

Trial accounting is carried so the family can be corrected: every
(target x model x fold-set) is one counted comparison.

RESEARCH ONLY · writes one report, touches no engine.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.wave1c.v1"
FAMILY = "R3G_SEQUENCE_WAVE1C"


def run_market(root: Path, market: str) -> dict:
    from backend.research.ml_discovery import sequence_models as sm

    ds = sm.build_dataset(root, market)
    eps, seqs = ds["episodes"], ds["sequences"]
    conc = sm.concentration_report(eps)
    allow_seq = len(eps) >= sm.MIN_EPISODES_SEQUENCE

    rep = {
        "schema_version": SCHEMA_VERSION,
        "experiment_family": FAMILY,
        "status": "RESEARCH ONLY · no production rule · R2 exits unchanged",
        "market": market.lower(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": sm.WINDOW,
        "sequence_features": sm.SEQ_FEATURES,
        "concentration": conc,
        "sequence_gate": {
            "min_episodes": sm.MIN_EPISODES_SEQUENCE,
            "n_episodes": len(eps),
            "allowed": allow_seq,
            "rationale": ("a network with more parameters than episodes "
                          "fits them perfectly and learns nothing · the "
                          "parameter count is reported beside the episode "
                          "count so the ratio is visible"),
        },
    }
    if len(eps) < 60:
        rep["refusal"] = ("NO MODELS FITTED · %d episodes with a real stop"
                          % len(eps))
        return rep

    tgts = sm.targets_for(eps)
    tick_folds = sm._folds_by([e["ticker"] for e in eps])
    date_folds = sm._folds_by([e["entry_date"] for e in eps])

    results, trials = {}, 0
    for name, y in tgts.items():
        pos = sum(y)
        if pos < 15 or (len(y) - pos) < 15:
            results[name] = {"skipped": "class too small (%d/%d)"
                                        % (pos, len(y))}
            continue
        entry = {"event_rate_pct": round(pos / len(y) * 100, 1), "n": len(y)}
        for fold_name, folds in (("ticker_disjoint", tick_folds),
                                 ("date_disjoint", date_folds)):
            if not folds:
                entry[fold_name] = {"skipped": "no usable folds"}
                continue
            entry[fold_name] = sm.run_target(seqs, eps, y, folds, allow_seq)
            trials += len(sm.MODELS)
        results[name] = entry

    rep["targets"] = results
    rep["trial_accounting"] = {
        "n_comparisons": trials,
        "note": ("each (target x model x fold-set) is one counted "
                 "comparison · corrected before any promotion claim"),
    }

    # Headline · does ANY sequence model survive on ANY target, on BOTH
    # fold sets? That is the only result that would justify keeping one.
    survivors = []
    for tname, t in results.items():
        if "ticker_disjoint" not in t or "date_disjoint" not in t:
            continue
        for mdl in ("tcn", "gru", "transformer"):
            vt = t["ticker_disjoint"].get("sequence_verdicts", {}).get(mdl, "")
            vd = t["date_disjoint"].get("sequence_verdicts", {}).get(mdl, "")
            if vt.startswith("KEEP") and vd.startswith("KEEP"):
                survivors.append({"target": tname, "model": mdl})
    rep["sequence_survivors_both_fold_sets"] = survivors
    rep["verdict"] = ("SEQUENCE MODELS ADD VALUE" if survivors
                      else "KILL SEQUENCE MODELS · no target survives both "
                           "fold sets against LightGBM and baselines")
    return rep


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "ml_discovery"
         / f"wave1c_sequence_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = (root / "reports" / "research" / "ml_discovery"
         / f"wave1c_sequence_{market.lower()}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3-G Wave 1C sequence models")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = run_market(root, m)
        emit(root, rep)
        c = rep["concentration"]
        print(f"wave1c:{m} · episodes {c['n_episodes']} · tickers "
              f"{c['n_tickers']} · dates {c['n_dates']} · top-date share "
              f"{c['top_date_share_pct']}% · seq_allowed "
              f"{rep['sequence_gate']['allowed']}")
        if rep.get("refusal"):
            print(f"    {rep['refusal']}")
        else:
            print(f"    {rep['verdict']}")
            for s in rep["sequence_survivors_both_fold_sets"]:
                print(f"      SURVIVOR · {s['model']} on {s['target']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
