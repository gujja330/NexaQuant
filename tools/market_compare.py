# tools/market_compare.py
"""
PROGRAM X — Market Comparison (MC). Decide each market's long-term ROLE with evidence, not preference.
MC002 (research success) is computed live from the Leaderboard; MC001/003-006 are evidence-grounded
assessments (factual where known, judgment clearly flagged). Emits markets/research/MARKET_DECISION.md.

Run:  python tools/market_compare.py
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "markets" / "research"
LB = list(csv.DictReader((RES / "LEADERBOARD.csv").open()))


def conf_num(s):
    try:
        return int(s.split("(")[0])
    except Exception:
        return None


def mc002(mkt):
    rows = [r for r in LB if r["market"] == mkt and r["status"] != "superseded"]
    promoted = sum(1 for r in rows if r["status"] in ("kept", "promoted"))
    rejected = sum(1 for r in rows if r["status"] in ("not-promoted", "weak", "neutral", "no-effect", "reject-as-positive"))
    invest = sum(1 for r in rows if r["status"] == "investigate")
    cf = [conf_num(r.get("confidence", "")) for r in rows]
    cf = [c for c in cf if c is not None]
    return dict(n=len(rows), promoted=promoted, rejected=rejected, invest=invest,
                avgc=round(sum(cf) / len(cf)) if cf else 0)


def main():
    i, u = mc002("INDIA"), mc002("USA")
    L = ["# Program X — Market Comparison & Decision (MARKET_DECISION.md)",
         "",
         "Evidence-based decision on each market's long-term role. MC002 is computed from the Leaderboard; "
         "other sections are evidence-grounded assessment (J = judgment, F = factual).",
         "",
         "## MC001 — Data Quality & Availability",
         "| Dimension | India | USA |",
         "|---|---|---|",
         "| Price history (F) | ~5y usable panels | **decades** (SPX 1927; stocks up to 64y) |",
         "| Liquid universe (F) | few hundred (NSE) | **5,000+ screened → 227 liquid, expandable** |",
         "| PIT fundamentals (F) | limited/costly | **SEC EDGAR — free, official, filed-date** |",
         "| Insider data (F) | sparse/unclean | **SEC Form 4 — free, ~2-day PIT** |",
         "| 13F / ETF / macro (F) | mostly unavailable free | **all free (SEC 13F, issuers, FRED)** |",
         "| Survivorship-free source (F) | hard | hard (both need CRSP/Norgate eventually) |",
         "| Free availability / API (F) | broker-gated | **fully free + stable (SEC/Yahoo/FRED)** |",
         "| → MC001 winner | | **USA (decisively)** |",
         "",
         "## MC002 — Research Success (computed from the Leaderboard)",
         "| Metric | India | USA |",
         "|---|---|---|",
         f"| Experiments (ex-superseded) | {i['n']} | {u['n']} |",
         f"| Promoted | {i['promoted']} | {u['promoted']} |",
         f"| Rejected / closed | {i['rejected']} | {u['rejected']} |",
         f"| Investigating | {i['invest']} | {u['invest']} |",
         f"| Avg confidence | {i['avgc']} | {u['avgc']} |",
         "| → MC002 read | concentrated: 1 validated edge | high throughput, mostly rejections |",
         "",
         "**Key finding:** neither market has demonstrated stock-**selection** alpha. The ONLY validated edge "
         "— the regime overlay — is **cross-market** (works in both). So 'which market discovers edges' is "
         "largely the wrong question: the edge we found is market-agnostic.",
         "",
         "## MC003 — Production Comparison (J/F)",
         "- **India:** LIVE production engine — daily automation (GitHub Actions), Telegram + Google Sheets, "
         "recommendation DB, frozen v1.x baseline. Real operational track record. (F)",
         "- **USA:** paper-only; no live track record yet. (F)",
         "- Both engines are the SAME core via adapters; India is simply further along operationally.",
         "- → **Production winner: India** (maturity/operations), not because of better alpha.",
         "",
         "## MC004 — Research Cost (J)",
         "- **USA:** richer data but heavier pipelines (deep ingest, shards, large universes → more compute/"
         "storage/maintenance). **India:** smaller, simpler, cheaper to run, but expensive/hard to *expand* "
         "(little free alt-data). → Cost-per-experiment favors India today; cost-to-scale favors USA.",
         "",
         "## MC005 — Expandability (F/J)",
         "- **USA wins decisively:** insider, 13F, ETF, options, macro (FRED), news — all free and PIT. "
         "India has few comparable free alternative datasets. → **USA**.",
         "",
         "## MC006 — Commercial Opportunity (J)",
         "- Larger addressable market, deeper liquidity, more data vendors and customers in **USA/Global**; "
         "India is a strong secondary. (Business judgment, not a research result.) → **USA/Global**.",
         "",
         "## Scorecard (ratings are judgment, 1–5)",
         "| Category | India | USA | Winner |",
         "|---|--:|--:|---|",
         "| Data quality/depth | 2 | 5 | USA |",
         "| Research success (edges found) | 3 | 3 | Tie (edge is cross-market) |",
         "| Production maturity | 5 | 2 | India |",
         "| Research cost (cheap to run) | 4 | 3 | India |",
         "| Expandability | 2 | 5 | USA |",
         "| Commercial/scale | 3 | 5 | USA |",
         "| AI potential (data diversity) | 2 | 5 | USA |",
         "",
         "## Decision",
         "**Do NOT pick one market. Stay market-AGNOSTIC (Option D) — which AEGIS already is** (the "
         "`MarketAdapter` seam: one research core, markets are adapters). The evidence supports a clear "
         "division of roles:",
         "- **USA = primary RESEARCH market** — richest free PIT data, deepest history, most expandable, best "
         "for discovering and stress-testing factors at scale.",
         "- **India = primary PRODUCTION market** — the mature live engine, automation, and operational track "
         "record; keep it as the production adapter.",
         "- **The core stays market-neutral.** The single strongest argument for this: our one validated edge "
         "(the regime overlay) is itself **cross-market** — value lives in the shared research core, not in "
         "either market. New domains (insider/analyst/ETF/macro) are best mined in USA (data) and any robust, "
         "cross-market-validated factor is promoted into the shared library, then into India production.",
         "",
         "**Frozen market strategy:** market-agnostic core · USA-led research · India-led production · "
         "promote only cross-market-validated factors to production.",
         "",
         "_Pending: RC005 (insider) deep ingest still running; its verdict updates MC002 for USA when done — "
         "does not change the role decision._"]
    out = RES / "MARKET_DECISION.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  wrote {out.relative_to(ROOT)}")
    print(f"  MC002 — India: {i['n']} exp, {i['promoted']} promoted, avg conf {i['avgc']}")
    print(f"  MC002 — USA:   {u['n']} exp, {u['promoted']} promoted, avg conf {u['avgc']}")


if __name__ == "__main__":
    main()
