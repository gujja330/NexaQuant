# experiments/rc005_insider.py
"""
RC005 — Program 1 (Alternative Data), insider trading via SEC Form 4. A genuinely DIFFERENT information
source from Program A's static ratios (which Program 0 showed are flat). Open-market insider PURCHASES
(transaction code P) are the literature's cleanest insider signal; sales (S) are noisy.

PIT: the SEC `filed` date (insiders must file within ~2 business days). Pipeline mirrors the others:
ingest raw -> cache -> derived feature (net open-market buy, 90d) -> research gate (cross-sectional IC vs
forward 63d, non-overlap IR, confidence) -> publish via the automation harness. Engine helpers imported
from the LOCKED core (parameterize, don't rewrite).

SCOPE NOTE: submissions "recent" covers only ~1-2y for active filers (deep history needs shard traversal),
so this is a PILOT — expect Low confidence, like the 2y price baseline. Deepening via shards / full-index is
the documented follow-up before any verdict is trusted.

Run:  python -m experiments.rc005_insider --probe         # validate parsing on a few names
      python -m experiments.rc005_insider --run [--cap N]  # ingest (cached) + gate + publish
"""
import sys, json, time, urllib.request, warnings
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
warnings.simplefilter("ignore")
from core.market_adapter import USAAdapter
from core.usa_research import summarize, stride_for, CAD
from run_experiment import publish, confidence

UA = {"User-Agent": "AEGIS Research aegis-research@example.com"}
CIK_MAP = ROOT / "markets" / "usa" / "raw" / "fundamentals" / "cik_map.json"
RAWI = ROOT / "markets" / "usa" / "raw" / "insiders"
HOLD = 63


def _get(url, raw=False):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
    return r if raw else json.loads(r)


def _form4_from_block(rec, since):
    out = []
    for i, form in enumerate(rec.get("form", [])):
        if form == "4":
            fd = rec["filingDate"][i]
            if since and fd < since:
                continue
            doc = rec["primaryDocument"][i].split("/")[-1]            # raw XML = drop the xsl.../ prefix
            out.append((fd, rec["accessionNumber"][i].replace("-", ""), doc))
    return out


def list_form4(cik, cap):
    """Recent-only Form 4 filings (PILOT path)."""
    sub = _get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    return _form4_from_block(sub["filings"]["recent"], None)[:cap]


def gather_form4(cik, since, cap=300, max_shards=6):
    """DEEP Form 4 history: recent block + older shard files (bounded), filed >= `since`. Newest first.
    Shards/docs are capped so the universe-wide ingest stays tractable (hours -> ~under an hour)."""
    sub = _get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    out = _form4_from_block(sub["filings"]["recent"], since)
    for sh in sub["filings"].get("files", [])[:max_shards]:
        try:
            out += _form4_from_block(_get(f"https://data.sec.gov/submissions/{sh['name']}"), since)
            time.sleep(0.1)
        except Exception:
            pass
    return sorted(out, reverse=True)[:cap]


