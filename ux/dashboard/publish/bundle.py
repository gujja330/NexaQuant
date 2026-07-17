"""UX031 · publish 5 JSON configs + README pointer."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"

from ux.dashboard.lib import theme, widgets, routes, layouts, config


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    return obj


def build_and_publish() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)

    stamp = {"run_utc": datetime.now(timezone.utc).isoformat() + "Z",
              "dev_version": "UX031 v0.1"}

    written = []

    for name, obj in [
        ("dashboard_layout.json",   {**stamp, "layouts":  layouts.all_layouts()}),
        ("dashboard_widgets.json",  {**stamp, "widgets":  widgets.all_widgets(),
                                          "count": len(widgets.all_widgets())}),
        ("dashboard_routes.json",   {**stamp, "routes":   routes.routes(),
                                          "filters": routes.filters(),
                                          "count_routes": len(routes.routes())}),
        ("dashboard_theme.json",    {**stamp, "theme":    theme.theme_dict()}),
        ("dashboard_config.json",   {**stamp, "config":   config.config()}),
    ]:
        with (REPORTS / name).open("w", encoding="utf-8") as f:
            json.dump(_sanitize(obj), f, indent=2)
        written.append(name)

    return {"written": written,
             "n_widgets": len(widgets.all_widgets()),
             "n_routes":  len(routes.routes()),
             "n_layouts": len(layouts.all_layouts()),
             "n_filters": len(routes.filters())}
