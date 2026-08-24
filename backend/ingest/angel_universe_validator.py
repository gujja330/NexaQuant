"""Angel SmartAPI · universe validator + live-price wrapper.

Operator 2026-08-24: "u can pull whatever data is availble using
angel, dont miss the chance." Two Angel-powered additions the daily
pipeline can lean on right now (no extra API calls beyond the
already-cached instrument master + a per-ticker LTP fetch):

  1. Universe validator · walks our parquet-derived universe and
     cross-checks every symbol against Angel's live NSE instrument
     master. Flags tickers that DO NOT exist in NSE anymore ·
     auto-detects the TATAMOTORS / LTIM / PEL / MM problem before it
     bites the fundamentals ingest.

  2. Live LTP (last-traded-price) fetcher · pulls current market
     price for a batch of tickers in near-real-time via Angel's
     quote endpoint. Optional refresh for the sender's P&L math ·
     drops the "yesterday close" lag when markets are open.

Both live under backend.ingest. Zero cost to yfinance chain.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, date
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# Universe validator
# ─────────────────────────────────────────────────────────────

def _load_angel_instrument_master(root: Path) -> dict:
    """Return {bare_symbol: token} for NSE EQ. Cached at
    data/raw/angel_instruments.json by the intraday adapter · we
    reuse it here."""
    p = root / "data" / "raw" / "angel_instruments.json"
    if not p.exists():
        # Trigger a refresh via the intraday adapter's loader
        try:
            from backend.intraday.feed import angel_adapter as _angel
            _angel._resolve_instrument_token(root, "RELIANCE")   # warms cache
        except Exception:
            return {}
    if not p.exists(): return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


@dataclass
class UniverseValidationReport:
    engine:         str = "aegis.angel.universe_validator.v1"
    generated_utc:  str = ""
    market:         str = ""
    asof:           str = ""
    n_universe:     int = 0
    n_valid_nse:    int = 0
    n_dead:         int = 0
    dead_symbols:   list = field(default_factory=list)
    alias_hits:     list = field(default_factory=list)


def _local_universe(root: Path, market: str) -> list:
    d = ((root / "usa" / "data" / "raw" / "us") if market.lower() == "usa"
             else (root / "data" / "raw" / "india"))
    if not d.exists(): return []
    return sorted(p.stem.replace("_D1", "").upper()
                          for p in d.glob("*_D1.parquet"))


def validate_universe(root: Path, market: str, asof: str) -> UniverseValidationReport:
    """India only (Angel is NSE-scoped)."""
    market = market.lower()
    asof = asof[:10]
    rep = UniverseValidationReport(
        market=market, asof=asof,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    if market != "india":
        return rep     # Angel is NSE-only · no-op for USA
    universe = _local_universe(root, market)
    rep.n_universe = len(universe)
    master = _load_angel_instrument_master(root)
    if not master:
        return rep     # instrument master unavailable · noop

    # Load alias config so a legacy symbol like MM maps to M&M before check
    try:
        import yaml
        aliases_p = root / "configs" / "ticker_aliases.yaml"
        aliases = (yaml.safe_load(aliases_p.read_text(encoding="utf-8"))
                          or {}).get("india", {}) if aliases_p.exists() else {}
    except Exception:
        aliases = {}

    master_up = {k.upper(): v for k, v in master.items()}
    for sym in universe:
        # Non-stock indices skip
        if sym in ("NSEI", "NSEBANK", "INDIAVIX", "SP500"): continue
        if sym in master_up:
            rep.n_valid_nse += 1
            continue
        # Try alias
        alias = aliases.get(sym, "")
        if alias and alias.upper() in master_up:
            rep.n_valid_nse += 1
            rep.alias_hits.append({"legacy": sym, "live": alias})
            continue
        rep.n_dead += 1
        rep.dead_symbols.append(sym)
    return rep


def emit_validation(root: Path, rep: UniverseValidationReport) -> Path:
    p = (root / "reports" / "context"
             / f"angel_universe_validation_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def summary_line(rep: UniverseValidationReport) -> str:
    if rep.n_dead > 0:
        return (f"⚠️ {rep.n_dead} DEAD symbols in universe · "
                    f"first: {', '.join(rep.dead_symbols[:5])}")
    return f"✅ {rep.n_valid_nse}/{rep.n_universe} tickers valid in NSE"


# ─────────────────────────────────────────────────────────────
# Live LTP (last-traded-price) fetcher
# ─────────────────────────────────────────────────────────────

def fetch_ltp_batch(root: Path, tickers: list) -> dict:
    """Return {bare_ticker: last_price_float} for a batch. Angel's
    quote endpoint accepts up to 50 tokens/call · we chunk larger
    lists. Returns partial results on failure (never raises)."""
    try:
        from backend.intraday.feed import angel_adapter as _angel
    except Exception:
        return {}
    client = _angel._get_client(root)
    if client is None: return {}
    out: dict = {}
    # Resolve tokens
    tokens = []
    tk_by_token = {}
    for tk in tickers:
        tok = _angel._resolve_instrument_token(root, tk)
        if tok:
            tokens.append(tok)
            tk_by_token[tok] = str(tk).upper().replace(".NS","").replace(".BO","")
    if not tokens: return {}
    # Angel accepts one exchange · we use NSE
    for i in range(0, len(tokens), 50):
        chunk = tokens[i:i+50]
        try:
            payload = {"mode": "LTP",
                             "exchangeTokens": {"NSE": chunk}}
            data = client.getMarketData(**payload)
            if not data or not data.get("status"): continue
            for row in (data.get("data") or {}).get("fetched", []):
                tok = str(row.get("symbolToken") or "")
                ltp = row.get("ltp")
                if tok and isinstance(ltp, (int, float)):
                    tk = tk_by_token.get(tok, tok)
                    out[tk] = float(ltp)
        except Exception:
            continue
    return out


def emit_ltp_snapshot(root: Path, market: str, ltp_map: dict) -> Path:
    """Persist the LTP snapshot as JSON for sender + audit consumers."""
    p = (root / "reports" / "context"
             / f"angel_ltp_snapshot_{market.lower()}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":        market.lower(),
        "n_tickers":     len(ltp_map),
        "ltp":           ltp_map,
    }
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p
