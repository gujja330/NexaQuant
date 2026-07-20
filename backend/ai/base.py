"""Base contract for every AI agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class AgentOutput:
    """Every AI agent returns THIS shape — narrative + evidence + confidence + caveats."""
    agent:        str                     # short id, e.g. "data_quality"
    version:      str
    market:       str                     # "india" | "usa" | "global"
    asof:         date
    headline:     str                     # one-line summary
    narrative:    str                     # multi-paragraph explanation
    findings:     list[dict] = field(default_factory=list)     # structured findings
    evidence:     dict = field(default_factory=dict)           # exact inputs used
    citations:    list[str] = field(default_factory=list)      # producer paths / rows
    confidence:   float = 1.0             # 0..1
    caveats:      list[str] = field(default_factory=list)
    determinism:  str = "template"        # "template" | "llm-cached" — for future upgrade
