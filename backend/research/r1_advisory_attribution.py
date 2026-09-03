"""V2 §18 · R1 advisory attribution + R1 vs R2 early-warning study.

For every R1 daily pick historically preserved, compare:
  - R1's pick date · rank · signal
  - Was the same ticker eventually picked by R2?
  - How many days later?
  - Did R1 provide EARLY WARNING (positive OR negative) that R2 missed?

Reports:
  reports/research/r1_advisory_attribution/{market}.json

Governance: R1 stays advisory · this report does NOT alter production.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path


def _load_r1_history(root: Path, market: str) -> dict[str, list[str]]:
    """{date: [tickers]} from any preserved R1 archive."""
    out: dict[str, list[str]] = {}
    # Standard R1 daily archive path (if present)
    for base in (root / "data" / "r1_daily_archive",
                 root / "reports" / "r1_archive" / market):
        if not base.exists(): continue
        for f in sorted(base.glob("*.csv")):
            try:
                import pandas as pd
                df = pd.read_csv(f)
                date_str = f.stem
                tickers = [str(t).upper().split(".",1)[0]
                          for t in df.get("ticker", []) if str(t).strip()]
                if tickers: out.setdefault(date_str, []).extend(tickers)
            except Exception:
                pass
    return out


def _load_r2_registry_by_date(root: Path, market: str) -> dict[str, list[str]]:
    """{date: [R2 tickers opened]}."""
    import pandas as pd
    p = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if not p.exists(): return {}
    try:
        df = pd.read_parquet(p)
        df = df[df["runner"] == "R2"]
        out: dict[str, list[str]] = {}
        for _, r in df.iterrows():
            ed = str(r.get("entry_date","")) or ""
            t = str(r.get("ticker","")).upper()
            if ed: out.setdefault(ed, []).append(t)
        return out
    except Exception:
        return {}


def analyze(root: Path, market: str) -> dict:
    r1_hist = _load_r1_history(root, market)
    r2_hist = _load_r2_registry_by_date(root, market)

    early_warnings: list[dict] = []
    r1_only: list[dict] = []
    both_agree: list[dict] = []

    for r1_date, tickers in r1_hist.items():
        for t in tickers:
            # Find R2's earliest open of this ticker
            r2_dates = sorted([d for d, ts in r2_hist.items() if t in ts])
            if not r2_dates:
                r1_only.append({"ticker": t, "r1_date": r1_date})
                continue
            first_r2 = r2_dates[0]
            try:
                days_gap = (date.fromisoformat(first_r2) - date.fromisoformat(r1_date)).days
            except Exception:
                days_gap = None
            if days_gap is not None and days_gap > 0:
                early_warnings.append({
                    "ticker": t, "r1_date": r1_date, "r2_date": first_r2,
                    "days_r1_before_r2": days_gap,
                })
            else:
                both_agree.append({
                    "ticker": t, "r1_date": r1_date, "r2_date": first_r2,
                    "days_gap": days_gap,
                })

    payload = {
        "market": market,
        "n_r1_days_archived": len(r1_hist),
        "n_r1_tickers_total": sum(len(v) for v in r1_hist.values()),
        "n_r2_days_open": len(r2_hist),
        "n_early_warnings_r1_before_r2": len(early_warnings),
        "n_r1_only": len(r1_only),
        "n_both_agree": len(both_agree),
        "early_warnings_sample": early_warnings[:20],
        "governance_note": (
            "R1 = RETIRED_ADVISORY · this attribution is DIAGNOSTIC · "
            "does NOT authorize R1 to acquire production authority. "
            "'Early warning' is an information observation, not a signal to act on."
        ),
        "data_gap_note": (
            "If data/r1_daily_archive/ is empty, this report shows n=0 for "
            "all counts. R1 daily archive is a Week-3 Sprint A deliverable per "
            "docs/AEGIS/SPRINT_A_R1_R2_R3_PARALLEL_DEVELOPMENT.md."
        ),
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out_dir = root / "reports" / "research" / "r1_advisory_attribution"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{market}.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    return payload


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    args = ap.parse_args()
    root = Path(args.root)
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = analyze(root, m)
        print(f"[r1-attribution] {m} · r1_days={r['n_r1_days_archived']} · early_warnings={r['n_early_warnings_r1_before_r2']} · r2_days={r['n_r2_days_open']}")


if __name__ == "__main__":
    main()
