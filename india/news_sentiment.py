# india/news_sentiment.py
"""
LIVE news-sentiment pipeline (the one lever not already in price).

Free source: Google News RSS (per stock, India). Scored by FinBERT (positive/negative/neutral).
Per stock we compute a sentiment score in [-1, +1] = (positive - negative) / headlines.
Saved/appended to data/raw/india/news_sentiment.parquet with an as-of timestamp, so running it
daily BUILDS a forward history we can later test (free historical news doesn't exist -> we
accumulate it going forward).

  python india/news_sentiment.py            # score the current EW-30 quality basket
  python india/news_sentiment.py --all      # score the whole universe (slow)

This is a LIVE/forward experiment: it cannot be backtested, only paper-traded forward.
"""
import argparse, sys, warnings, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.feature_engine import load_panels
from india.arjuna_strategy import screen, K

OUT = ROOT / "data" / "raw" / "india" / "news_sentiment.parquet"

NAMES = {  # symbol -> better news query (company name); fallback handles the rest
    "RELIANCE": "Reliance Industries", "TCS": "Tata Consultancy Services", "HDFCBANK": "HDFC Bank",
    "ICICIBANK": "ICICI Bank", "INFY": "Infosys", "SBIN": "State Bank of India",
    "BHARTIARTL": "Bharti Airtel", "ITC": "ITC Ltd", "LT": "Larsen Toubro",
    "KOTAKBANK": "Kotak Mahindra Bank", "HINDUNILVR": "Hindustan Unilever", "AXISBANK": "Axis Bank",
    "BAJFINANCE": "Bajaj Finance", "MARUTI": "Maruti Suzuki", "SUNPHARMA": "Sun Pharma",
    "TITAN": "Titan Company", "ASIANPAINT": "Asian Paints", "TATASTEEL": "Tata Steel",
    "ADANIENT": "Adani Enterprises", "ADANIPOWER": "Adani Power", "ADANIGREEN": "Adani Green",
    "ADANIPORTS": "Adani Ports", "JSWSTEEL": "JSW Steel", "HINDALCO": "Hindalco",
    "COALINDIA": "Coal India", "NTPC": "NTPC", "POWERGRID": "Power Grid", "ONGC": "ONGC",
    "MARICO": "Marico", "NESTLEIND": "Nestle India", "TORNTPHARM": "Torrent Pharma",
    "LUPIN": "Lupin", "BIOCON": "Biocon", "ZYDUSLIFE": "Zydus Lifesciences", "SAIL": "SAIL",
    "POLYCAB": "Polycab India", "SHRIRAMFIN": "Shriram Finance", "BAJAJ-AUTO": "Bajaj Auto",
    "EICHERMOT": "Eicher Motors", "GRASIM": "Grasim", "VBL": "Varun Beverages",
    "JINDALSTEL": "Jindal Steel", "MOTHERSON": "Samvardhana Motherson", "APOLLOHOSP": "Apollo Hospitals",
    "ABB": "ABB India", "THERMAX": "Thermax", "LAURUSLABS": "Laurus Labs",
}


def headlines(query, n=8):
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query + " share price") + \
          "&hl=en-IN&gl=IN&ceid=IN:en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        xml = urllib.request.urlopen(req, timeout=20).read()
        return [it.find("title").text for it in ET.fromstring(xml).iter("item")][:n]
    except Exception:
        return []


def sentiment_for(clf, query):
    hl = headlines(query)
    if not hl:
        return 0.0, 0, 0, 0
    pos = neg = neu = 0
    for h in hl:
        r = clf(h[:300])[0]
        lab = max(r, key=lambda x: x["score"])["label"].lower()
        pos += lab == "positive"; neg += lab == "negative"; neu += lab == "neutral"
    n = len(hl)
    return (pos - neg) / n, pos, neg, neu


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    closes, _, _, vols, _, _, _ = load_panels()
    if a.all:
        syms = list(closes.columns)
    else:
        sc = screen(closes, vols, "quality")
        syms = list(sc.loc[sc.index.max()].dropna().sort_values(ascending=False).head(K).index)

    print(f"  loading FinBERT + scoring {len(syms)} stocks from Google News (India)...")
    from transformers import pipeline
    clf = pipeline("text-classification", model="ProsusAI/finbert", top_k=None)
    asof = datetime.now()
    rows = []
    for s in syms:
        score, pos, neg, neu = sentiment_for(clf, NAMES.get(s, s))
        rows.append({"asof": asof, "symbol": s, "news_sent": round(score, 3),
                     "pos": pos, "neg": neg, "neu": neu})
        print(f"  {s:<12} sent {score:+.2f}  (+{pos}/-{neg}/~{neu})")
    df = pd.DataFrame(rows)
    # append to the forward-accumulating table
    if OUT.exists():
        df = pd.concat([pd.read_parquet(OUT), df], ignore_index=True)
    df.to_parquet(OUT)
    today = df[df["asof"] == asof]
    print(f"\n  saved -> {OUT}  ({len(df)} total rows, building forward history)")
    print(f"  MOST POSITIVE today: " + ", ".join(today.nlargest(5, 'news_sent')['symbol']))
    print(f"  MOST NEGATIVE today: " + ", ".join(today.nsmallest(5, 'news_sent')['symbol']))


if __name__ == "__main__":
    main()
