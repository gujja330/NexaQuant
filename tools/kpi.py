# tools/kpi.py
"""
AEGIS Research KPI dashboard — the CEO view: current vs target, one screen. NOT governance prose; computed
live from the registries + leaderboard + actual cached data. Run:  python tools/kpi.py
"""
import csv, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "markets" / "research"
OUT = RES / "RESEARCH_KPI.md"


def _rows(p):
    f = RES / p
    return list(csv.DictReader(f.open())) if f.exists() else []


def price_years():
    import pandas as pd
    files = glob.glob(str(ROOT / "data" / "raw" / "usa" / "*_D1.parquet"))
    if not files:
        return 0, 0
    spans = []
    for f in files[:60]:                                  # sample for speed
        df = pd.read_parquet(f)
        if len(df) > 1:
            spans.append((df.index.max() - df.index.min()).days / 365.25)
    return (round(min(spans), 1), round(max(spans), 1)) if spans else (0, 0)


def main():
    lb = _rows("LEADERBOARD.csv")
    ds = _rows("registry/DATASET_REGISTRY.csv")
    feat = _rows("registry/FEATURE_CATALOG.csv")
    exp = _rows("registry/EXPERIMENT_REGISTRY.csv")
    sec = len(glob.glob(str(ROOT / "markets" / "usa" / "raw" / "fundamentals" / "*.json"))) - 1  # minus cik_map
    promoted = sum(1 for r in lb if r["status"] in ("kept", "promoted"))
    investigating = sum(1 for r in lb if r["status"] == "investigate")
    pmin, pmax = price_years()

    kpis = [
        ("Datasets ready", sum(1 for r in ds if r["status"] == "ready"), 20),
        ("Datasets registered", len(ds), 40),
        ("Features catalogued", len(feat), 200),
        ("Experiments logged", len(lb), 250),
        ("Experiments registered", len(exp), 250),
        ("Promoted", promoted, 20),
        ("Investigating", investigating, 10),
        ("SEC coverage (names)", sec, 1000),
        ("Price history (yrs, min-max)", f"{pmin}-{pmax}", "20+ avg"),
    ]
    L = ["# AEGIS Research KPIs (CEO dashboard)", "",
         "Auto-computed from registries + leaderboard + cached data — `python tools/kpi.py`. "
         "Targets are the long-term build-out, not commitments.", "",
         "| KPI | Current | Target |", "|---|--:|--:|"]
    for name, cur, tgt in kpis:
        L.append(f"| {name} | {cur} | {tgt} |")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  wrote {OUT.relative_to(ROOT)}")
    for name, cur, tgt in kpis:
        print(f"  {name:32s} {str(cur):>10} / {tgt}")


if __name__ == "__main__":
    main()
