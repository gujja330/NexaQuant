"""AEGIS USA · News Sentiment Ingestion v1.0.

Google News RSS per-ticker → light lexicon-based sentiment score.

Free source: Google News RSS (per company name search). No API key.
Score: (positive_hits - negative_hits) / max(1, headlines) in [-1, +1].
Uses a compact finance-oriented lexicon (avoids the FinBERT dependency
on the ingest side — sentiment can be re-scored offline with FinBERT
later without changing the ingest pipeline).

Output:
  usa/data/raw/us/news_sentiment.parquet    (append-only ledger)
  usa/reports/news_sentiment_summary.json   (compact daily snapshot)

Deterministic — no random state; sorted iteration.
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

warnings.simplefilter("ignore")

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]

UNIVERSE_JSON = _USA / "reports" / "universe.json"
OUT_PARQUET   = _USA / "data"    / "raw" / "us" / "news_sentiment.parquet"
OUT_SUMMARY   = _USA / "reports" / "news_sentiment_summary.json"

# Compact finance-oriented lexicon (deterministic, offline; sentiment can be
# upgraded to FinBERT later without touching the ingest pipeline).
POS = {"beat", "beats", "beat estimates", "record", "surge", "soar", "soars",
       "upgrade", "upgraded", "outperform", "buy rating", "raises guidance",
       "profit rises", "bull", "bullish", "rally", "expand", "expansion",
       "acquires", "acquisition", "wins", "contract win", "approved", "approval",
       "growth", "gains", "jumps", "climbs", "milestone", "strong", "beats forecast"}
NEG = {"miss", "misses", "miss estimates", "downgrade", "downgraded",
       "underperform", "sell rating", "cuts guidance", "profit falls", "loss",
       "losses", "bear", "bearish", "plunge", "plunges", "slump", "slumps",
       "falls", "drops", "tumble", "tumbles", "probe", "lawsuit", "fraud",
       "recall", "layoffs", "warning", "warns", "cut", "downturn", "weak"}


def _headlines(query: str, n: int = 8) -> list[str]:
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(query + " stock") + "&hl=en-US&gl=US&ceid=US:en")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        xml = urllib.request.urlopen(req, timeout=15).read()
    except Exception:
        return []
    try:
        root = ET.fromstring(xml)
    except Exception:
        return []
    titles = []
    for item in root.iter("item"):
        t = item.findtext("title")
        if t: titles.append(t.strip())
        if len(titles) >= n: break
    return titles


def _score(headlines: list[str]) -> tuple[float, int, int, int]:
    if not headlines:
        return 0.0, 0, 0, 0
    text = " ".join(h.lower() for h in headlines)
    pos = sum(1 for k in POS if k in text)
    neg = sum(1 for k in NEG if k in text)
    n = len(headlines)
    # Bounded score in [-1, +1]
    score = (pos - neg) / max(1, n)
    score = max(-1.0, min(1.0, score))
    return round(score, 3), pos, neg, n


def _load_universe() -> list[tuple[str, str]]:
    """Return list of (symbol, query_name) — reads from universe.json (tenant-generic)."""
    if not UNIVERSE_JSON.exists():
        return []
    data = json.loads(UNIVERSE_JSON.read_text(encoding="utf-8"))
    out = []
    for t in data.get("tickers", []):
        sym = t.get("symbol")
        name = t.get("name") or sym
        # Strip the "Inc.", "Corporation", "Company" suffixes for cleaner news queries
        for s in [" Inc.", " Corporation", " Company", " Corp.", ", Inc.", " Group"]:
            name = name.replace(s, "")
        if sym:
            out.append((sym, name.strip()))
    return sorted(out, key=lambda x: x[0])


def main() -> int:
    print("=" * 70)
    print("  USA News Sentiment Ingest v1.0")
    print("=" * 70)
    universe = _load_universe()
    if not universe:
        print("  FATAL: no USA universe found at usa/reports/universe.json"); return 1
    print(f"  universe: {len(universe)} tickers")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    rows = []
    for sym, name in universe:
        titles = _headlines(name, n=8)
        score, pos, neg, n_head = _score(titles)
        rows.append({
            "asof":        now.date().isoformat(),
            "ingested_utc": now_iso,
            "symbol":      sym,
            "query":       name,
            "news_sent":   score,
            "pos":         pos,
            "neg":         neg,
            "n_headlines": n_head,
        })
        time.sleep(0.15)     # be gentle to Google News

    df_new = pd.DataFrame(rows)
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    if OUT_PARQUET.exists():
        try:
            df_old = pd.read_parquet(OUT_PARQUET)
            df = pd.concat([df_old, df_new], ignore_index=True) \
                   .drop_duplicates(subset=["asof", "symbol"], keep="last") \
                   .sort_values(["asof", "symbol"]).reset_index(drop=True)
        except Exception:
            df = df_new
    else:
        df = df_new
    df.to_parquet(OUT_PARQUET, index=False)

    # Compact summary for backend_validation + downstream engines
    with_news = df_new[df_new["n_headlines"] > 0]
    summary = {
        "engine":       "usa_news_sentiment",
        "version":      "v1.0",
        "run_utc":      now_iso,
        "asof":         now.date().isoformat(),
        "n_tickers":    len(df_new),
        "n_with_news":  int(len(with_news)),
        "avg_sentiment": round(float(with_news["news_sent"].mean()), 3) if len(with_news) else 0.0,
        "n_positive":   int((df_new["news_sent"] > 0.1).sum()),
        "n_negative":   int((df_new["news_sent"] < -0.1).sum()),
        "n_neutral":    int(df_new["news_sent"].abs().le(0.1).sum()),
        "history_rows": int(len(df)),
        "parquet":      str(OUT_PARQUET.relative_to(_ROOT).as_posix()),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_PARQUET.relative_to(_ROOT)} · {len(df)} rows (history), {len(df_new)} today")
    print(f"  summary: {OUT_SUMMARY.relative_to(_ROOT)}")
    print(f"  avg sentiment (with news): {summary['avg_sentiment']}  · "
          f"pos={summary['n_positive']}  neg={summary['n_negative']}  neu={summary['n_neutral']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
