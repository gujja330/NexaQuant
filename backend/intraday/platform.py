"""Intraday Platform SSoT emitter · reports/intraday/intraday_platform.json.

Zero coupling to backend/research/ or backend/recommendation/. Writes
its OWN SSoT that scripts/intraday_paper_run.py + its own Telegram
sender consume.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path


def build_intraday_platform(root: Path,
                                market: str = "india",
                                experiment_start: str | None = None) -> dict:
    """Compile intraday-only SSoT from backtest + any live paper state."""
    now = datetime.now(timezone.utc)
    day_of_program = 0
    if experiment_start:
        try:
            day_of_program = (date.today()
                                - date.fromisoformat(experiment_start)).days + 1
        except ValueError:
            pass

    payload = {
        "engine":               "aegis.intraday.platform.v1",
        "schema_fingerprint":   "aegis.intraday.platform.v1.20260731",
        "run_utc":              now.isoformat(),
        "market":               market,
        "kind":                 "intraday",
        "program": {
            "experiment_start":     experiment_start,
            "day_of_program":       day_of_program,
            "window_days_minimum":  60,
            "window_days_target":   90,
            "lifecycle_state":      "HISTORICAL_BACKTEST",   # ticket R004
            "product_status":       "DEFERRED_as_product",
        },
        "backtest":             None,
        "note":                 ("Intraday engine per docs/AEGIS_INTRADAY_ARCHITECTURE.md · "
                                    "ticket R004 · Article IX Research Lifecycle."),
    }

    # Attach backtest if present
    bt_path = root / "reports" / "intraday" / f"backtest_{market}.json"
    if bt_path.exists():
        try:
            payload["backtest"] = json.loads(bt_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Attach today's paper session if present
    paper_path = root / "reports" / "intraday" / f"paper_{market}_{date.today().isoformat()}.json"
    if paper_path.exists():
        try:
            payload["today_paper"] = json.loads(paper_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    out = root / "reports" / "intraday" / "intraday_platform.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return payload
