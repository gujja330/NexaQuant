"""UX031 · dashboard runtime configuration.

Global settings the frontend needs at boot: brand, data sources, auth mode,
performance budgets, feature flags.

None of these values are secret. Actual TELEGRAM_BOT_TOKEN etc. remain in
`.env` and are not surfaced to the browser."""
from __future__ import annotations


def config() -> dict:
    return {
        "brand": {
            "name":        "NEXAQUANT",
            "product":     "AEGIS",
            "product_full":"AEGIS Institutional Intelligence Platform",
            "logo_short":  "N",
            "tagline":     "Evidence-driven institutional intelligence",
        },
        "runtime": {
            "environment":    "production",
            "default_theme":  "dark",
            "allow_theme_toggle": True,
            "default_route":  "/",
            "advisory_only":  True,
        },
        "data_sources": {
            "root_path":       "reports/",
            "refresh_cadence": "daily_06:00_IST",
            "file_watchers":   True,
            "stale_after_hours": 30,
        },
        "quality_gates": {
            "advisory_only":     True,
            "no_state_mutation": True,
            "tenant_generic":    True,
            "deterministic":     True,
        },
        "auth": {
            "mode":                "session",   # frontend session cookie; backend enforces
            "require_login":       False,       # single-tenant dev deployment
            "supported_roles":     ["operator", "viewer", "admin"],
        },
        "performance_budgets": {
            "initial_render_ms":       1500,
            "widget_data_load_ms":     600,
            "route_transition_ms":     220,
            "max_widgets_per_route":   14,
        },
        "feature_flags": {
            "knowledge_graph":        True,
            "champion_challenger":    True,
            "confidence_calibration": True,
            "recommendation_dna":     True,
            "strategy_doctor":        True,
        },
        "shortcuts": {
            "cmd_k":             "open_command_palette",
            "cmd_p":             "quick_switch_route",
            "cmd_h":             "toggle_help_overlay",
            "?":                 "show_keyboard_shortcuts",
            "g_then_p":          "goto_portfolio",
            "g_then_r":          "goto_recommendations",
            "g_then_c":          "goto_champion",
            "g_then_k":          "goto_knowledge_graph",
        },
        "principles": [
            "advisory only; the dashboard never mutates state",
            "tenant-generic (no hardcoded tickers/sectors/companies)",
            "deterministic — same reports/ input, same rendering",
            "responsive; usable at mobile, tablet, desktop",
            "accessible (WCAG AA color contrast, keyboard-navigable)",
            "fast — every widget lazy-loaded, no blocking calls",
        ],
    }
