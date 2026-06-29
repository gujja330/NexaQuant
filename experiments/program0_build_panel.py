# experiments/program0_build_panel.py
"""
PROGRAM 0 — efficient PIT panel builder for the EXPANDED dataset (deeper price history + 208 SEC names).

core/usa_research.build_panel() calls normalize_one() per (date,symbol), which re-parses each SEC JSON every
call — fine for 74x21, but ~100k re-parses on the expanded data. This builder parses each filing ONCE into a
concept timeline, then evaluates PIT fundamentals at every rebalance from memory. It MIRRORS normalize_one's
exact formulas (so results stay faithful) and writes the SAME panel parquet the LOCKED analysis engine reads
(core/usa_research.py is untouched — run `python -m core.usa_research` afterwards for the analysis).

Survivorship note: deeper history on the CURRENT universe is survivorship-biased (delisted names absent) —
flagged, to be addressed later with a survivorship-free source. Run:  python -m experiments.program0_build_panel
"""
import sys, glob, json, re, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from core.market_adapter import USAAdapter
from core.usa_fundamentals import RAW
from core.usa_research import PANEL, FACTORS, HORIZONS, CAD

YEARS_BACK = 14                                   # cap window to the SEC era (bounds cost, keeps power)
ANNUAL = re.compile(r"CY\d{4}")


def load_timeline(path):
    g = json.loads(path.read_text()).get("facts", {}).get("us-gaap", {})
    def u(c, unit="USD"): return g.get(c, {}).get("units", {}).get(unit, [])
    rev = u("Revenues") or u("RevenueFromContractWithCustomerExcludingAssessedTax")
    ann = lambda items: [x for x in items if ANNUAL.fullmatch(str(x.get("frame", "")))]
    return {"rev": ann(rev), "ni": ann(u("NetIncomeLoss")),
            "eq": u("StockholdersEquity"), "li": u("Liabilities")}


def _annual_asof(items, today):
    out = [x for x in items if x.get("filed", "9") <= today]
    return sorted(out, key=lambda x: x["end"], reverse=True)


def _latest_asof(items, today):
    out = [x for x in items if x.get("filed", "9") <= today]
    return max(out, key=lambda x: x["filed"]) if out else None


def fundamentals_asof(tl, today):
    rev, ni = _annual_asof(tl["rev"], today), _annual_asof(tl["ni"], today)
    eq, li = _latest_asof(tl["eq"], today), _latest_asof(tl["li"], today)
    row = {}
    if ni and eq and eq["val"]:
        row["f_roe"] = round(100 * ni[0]["val"] / eq["val"], 1)
    if ni and rev and rev[0]["val"]:
        row["f_net_margin"] = round(100 * ni[0]["val"] / rev[0]["val"], 1)
    if li and eq and eq["val"]:
        row["f_debt_to_equity"] = round(li["val"] / eq["val"], 2)
    if len(rev) >= 2 and rev[1]["val"]:
        row["f_rev_growth_yoy"] = round(100 * (rev[0]["val"] / rev[1]["val"] - 1), 1)
    return row


def main():
    adp = USAAdapter()
    closes, _, _, _, idx, vix, _ = adp.get_market_data()
    covered = [Path(f).stem for f in glob.glob(str(RAW / "*.json")) if Path(f).stem != "cik_map"]
    covered = [c for c in covered if c in closes.columns]
    closes = closes[covered]
    idx = idx.reindex(closes.index).ffill()
    vix = vix.reindex(closes.index).ffill() if vix is not None else None
    vix_med = float(vix.median()) if vix is not None else None
    timelines = {s: load_timeline(RAW / f"{s}.json") for s in covered}   # parse each JSON ONCE
    sect = {s: adp.get_sector(s) for s in covered}

    start = max(126, len(closes) - YEARS_BACK * 252)
    rows = []
    for i in range(start, len(closes) - 63, CAD):
        dt = str(closes.index[i].date())
        bull = int(idx.iloc[i] > idx.iloc[max(0, i - 200):i].mean())
        highvol = int(vix.iloc[i] > vix_med) if vix is not None else -1
        fwd = {h: (closes.iloc[i + h] / closes.iloc[i] - 1) if i + h < len(closes) else None for h in HORIZONS}
        for s in covered:
            if pd.isna(closes[s].iloc[i]):
                continue
            f = fundamentals_asof(timelines[s], dt)
            if not f:
                continue
            row = {"date": dt, "symbol": s, "sector": sect[s], "bull": bull, "highvol": highvol}
            row.update({k: f.get(k) for k, _ in FACTORS})
            for h in HORIZONS:
                row[f"fwd{h}"] = float(fwd[h][s]) if (fwd[h] is not None and s in fwd[h] and pd.notna(fwd[h][s])) else np.nan
            rows.append(row)
    df = pd.DataFrame(rows)
    PANEL.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PANEL)
    print(f"  EXPANDED panel: {len(df)} rows · {df['symbol'].nunique()} names · {df['date'].nunique()} dates "
          f"· {df['date'].min()}..{df['date'].max()} -> {PANEL.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
