"""backend.recommendation.ssot — Single-Source-of-Truth publisher.

Final Platform Completion Program · Phase 1.

Purpose: eliminate the keystone `reports/recommendations.json` gap by
publishing the fresh Runner 2 v3 output in the legacy schema that
downstream consumers (fusion · knowledge_graph · institutional_memory ·
decision_attribution · winner_genome · morning_report · Telegram
UX030 · dashboard) expect.

One producer. One schema. One consumer contract.

Constitution: Articles 20 · 21 · 25 · 100 (L4 CONSUMED target).
"""
from __future__ import annotations

from backend.recommendation.ssot.bridge import (  # noqa: F401
    publish_ssot,
    translate_v3_to_legacy,
    ACTION_MAP,
    SCHEMA_FINGERPRINT,
    SCHEMA_VERSION,
    ENGINE_ID,
)

__version__ = "1.0.0"
__constitution_articles__ = ("Article 20", "Article 21", "Article 100")