def parse_form4(cik, acc, xmlname):
    """Per-filing net open-market value: + for purchases (P), - for sales (S); + officer-buy flag."""
    try:
        xml = _get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{xmlname}", raw=True)
        root = ET.fromstring(xml)
    except Exception:
        return None
    rel = root.find(".//reportingOwner/reportingOwnerRelationship")
    officer = bool(rel is not None and (rel.findtext("isOfficer") in ("1", "true")))
    buy = sell = 0.0
    for tx in root.findall(".//nonDerivativeTransaction"):
        code = tx.findtext("transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        try:
            sh = float(tx.findtext("transactionAmounts/transactionShares/value"))
            px = float(tx.findtext("transactionAmounts/transactionPricePerShare/value") or 0)
        except (TypeError, ValueError):
            continue
        val = sh * px
        if code == "P":
            buy += val
        else:
            sell += val
    return {"buy": buy, "sell": sell, "officer_buy": int(officer and buy > 0)}


def ingest(symbols, cap, deep=False, since="2012-01-01"):
    tm = json.loads(CIK_MAP.read_text())
    RAWI.mkdir(parents=True, exist_ok=True)
    done = 0
    for s in symbols:
        out_p = RAWI / f"{s}.json"
        if out_p.exists():                              # resume-friendly (re-ingest = clear the dir first)
            done += 1; continue
        cik = tm.get(s)
        if not cik:
            continue
        recs = []
        try:
            filings = gather_form4(cik, since) if deep else list_form4(cik, cap)
            for filed, acc, doc in filings:
                p = parse_form4(cik, acc, doc)
                time.sleep(0.1)
                if p and (p["buy"] or p["sell"]):
                    recs.append({"filed": filed, **p})
        except Exception:
            pass
        out_p.write_text(json.dumps(recs))
        done += 1
        if done % 20 == 0:
            print(f"  ingested {done}/{len(symbols)} names...", flush=True)
    return done


def gate():
    adp = USAAdapter()
    closes = adp.get_market_data()[0]
    files = list(RAWI.glob("*.json"))
    # net open-market buy value over trailing 90d, per name, at each monthly rebalance
    insiders = {}
    for f in files:
        recs = json.loads(f.read_text())
        if recs:
            insiders[f.stem] = pd.DataFrame(recs)
    covered = [s for s in insiders if s in closes.columns]
    rows = []
    for i in range(126, len(closes) - HOLD, CAD):
        dt = closes.index[i]
        dt_s = str(dt.date())
        lo = str((dt - pd.Timedelta(days=90)).date())
        fwd = (closes.iloc[i + HOLD] / closes.iloc[i] - 1)
        for s in covered:
            if pd.isna(closes[s].iloc[i]) or pd.isna(fwd[s]):
                continue
            df = insiders[s]
            w = df[(df["filed"] > lo) & (df["filed"] <= dt_s)]
            net = float((w["buy"] - w["sell"]).sum()) if len(w) else 0.0
            rows.append({"month": dt_s[:7], "symbol": s, "net_buy": net, "fwd": float(fwd[s])})
    panel = pd.DataFrame(rows)
    # cross-sectional IC of net-buy vs forward return, per month; significance on non-overlap months
    months = sorted(panel["month"].unique())
    def ics(ms):
        out = []
        for m in ms:
            g = panel[panel["month"] == m]
            if g["net_buy"].abs().sum() == 0 or len(g) < 12:
                continue
            out.append(g["net_buy"].rank().corr(g["fwd"].rank()))
        return pd.Series([x for x in out if pd.notna(x)], dtype=float)
    full = summarize(ics(months))
    nonov = summarize(ics(months[::stride_for(HOLD)]))
    active = int((panel["net_buy"] != 0).sum())
    return panel, full, nonov, active, len(covered)


def main():
    syms = USAAdapter().symbols
    if "--probe" in sys.argv:
        tm = json.loads(CIK_MAP.read_text())
        for t in ["JPM", "XOM", "WMT"]:
            recs = []
            for filed, acc, doc in list_form4(tm[t], 8):
                p = parse_form4(tm[t], acc, doc); time.sleep(0.1)
                if p:
                    recs.append((filed, round(p["buy"]), round(p["sell"]), p["officer_buy"]))
            print(f"{t}: {recs}")
        return
    if "--run" in sys.argv:
        cap = int(sys.argv[sys.argv.index("--cap") + 1]) if "--cap" in sys.argv else 80
        deep = "--deep" in sys.argv
        print(f"  ingesting Form 4 for {len(syms)} names ({'DEEP shards since 2012' if deep else f'recent cap {cap}'})...", flush=True)
        ingest(syms, cap, deep=deep)
        panel, full, nonov, active, ncov = gate()
        ic = nonov[0] if nonov else (full[0] if full else 0.0)
        ir = nonov[1] if nonov else 0.0
        n = nonov[2] if nonov else 0
        tag = "deep 12y" if deep else "PILOT recent-only"
        promote = full and abs(full[0]) > 0.03 and nonov and abs(nonov[1]) > 2.0
        status = "promoted" if promote else ("investigate" if (full and abs(full[0]) > 0.03) else "not-promoted")
        verdict = ("PROMISING" if promote else ("directional lead, underpowered" if (full and abs(full[0]) > 0.03) else f"no signal ({tag})"))
        print("=" * 64)
        print("  RC005 — INSIDER NET OPEN-MARKET BUY (Form 4, PILOT recent-only)")
        print("=" * 64)
        print(f"  names {ncov} · active net-buy obs {active} · months {panel['month'].nunique()}")
        if full:
            print(f"  monthly IC {full[0]:+.3f} (IR {full[1]:+.2f}, {full[2]}m)")
        if nonov:
            print(f"  non-overlap IC {nonov[0]:+.3f} (IR {nonov[1]:+.2f}, {nonov[2]}m)  <- significance read")
        print(f"  VERDICT: {verdict}")
        md = f"""# RC005 — Insider net open-market buy (Program 1, PILOT)

**Status:** PILOT (recent-only) · **Verdict:** {verdict} · **Date:** {date.today()} · **Script:** `experiments/rc005_insider.py`

SEC Form 4 open-market purchases (code P) minus sales (S), net over trailing 90d (PIT `filed` date),
cross-sectional rank-IC vs forward {HOLD}d return; significance on non-overlapping months.

- names {ncov} · active net-buy observations {active} · months {panel['month'].nunique()}
- monthly IC {f'{full[0]:+.3f} (IR {full[1]:+.2f}, n={full[2]})' if full else 'insufficient'}
- non-overlap IC {f'{nonov[0]:+.3f} (IR {nonov[1]:+.2f}, n={nonov[2]})' if nonov else 'insufficient'}

**Scope:** {tag}. Deep mode traverses submission shards (bounded) back to 2012; insider open-market BUYS (P)
are sparse in mega-caps, so power comes from breadth × time. The pipeline (ingest -> feature -> gate ->
publish) is built and reusable.

**Next best experiment:** {"RC006 analyst revisions (genuinely different signal)" if status=='not-promoted' else "split into CEO-buy / cluster-buy / large-buy and officer-only variants"}.
"""
        row = {"market": "USA", "program": "1-Insider", "cycle": "RC005",
               "factor_or_experiment": "insider_net_buy_90d", "scope": f"fwd {HOLD}d (Form4 {tag})",
               "IC": f"{ic:.3f}", "IC_IR": f"{ir:.2f}", "lift": "", "n": n, "status": status,
               "confidence": confidence(ir, n), "date": str(date.today()),
               "notes": verdict + f"; SEC Form 4 code P-S net 90d; {tag}",
               "next_best_experiment": "RC006 analyst revisions" if status == "not-promoted" else "split CEO/cluster/large-buy + officer-only"}
        publish(program="1-AltData", report_slug="RC005_insider", report_md=md, rows=[row])
        return
    print(__doc__)


if __name__ == "__main__":
    main()
