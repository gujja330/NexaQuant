"""AEGIS USA · Universe Builder.

Reads usa/configs/universe.yaml, resolves the active universe, and
emits usa/reports/universe.json — the canonical list every downstream
engine consumes. Same shape India uses for data/aegis_registry.csv,
but explicit JSON for cleaner USA-side plumbing.

Post-LOCK-compatible: does NOT touch India. Only writes under usa/.
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import yaml
except ImportError:
    print("FATAL: PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)

_ROOT = Path(__file__).resolve().parents[2]     # repo root
_USA  = Path(__file__).resolve().parents[1]     # usa/


def main() -> int:
    cfg_path = _USA / "configs" / "universe.yaml"
    if not cfg_path.exists():
        print(f"FATAL: {cfg_path} not found")
        return 1

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    active_name = cfg.get("active_universe") or "sp500_plus_midcap400"
    universes   = cfg.get("universes") or {}
    universe = universes.get(active_name)
    if not universe:
        print(f"FATAL: active_universe '{active_name}' not found in configs/universe.yaml")
        return 1

    tickers = universe.get("tickers") or []

    # v3.0 dynamic universe · Article 3 compliance:
    # A universe may point to an external JSON list via `tickers_from_json`.
    # This lets S&P 500 / MidCap 400 / Russell 1000 be refreshed via a fetcher
    # script without editing YAML. Sector/industry can be filled from adapters
    # downstream OR left blank (adapters tolerate this).
    if not tickers and universe.get("tickers_from_json"):
        json_rel = universe["tickers_from_json"]
        json_path = _USA / json_rel
        if not json_path.exists():
            print(f"FATAL: tickers_from_json points to missing file {json_path}")
            print(f"       run: python usa/scripts/refresh_universe.py")
            return 1
        import json as _json
        payload = _json.loads(json_path.read_text(encoding="utf-8"))
        raw_tickers = payload.get("tickers") or []
        # Compose ticker dicts with metadata defaults
        default_sector = universe.get("default_sector", "Unknown")
        default_exchange = universe.get("default_exchange", "NYSE")
        tickers = [
            {"symbol": t, "name": t, "sector": default_sector,
              "industry": "Unknown", "exchange": default_exchange}
            for t in raw_tickers
        ]
        print(f"[build_universe] loaded {len(tickers)} tickers dynamically from "
              f"{json_rel} · source={payload.get('description', '?')}")

    if not tickers:
        print(f"FATAL: universe '{active_name}' has no tickers")
        return 1

    # Deterministic output — sort by symbol
    tickers_sorted = sorted(tickers, key=lambda t: str(t.get("symbol") or ""))

    # Sector rollup for reporting
    by_sector: dict[str, int] = {}
    by_exchange: dict[str, int] = {}
    for t in tickers_sorted:
        by_sector[t.get("sector", "?")] = by_sector.get(t.get("sector", "?"), 0) + 1
        by_exchange[t.get("exchange", "?")] = by_exchange.get(t.get("exchange", "?"), 0) + 1

    out = {
        "engine":        "usa_universe",
        "version":       "v1.0",
        "run_utc":       datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "active_universe": active_name,
        "description":   universe.get("description", ""),
        "currency":      cfg.get("market", {}).get("currency", "USD"),
        "currency_symbol": cfg.get("market", {}).get("currency_symbol", "$"),
        "n_tickers":     len(tickers_sorted),
        "by_sector":     dict(sorted(by_sector.items(), key=lambda kv: -kv[1])),
        "by_exchange":   dict(sorted(by_exchange.items(), key=lambda kv: -kv[1])),
        "tickers":       tickers_sorted,
        "benchmarks":    cfg.get("benchmarks", {}),
        "market":        cfg.get("market", {}),
    }

    reports_dir = _USA / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "universe.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print("=" * 70)
    print(f"  AEGIS USA · Universe · {active_name}")
    print("=" * 70)
    print(f"  tickers:    {out['n_tickers']}")
    print(f"  currency:   {out['currency_symbol']} ({out['currency']})")
    print()
    print("  By sector:")
    for s, n in list(out["by_sector"].items())[:8]:
        print(f"    {s:<26}  {n}")
    print()
    print("  By exchange:")
    for e, n in out["by_exchange"].items():
        print(f"    {e:<10}  {n}")
    print()
    print(f"  written: {out_path.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
