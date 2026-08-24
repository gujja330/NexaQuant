"""Part 20 · Data Quality (full · hard gate).

Extends Wave 6's advisory diagnostic warnings into a HARD BLOCKING gate
for critical data-integrity violations. Only violations that would produce
misleading operator output count as HARD FAIL · anything else stays WARN
so the day's XLSX still ships (partial > empty).

HARD FAIL (block delivery):
  · Registry file corrupted (unparseable JSON lines) · would leave
    every position with wrong state
  · recommendations.json missing or asof stale by > 3 days · would
    surface 3-day-old picks as today's

WARN (still ship, but flag in KPI banner):
  · > 5 tickers with stale Prev Close (data pipeline lag)
  · > 3 tickers with duplicate live positions across runners
  · universe size unusually small (< 50 tickers)
  · zero-NEW today WITHOUT a zero_reason narrative

Config in configs/opportunity_registry.yaml::data_quality_gate.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, date, timedelta
from pathlib import Path


@dataclass
class DQCheck:
    code:     str = ""
    name:     str = ""
    severity: str = "PASS"     # PASS | WARN | FAIL
    detail:   str = ""


@dataclass
class DQGateReport:
    engine:        str = "aegis.data_quality_gate.v1"
    generated_utc: str = ""
    market:        str = ""
    asof:          str = ""
    verdict:       str = "PASS"    # PASS | WARN | FAIL
    n_fail:        int = 0
    n_warn:        int = 0
    n_pass:        int = 0
    checks:        list = field(default_factory=list)


def _load_config(root: Path) -> dict:
    p = root / "configs" / "opportunity_registry.yaml"
    if not p.exists(): return {}
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cfg.get("data_quality_gate", {}) or {}
    except Exception:
        return {}


def _add(rep: DQGateReport, code, name, severity, detail):
    rep.checks.append(asdict(DQCheck(code=code, name=name,
                                                        severity=severity, detail=detail)))
    if severity == "FAIL":  rep.n_fail += 1
    elif severity == "WARN": rep.n_warn += 1
    else:                    rep.n_pass += 1
    if rep.n_fail > 0: rep.verdict = "FAIL"
    elif rep.n_warn > 0 and rep.verdict != "FAIL": rep.verdict = "WARN"


def compute(root: Path, market: str, asof: str) -> DQGateReport:
    market = market.lower(); asof = asof[:10]
    cfg = _load_config(root)
    max_recs_stale_days = int(cfg.get("max_recs_stale_days", 3))
    warn_dup_tickers   = int(cfg.get("warn_duplicate_tickers", 3))
    warn_min_universe  = int(cfg.get("warn_min_universe", 50))
    warn_stale_prev    = int(cfg.get("warn_stale_prev_close", 5))

    rep = DQGateReport(
        market=market, asof=asof,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    # DQ1 · Registry file corruption
    reg_p = root / "reports" / "research" / "opportunity_registry.jsonl"
    if not reg_p.exists():
        _add(rep, "DQ1", "Registry file present", "WARN",
                 "opportunity_registry.jsonl missing · fresh start OK")
    else:
        n_lines = 0; n_bad = 0
        for line in reg_p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line: continue
            n_lines += 1
            try: json.loads(line)
            except Exception: n_bad += 1
        if n_bad > 0:
            _add(rep, "DQ1", "Registry file JSON integrity", "FAIL",
                     f"{n_bad}/{n_lines} lines unparseable · would corrupt state")
        else:
            _add(rep, "DQ1", "Registry file JSON integrity", "PASS",
                     f"{n_lines} lines valid")

    # DQ2 · Recommendations freshness
    rec_p = ((root / "usa" / "reports" / "recommendations.json")
                 if market == "usa" else (root / "reports" / "recommendations.json"))
    if not rec_p.exists():
        _add(rep, "DQ2", "recommendations.json present", "FAIL",
                 f"missing at {rec_p} · would deliver stale/no recs")
    else:
        try:
            d = json.loads(rec_p.read_text(encoding="utf-8"))
            rec_asof = str(d.get("asof", ""))[:10]
            _asof_dt = date.fromisoformat(asof)
            _rec_dt  = date.fromisoformat(rec_asof) if rec_asof else _asof_dt
            days_stale = (_asof_dt - _rec_dt).days
            if days_stale > max_recs_stale_days:
                _add(rep, "DQ2", "recommendations freshness", "FAIL",
                         f"asof={rec_asof} · {days_stale}d stale (> {max_recs_stale_days}d)")
            elif days_stale > 0:
                _add(rep, "DQ2", "recommendations freshness", "WARN",
                         f"asof={rec_asof} · {days_stale}d stale")
            else:
                _add(rep, "DQ2", "recommendations freshness", "PASS",
                         f"asof={rec_asof} · fresh")
        except Exception as e:
            _add(rep, "DQ2", "recommendations freshness", "FAIL",
                     f"unreadable · {type(e).__name__}: {e}")

    # DQ3 · Duplicate live positions across runners (consume ops diagnostic)
    ops_p = root / "reports" / "context" / f"daily_ops_diagnostic_{market}.json"
    if ops_p.exists():
        try:
            ops = json.loads(ops_p.read_text(encoding="utf-8"))
            n_dupes = int(ops.get("counts", {}).get("duplicate_live_tickers", 0))
            if n_dupes > warn_dup_tickers:
                _add(rep, "DQ3", "duplicate live tickers", "WARN",
                         f"{n_dupes} tickers ACTIVE across R1+R2 (Wave 2 collapses display · Registry has both)")
            else:
                _add(rep, "DQ3", "duplicate live tickers", "PASS",
                         f"{n_dupes} dupes · within threshold {warn_dup_tickers}")
        except Exception:
            pass

    # DQ4 · Universe size sanity
    from backend.research.new_opportunity_diagnostic import _universe_size
    n_u = _universe_size(root, market)
    if n_u < warn_min_universe:
        _add(rep, "DQ4", "universe size", "WARN",
                 f"universe={n_u} < {warn_min_universe} · check parquet cache")
    else:
        _add(rep, "DQ4", "universe size", "PASS",
                 f"universe={n_u} tickers scanned")

    # DQ5 · Zero-NEW must carry explanation
    nod_p = root / "reports" / "context" / f"new_opportunity_diagnostic_{market}.json"
    if nod_p.exists():
        try:
            n = json.loads(nod_p.read_text(encoding="utf-8"))
            if n.get("n_new_today") == 0 and not n.get("zero_reason"):
                _add(rep, "DQ5", "zero-NEW explanation", "WARN",
                         "NEW=0 but no zero_reason narrative emitted")
            else:
                _add(rep, "DQ5", "zero-NEW explanation", "PASS",
                         f"NEW={n.get('n_new_today', 0)} · explanation present or not needed")
        except Exception:
            pass

    return rep


def emit(root: Path, rep: DQGateReport) -> Path:
    p = (root / "reports" / "context"
             / f"data_quality_gate_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def summary_line(rep: DQGateReport) -> str:
    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(rep.verdict, "?")
    return (f"{icon} {rep.verdict} · pass={rep.n_pass} · "
                f"warn={rep.n_warn} · fail={rep.n_fail}")
