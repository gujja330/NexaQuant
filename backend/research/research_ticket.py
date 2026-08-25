# backend/research/research_ticket.py
"""AEGIS · Sprint M · Phase D · Research Ticket System (CEO Part 20).

File-based governance workflow. Any research finding that meets
Statistical Discipline (N ≥ 20) can be filed as a Research Ticket.

Ticket path: reports/research/tickets/RT-{YYYY}-{NNN}.md
Ticket index: reports/research/tickets/INDEX.json

Ticket schema (mandatory fields):
  - id · RT-2026-025
  - finding · one-line summary
  - evidence · N, expectancy, PF, sample details
  - hypothesis · what change we'd make
  - required_validation · walk-forward criteria
  - status · OPEN / VALIDATING / APPROVED / REJECTED / IMPLEMENTED
  - created_utc · timestamp
  - impact_score · 0-10 · CEO uses to rank

Constitutional invariant: NO production change without a ticket
promoted to APPROVED + walk-forward validated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.research_ticket.v1.20260825"

VALID_STATUSES = {"OPEN", "VALIDATING", "APPROVED", "REJECTED", "IMPLEMENTED"}


@dataclass
class ResearchTicket:
    id: str
    finding: str
    evidence: dict                    # {n, expectancy_pct, profit_factor, ...}
    hypothesis: str
    required_validation: str
    status: str                       # OPEN / VALIDATING / APPROVED / REJECTED
    created_utc: str
    impact_score: float               # 0-10
    market: str = ""
    tags: list = field(default_factory=list)
    ceo_note: str = ""


def _tickets_dir(root: Path) -> Path:
    p = root / "reports" / "research" / "tickets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _next_id(root: Path, year: Optional[int] = None) -> str:
    from datetime import date as _d
    yr = year or _d.today().year
    d = _tickets_dir(root)
    existing = sorted(d.glob(f"RT-{yr}-*.md"))
    if not existing: return f"RT-{yr}-001"
    last = existing[-1].stem
    try:
        n = int(last.split("-")[-1])
        return f"RT-{yr}-{n+1:03d}"
    except Exception:
        return f"RT-{yr}-{len(existing)+1:03d}"


def _render_markdown(t: ResearchTicket) -> str:
    lines = [
        f"# {t.id} · {t.finding}",
        "",
        f"- **Status**: {t.status}",
        f"- **Market**: {t.market or 'both'}",
        f"- **Impact score**: {t.impact_score}/10",
        f"- **Created**: {t.created_utc}",
        f"- **Tags**: {', '.join(t.tags) if t.tags else '—'}",
        "",
        "## Evidence",
    ]
    for k, v in (t.evidence or {}).items():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "## Hypothesis",
        t.hypothesis,
        "",
        "## Required validation",
        t.required_validation,
        "",
        "## CEO note",
        t.ceo_note or "_(pending review)_",
    ]
    return "\n".join(lines)


def file_ticket(root: Path, *, finding: str, evidence: dict,
                hypothesis: str, required_validation: str,
                impact_score: float, market: str = "",
                tags: Optional[list] = None) -> ResearchTicket:
    """Create + persist a new Research Ticket.
    Raises if N-threshold guard (Statistical Discipline) blocks."""
    from backend.research.statistical_guard import assert_ticket_allowed
    n = evidence.get("n", 0) or 0
    assert_ticket_allowed(n)
    if impact_score < 0 or impact_score > 10:
        raise ValueError("impact_score must be 0-10")
    ticket = ResearchTicket(
        id=_next_id(root),
        finding=finding, evidence=evidence,
        hypothesis=hypothesis,
        required_validation=required_validation,
        status="OPEN",
        created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        impact_score=impact_score,
        market=market.lower(),
        tags=list(tags or []),
    )
    md_path = _tickets_dir(root) / f"{ticket.id}.md"
    md_path.write_text(_render_markdown(ticket), encoding="utf-8")
    _refresh_index(root)
    return ticket


def _refresh_index(root: Path) -> Path:
    """Rebuild reports/research/tickets/INDEX.json from all tickets."""
    d = _tickets_dir(root)
    tickets: list = []
    for f in sorted(d.glob("RT-*.md")):
        try:
            _content = f.read_text(encoding="utf-8")
            # Parse minimal fields
            _id = _content.splitlines()[0].replace("# ","").split(" · ")[0]
            _status = "OPEN"; _impact = 0.0; _market = ""
            for line in _content.splitlines():
                if "**Status**:" in line:
                    _status = line.split(":", 1)[1].strip()
                elif "**Impact score**:" in line:
                    try:
                        _impact = float(line.split(":", 1)[1].strip().split("/")[0])
                    except Exception:
                        _impact = 0.0
                elif "**Market**:" in line:
                    _market = line.split(":", 1)[1].strip()
            tickets.append({
                "id": _id, "status": _status,
                "impact_score": _impact, "market": _market,
                "path": f.name,
            })
        except Exception:
            continue
    # Sort by impact desc
    tickets.sort(key=lambda t: -t["impact_score"])
    idx_p = d / "INDEX.json"
    idx_p.write_text(json.dumps({
        "engine": SCHEMA_FINGERPRINT,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_tickets": len(tickets),
        "by_status": {
            s: sum(1 for t in tickets if t["status"] == s)
            for s in VALID_STATUSES
        },
        "tickets": tickets,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return idx_p


def load_top_tickets(root: Path, n: int = 10) -> list:
    """Return top-N tickets ranked by impact score."""
    idx_p = _tickets_dir(root) / "INDEX.json"
    if not idx_p.exists():
        _refresh_index(root)
    try:
        d = json.loads(idx_p.read_text(encoding="utf-8"))
        return d.get("tickets", [])[:n]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────
# Auto-file tickets from attribution findings
# ─────────────────────────────────────────────────────────────────
def auto_file_from_attribution(root: Path, market: str,
                               attribution_report) -> list:
    """Read AttributionMatrixReport findings and file tickets for the
    ones that meet N-threshold. Skips (observation-only) findings."""
    filed = []
    # C22 · Cap × Sector × Runner triples with N ≥ 20 and negative expectancy
    for cell in attribution_report.cap_sector_runner_matrix:
        n = cell["metrics"]["n"]
        exp = cell["metrics"]["expectancy_pct"]
        if n < 20: continue
        if exp >= 0: continue     # only file for losing combos
        try:
            t = file_ticket(
                root,
                finding=f"{cell['key']} is loss-making · expectancy {exp:+.2f}%",
                evidence={
                    "n": n,
                    "expectancy_pct": exp,
                    "profit_factor": cell["metrics"]["profit_factor"],
                    "win_rate_pct": cell["metrics"]["win_rate_pct"],
                    "avg_drawdown_pct": cell["metrics"]["avg_drawdown_pct"],
                },
                hypothesis=(f"Reduce or block {cell['key']} entries · "
                            f"expectancy is negative over {n} samples · "
                            f"walk-forward likely confirms."),
                required_validation=(
                    "walk-forward on last 90 days with veto on this combo · "
                    "compare cumulative P&L with vs without · N ≥ 20 required."),
                impact_score=min(10.0, abs(exp) * 2),
                market=market,
                tags=["cap-sector-runner", "negative-expectancy"],
            )
            filed.append(t.id)
        except ValueError:
            continue    # N-threshold blocked
    return filed
