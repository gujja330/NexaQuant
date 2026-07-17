"""UX030 · publish 5 JSON configs + examples.md."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"

from ux.telegram.lib import icons, commands, notification_rules, renderer
from ux.telegram.lib.aggregator import load_context


def _templates() -> dict:
    return {
        "brand": "NEXAQUANT · AEGIS",
        "message_types": {
            "morning_brief":          {"function": "render_morning_brief",       "max_lines": 4},
            "executive_summary":      {"function": "render_executive_summary",   "max_lines": 24},
            "new_buys_summary":       {"function": "render_new_buys_summary",    "max_lines": 12},
            "buy_alert":              {"function": "render_buy_alert",           "max_lines": 15, "args": ["ticker"]},
            "exit_alert":             {"function": "render_exit_alert",          "max_lines": 12, "args": ["ticker"]},
            "portfolio_health":       {"function": "render_portfolio_health",    "max_lines": 15},
            "risk_alert":             {"function": "render_risk_alert",          "max_lines": 8,  "args": ["alert"]},
            "champion_update":        {"function": "render_champion_update",     "max_lines": 12},
            "weekly_review":          {"function": "render_weekly_review",       "max_lines": 12},
        },
        "styling": {
            "use_markdown":      True,
            "line_max_chars":    42,
            "mobile_first":      True,
            "monospace_tickers": True,
        },
        "principles": [
            "consumable in <=30 seconds",
            "tenant-generic (no hardcoded tickers/sectors/companies)",
            "deterministic (same input -> same output)",
            "advisory-only (no state mutation from delivery)",
        ],
    }


def _layouts() -> dict:
    return {
        "executive_summary": {
            "sections": [
                {"name": "header",       "elements": ["brand", "timestamp"]},
                {"name": "counts",       "elements": ["buy_count", "hold_count", "exit_count"]},
                {"name": "regime",       "elements": ["regime_badge", "champion"]},
                {"name": "portfolio",    "elements": ["positions", "cash_pct", "top5_share"]},
                {"name": "opportunity",  "elements": ["top_ticker", "stars", "confidence"]},
                {"name": "exits",        "elements": ["exit_tickers"]},
                {"name": "ai_summary",   "elements": ["3_sentence_synthesis"]},
                {"name": "footer",       "elements": ["command_hint"]},
            ],
        },
        "buy_alert": {
            "sections": [
                {"name": "header",       "elements": ["status_icon", "sector_icon", "ticker", "rec_type"]},
                {"name": "levels",       "elements": ["entry_zone", "targets", "stop_loss"]},
                {"name": "score",        "elements": ["confidence_stars", "confidence_pct"]},
                {"name": "meta",         "elements": ["hold_days", "expiry_countdown", "sector"]},
                {"name": "why",          "elements": ["reasons_for"]},
            ],
        },
        "portfolio_health": {
            "sections": [
                {"name": "header",       "elements": ["brand", "timestamp"]},
                {"name": "grade",        "elements": ["overall_grade", "health_bar"]},
                {"name": "composition",  "elements": ["positions", "cash", "top5_share"]},
                {"name": "risk",         "elements": ["diversification_grade", "risk_level"]},
                {"name": "strategy",     "elements": ["champion", "sharpe", "max_dd", "regime"]},
            ],
        },
        "visual_elements": {
            "status_icons":     icons.STATUS,
            "grade_badges":     icons.GRADES,
            "regime_badges":    icons.REGIME,
            "confidence_stars": {"legend": "★★★★★ 95+, ★★★★☆ 85-94, ★★★☆☆ 75-84, ★★☆☆☆ 65-74, ★☆☆☆☆ <65"},
            "progress_bars":    {"cells": 10, "filled": "█", "empty": "░"},
        },
    }


def _commands_export() -> dict:
    return {
        "commands": {
            name: {"args": entry["args"], "description": entry["description"]}
            for name, entry in commands.COMMANDS.items()
        },
        "total_commands": len(commands.COMMANDS),
        "dispatch_note":  "Every command is deterministic; no LLM in the loop.",
    }


def _ui_config() -> dict:
    return {
        "brand":       "NEXAQUANT · AEGIS",
        "style":       "institutional",
        "theme":       "mobile-first-dark",
        "typography": {
            "monospace_tokens": ["ticker", "strategy_name", "allocator"],
            "bold_headings":    True,
            "italic_footnotes": True,
        },
        "icon_registry": {
            "status":   icons.STATUS,
            "grades":   icons.GRADES,
            "regime":   icons.REGIME,
            "sectors":  icons.SECTOR_ICONS,
            "rec_map":  icons.REC_ICON,
        },
        "confidence_star_thresholds": {
            "95+": 5, "85-94": 4, "75-84": 3, "65-74": 2, "<65": 1,
        },
    }


def _examples_md(ctx) -> str:
    """Render live examples from actual context."""
    lines = ["# UX030 · Telegram Message Examples",
              "",
              f"Generated from live AEGIS outputs at run time (`reports/`).",
              "",
              "> These are the actual messages the delivery layer would produce today.",
              "",
              "---",
              "",
              "## 1 · Morning Brief",
              "",
              "```",
              renderer.render_morning_brief(ctx),
              "```",
              "",
              "## 2 · Daily Executive Summary",
              "",
              "```",
              renderer.render_executive_summary(ctx),
              "```",
              "",
              "## 3 · Portfolio Health",
              "",
              "```",
              renderer.render_portfolio_health(ctx),
              "```",
              "",
              "## 4 · Champion Update",
              "",
              "```",
              renderer.render_champion_update(ctx),
              "```",
              "",
              "## 5 · New Buys Summary",
              "",
              "```",
              renderer.render_new_buys_summary(ctx),
              "```",
              "",
              "## 6 · Weekly Review",
              "",
              "```",
              renderer.render_weekly_review(ctx),
              "```",
              "",
              "---",
              "",
              "## Command Examples",
              "",
              ]

    for cmd in ["help", "portfolio", "risk", "champion", "regime", "confidence"]:
        lines += [f"### /{cmd}", "", "```", commands.dispatch(ctx, f"/{cmd}"), "```", ""]

    return "\n".join(lines)


def build_and_publish() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    ctx = load_context()

    written = []

    for name, obj in [
        ("telegram_templates.json",           _templates()),
        ("telegram_layouts.json",             _layouts()),
        ("telegram_commands.json",            _commands_export()),
        ("telegram_notification_rules.json",  notification_rules.summarise_ruleset()),
        ("telegram_ui_config.json",           _ui_config()),
    ]:
        obj["run_utc"] = datetime.now(timezone.utc).isoformat() + "Z"
        with (REPORTS / name).open("w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        written.append(name)

    md_path = REPORTS / "telegram_examples.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write(_examples_md(ctx))
    written.append("telegram_examples.md")

    return {"written": written, "context_ok": bool(ctx.recommendations or ctx.champion)}
