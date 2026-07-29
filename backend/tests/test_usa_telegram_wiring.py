"""Regression guardrail: USA workflow must pass Telegram tokens to the
orchestrator so the telegram_send step actually delivers.

Without this env block, usa/scripts/telegram_send.py silently no-ops:
    [usa telegram] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — skipping.
The India workflow has always wired these; USA parity was missing until
CEO cycle 4.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

USA_WF = _ROOT / ".github" / "workflows" / "aegis-usa.yml"


def _find_orchestrator_step_block() -> str:
    """Return the YAML block for the 'Run USA daily orchestrator' step."""
    text = USA_WF.read_text(encoding="utf-8")
    # Match from '- name: Run USA daily orchestrator' up to next '- name:' or EOF
    m = re.search(r"- name:\s*Run USA daily orchestrator[\s\S]*?(?=\n\s*- name:|\Z)",
                     text)
    assert m, "Could not locate 'Run USA daily orchestrator' step in aegis-usa.yml"
    return m.group(0)


def test_usa_workflow_passes_telegram_bot_token():
    block = _find_orchestrator_step_block()
    assert "TELEGRAM_BOT_TOKEN" in block, (
        "USA orchestrator step is missing TELEGRAM_BOT_TOKEN env — "
        "telegram_send will silently skip in CI"
    )
    assert "secrets.TELEGRAM_BOT_TOKEN" in block


def test_usa_workflow_passes_telegram_chat_id():
    block = _find_orchestrator_step_block()
    assert "TELEGRAM_CHAT_ID" in block, (
        "USA orchestrator step is missing TELEGRAM_CHAT_ID env — "
        "telegram_send will silently skip in CI"
    )
    assert "secrets.TELEGRAM_CHAT_ID" in block


def test_usa_telegram_sender_expects_shared_env_vars():
    """The sender must read the same env-var names India does. If we ever
    rename to USA_TELEGRAM_BOT_TOKEN etc., this test forces us to update the
    workflow guardrails at the same time."""
    src = (_ROOT / "usa" / "scripts" / "telegram_send.py").read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN" in src
    assert "TELEGRAM_CHAT_ID" in src
