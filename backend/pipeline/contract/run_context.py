"""RUN_ID + ASOF · the identity every artifact in a run carries.

    AEGIS-2026-09-09-INDIA-0702

WHY AN EXPLICIT RUN IDENTITY
-----------------------------
On 2026-09-09 the question "was today's data actually today's data?" took
two hours to answer, because nothing tied a workbook row back to the
snapshot that produced it. Each stage read "the latest" of whatever it
needed, so lineage had to be reconstructed by inspecting file mtimes.

With a run identity, the answer is a lookup. Where did this stock come
from, which snapshot scored it, and where did every other stock in the
universe end up - all answerable mechanically.

THE ASOF RULE
-------------
`requested_asof` is chosen ONCE, at the top of the run, and every stage is
handed it. A stage may not decide for itself which date it is working on.
That single rule removes the entire class of failure where one stage
silently works on a different day than its neighbour.
"""
from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.pipeline.contract.run_context.v1"

MARKETS = ("india", "usa")

# Where a run's lineage lives. One directory per run · never overwritten.
LINEAGE_DIR = "reports/context/lineage"


def new_run_id(market: str, asof: str, when: Optional[datetime] = None) -> str:
    w = when or datetime.now(timezone.utc)
    return "AEGIS-%s-%s-%s" % (str(asof)[:10], market.upper(),
                               w.strftime("%H%M"))


@dataclass
class StageContract:
    """The machine-readable receipt one stage hands the next."""
    stage: str = ""
    run_id: str = ""
    market: str = ""
    input_asof: Optional[str] = None
    output_asof: Optional[str] = None
    row_count: int = 0
    ticker_count: int = 0
    expected_ticker_count: int = 0
    coverage_pct: Optional[float] = None
    missing_count: int = 0
    duplicate_count: int = 0
    source_timestamp: Optional[str] = None
    schema_fingerprint: Optional[str] = None
    upstream_run_id: Optional[str] = None
    status: str = "PENDING"          # PASS | BLOCK | SKIP | PENDING
    failures: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)
    elapsed_s: float = 0.0

    def block(self, code: str, message: str) -> "StageContract":
        """Record a hard failure · the run stops at this stage."""
        self.status = "BLOCK"
        self.failures.append({"code": code, "message": message})
        return self

    def ok(self) -> "StageContract":
        if self.status != "BLOCK":
            self.status = "PASS"
        return self

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


@dataclass
class RunContext:
    """One market, one as-of, one identity, carried through every stage."""
    market: str
    requested_asof: str
    run_id: str = ""
    started_utc: str = ""
    host: str = ""
    trigger: str = "manual"          # manual | scheduled | ci
    root: Optional[Path] = None
    contracts: list = field(default_factory=list)

    def __post_init__(self):
        self.market = self.market.lower()
        self.requested_asof = str(self.requested_asof)[:10]
        if not self.run_id:
            self.run_id = new_run_id(self.market, self.requested_asof)
        if not self.started_utc:
            self.started_utc = datetime.now(timezone.utc).isoformat(
                timespec="seconds")
        if not self.host:
            try:
                self.host = socket.gethostname()
            except Exception:
                self.host = "unknown"

    # ── stage plumbing ──────────────────────────────────────────────────
    def stage(self, name: str) -> StageContract:
        c = StageContract(stage=name, run_id=self.run_id, market=self.market,
                          input_asof=self.requested_asof)
        return c

    def record(self, c: StageContract) -> StageContract:
        self.contracts.append(c)
        return c

    def get(self, name: str) -> Optional[StageContract]:
        for c in self.contracts:
            if c.stage == name:
                return c
        return None

    # ── the fail-closed rule ────────────────────────────────────────────
    def upstream_ok(self, *required: str) -> Optional[str]:
        """None when every named upstream stage passed · else the reason.

        This is the whole contract in one method. A stage calls it before
        doing any work, and a missing or blocked upstream means it does
        not run at all - rather than running on whatever happens to be on
        disk, which is what produced a September workbook from July data.
        """
        for name in required:
            c = self.get(name)
            if c is None:
                return "upstream stage %r did not run" % name
            if c.status == "BLOCK":
                codes = ", ".join(f["code"] for f in c.failures) or "unknown"
                return "upstream stage %r BLOCKED (%s)" % (name, codes)
            if c.status != "PASS":
                return "upstream stage %r is %s" % (name, c.status)
        return None

    @property
    def blocked(self) -> bool:
        return any(c.status == "BLOCK" for c in self.contracts)

    @property
    def first_failure(self) -> Optional[dict]:
        for c in self.contracts:
            if c.status == "BLOCK" and c.failures:
                return {"stage": c.stage, **c.failures[0]}
        return None

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "market": self.market,
            "requested_asof": self.requested_asof,
            "started_utc": self.started_utc,
            "host": self.host,
            "trigger": self.trigger,
            "blocked": self.blocked,
            "first_failure": self.first_failure,
            "stages": [asdict(c) for c in self.contracts],
        }

    def emit(self) -> Optional[Path]:
        if self.root is None:
            return None
        p = (Path(self.root) / LINEAGE_DIR
             / ("%s.json" % self.run_id.replace(":", "")))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, default=str),
                     encoding="utf-8")
        # A stable pointer to the latest run for this market.
        latest = Path(self.root) / LINEAGE_DIR / ("latest_%s.json" % self.market)
        latest.write_text(json.dumps(self.to_dict(), indent=2, default=str),
                          encoding="utf-8")
        return p


def load_latest(root: Path, market: str) -> Optional[dict]:
    p = Path(root) / LINEAGE_DIR / ("latest_%s.json" % market.lower())
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def resolve_asof(explicit: Optional[str] = None) -> str:
    """The ONE place a run's as-of is decided.

    Stages are handed this value; none of them may pick their own. An
    explicit override exists for replay, and it is always recorded in the
    lineage so a replayed run can never be mistaken for a live one.
    """
    if explicit:
        return str(explicit)[:10]
    env = os.environ.get("AEGIS_ASOF")
    if env:
        return str(env)[:10]
    return date.today().isoformat()
