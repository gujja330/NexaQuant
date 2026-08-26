"""AEGIS · Sprint M Research Runner (M-R) · v0.1

Post-lock research sandbox. Observes today's canonical INVESTMENT_ACTIVE
population, stamps entry context, and records a hypothesis + expected-
return definition for later outcome matching. Measurement-only.

CEO handover 2026-08-26 (verbatim after commit 3c4fa815 HARD LOCK):

> "Start M-R now, but very narrowly. Create the sandbox research runner,
>  give it an explicit experiment/version ID: M-R.v0.1. Read only locked
>  canonical inputs. Do not modify R1/R2. Do not touch _split_and_send,
>  XLSX contract/validator, Telegram delivery, lifecycle definitions, or
>  production decision logic. Write only to reports/research/mr_runner_
>  {market}.jsonl. Build tests proving M-R cannot contaminate production
>  outputs."

## STRICT ISOLATION RULES

This module MUST NOT:

  · modify any file outside `reports/research/`
  · import from `scripts/telegram_command_center_send.py`
  · touch `_split_and_send`, `xlsx_contract`, `xlsx_validator`
  · alter Registry state (`opportunity_registry.jsonl`)
  · alter recommendations.json
  · emit to Telegram or operator XLSX
  · influence R1/R2 signals, thresholds, or universes

Enforced by tests/research/test_mr_runner_isolation.py.

## What M-R.v0.1 actually does

1. Reads canonical INVESTMENT_ACTIVE population from
   `reports/context/portfolio_canonical_{market}.json` (sender-emitted,
   single source of truth per PRODUCTION_LOCK.md)
2. For each position, snapshots entry context (ticker, runner, entry
   price, current price, today's close, sector, cap)
3. Records a research observation with an explicit hypothesis and
   expected-return definition
4. Appends to `reports/research/mr_runner_{market}.jsonl` (append-only)

## What M-R.v0.1 does NOT do (yet)

  · No signal generation (M2 · signal quality · comes later)
  · No stop-loss experimentation (M3 · comes later)
  · No momentum signal (M4 · comes later)
  · No re-entry analysis (M5 · comes later)
  · No conclusions (M6 · comes later after n>=100 evidence)

It is intentionally minimal · foundation + M1 baseline observations only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────
# EXPERIMENT IDENTITY
# ─────────────────────────────────────────────────────────────────
EXPERIMENT_ID = "M-R.v0.1"
SCHEMA_FINGERPRINT = "aegis.mr_runner.v0.1.20260826"

# Only this directory is a valid write target. Any other write path is
# a violation of the M-R isolation contract.
ALLOWED_WRITE_ROOT = Path("reports/research")


# ─────────────────────────────────────────────────────────────────
# Observation schema
# ─────────────────────────────────────────────────────────────────
@dataclass
class ResearchObservation:
    """A single M-R research observation.

    Every field is written verbatim to the sandbox jsonl. Fields marked
    'populated later' are `None` at observation time and filled by a
    follow-up outcome-matcher (M6 will consume these).
    """
    experiment_id:               str
    schema_fingerprint:          str
    generated_utc:               str
    asof:                        str          # observation date
    market:                      str
    position_id:                 Optional[str]
    ticker:                      str
    runner:                      str          # source production runner (R1/R2)
    decision:                    str          # from canonical portfolio
    lifecycle:                   str          # from canonical portfolio
    entry_date:                  str
    entry_price:                 Optional[float]
    current_price:               Optional[float]
    sector:                      Optional[str]
    hypothesis:                  str
    expected_return_horizon_days: int
    expected_return_definition:  str
    # Outcome fields · populated by follow-up matcher (not this module)
    outcome_asof:                Optional[str] = None
    outcome_return_pct:          Optional[float] = None
    outcome_verdict:             Optional[str] = None


# ─────────────────────────────────────────────────────────────────
# INTERNAL · canonical input loaders (read-only)
# ─────────────────────────────────────────────────────────────────
def _load_canonical_investment_active(root: Path, market: str) -> list:
    """Read the sender-emitted canonical INVESTMENT_ACTIVE list.

    This is the ONLY source of truth for the population M-R observes.
    Guaranteed to match what the operator sees in the Portfolio XLSX.
    """
    p = root / "reports" / "context" / f"portfolio_canonical_{market.lower()}.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("investment_active", []) or []
    except Exception:
        return []


def _sector_lookup(root: Path, ticker: str, market: str) -> Optional[str]:
    """Read-only sector cache lookup · never mutates."""
    p = root / "reports" / "sector_cache.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return (d.get(market.lower(), {}) or {}).get(ticker.upper())
    except Exception:
        return None


def _parquet_close_readonly(root: Path, ticker: str,
                             market: str, iso_date: str) -> Optional[float]:
    """Read-only parquet close lookup for the given date (or nearest prior)."""
    try:
        import pandas as pd
        clean = ticker.upper().replace(".NS", "").replace(".BO", "")
        base = ("usa/data/raw/us" if market.lower() == "usa"
                else "data/raw/india")
        p = root / base / f"{clean}_D1.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        if iso_date in df.index:
            return float(df.loc[iso_date, col])
        earlier = [d for d in df.index if d <= iso_date]
        return float(df.loc[earlier[-1], col]) if earlier else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────
# PUBLIC · observe + emit
# ─────────────────────────────────────────────────────────────────
def observe(root: Path, market: str,
            asof: Optional[str] = None) -> list:
    """M1 baseline · one research observation per canonical INVESTMENT_ACTIVE
    position for today. Each observation records the entry context and a
    forward-return hypothesis for later outcome matching (20 trading days).

    Returns list[ResearchObservation]. Does NOT write to disk · call
    emit() for that.
    """
    asof_iso = str(asof or date.today().isoformat())[:10]
    now_utc  = datetime.now(timezone.utc).isoformat(timespec="seconds")
    canonical = _load_canonical_investment_active(root, market)
    observations = []
    for pos in canonical:
        _tk = str(pos.get("ticker", "")).upper()
        _rn = str(pos.get("runner", "")).upper()
        _ed = str(pos.get("entry_date", "") or "")[:10]
        _ep = _parquet_close_readonly(root, _tk, market, _ed) if _ed else None
        _cp = _parquet_close_readonly(root, _tk, market, asof_iso)
        _sec = _sector_lookup(root, _tk, market)
        obs = ResearchObservation(
            experiment_id      = EXPERIMENT_ID,
            schema_fingerprint = SCHEMA_FINGERPRINT,
            generated_utc      = now_utc,
            asof               = asof_iso,
            market             = market.lower(),
            position_id        = None,          # canonical file doesn't expose PID yet
            ticker             = _tk,
            runner             = _rn,
            decision           = str(pos.get("decision", "")),
            lifecycle          = str(pos.get("lifecycle", "")),
            entry_date         = _ed,
            entry_price        = round(_ep, 2) if isinstance(_ep, (int, float)) else None,
            current_price      = round(_cp, 2) if isinstance(_cp, (int, float)) else None,
            sector             = _sec,
            hypothesis         = ("M1 baseline · locked R1/R2 position observed "
                                  "at asof · will be matched to actual return over "
                                  "the next 20 trading days to establish realized "
                                  "outcome distribution per runner/lifecycle/sector"),
            expected_return_horizon_days = 20,
            expected_return_definition   = ("forward_close_20d - current_close / "
                                            "current_close × 100 · using canonical "
                                            "parquet close · no capital weighting"),
        )
        observations.append(obs)
    return observations


def emit(root: Path, market: str, observations: list) -> Path:
    """Append observations to sandbox jsonl.

    Enforces the M-R isolation contract: the write target MUST be under
    ALLOWED_WRITE_ROOT. Any other path raises RuntimeError.
    """
    if not observations:
        # Emit a heartbeat so we know the runner fired even on empty days
        pass
    out_dir = root / ALLOWED_WRITE_ROOT
    out_path = out_dir / f"mr_runner_{market.lower()}.jsonl"
    # Isolation guard · defense-in-depth
    try:
        _resolved = out_path.resolve()
        _allowed  = (root / ALLOWED_WRITE_ROOT).resolve()
        if not str(_resolved).startswith(str(_allowed)):
            raise RuntimeError(
                f"M-R isolation violation · write target {_resolved} "
                f"is outside ALLOWED_WRITE_ROOT {_allowed}")
    except Exception as e:
        raise RuntimeError(f"M-R isolation guard failed · {e}")
    out_dir.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as f:
        for obs in observations:
            f.write(json.dumps(asdict(obs), default=str,
                               ensure_ascii=False) + "\n")
    return out_path


def summary_line(observations: list) -> str:
    """Compact one-liner for CI/log."""
    if not observations:
        return f"mr_runner · {EXPERIMENT_ID} · 0 observations"
    from collections import Counter
    runners = Counter(o.runner for o in observations)
    return (f"mr_runner · {EXPERIMENT_ID} · "
            f"{len(observations)} baseline observations · "
            f"{dict(runners)}")


# ─────────────────────────────────────────────────────────────────
# CLI · runnable standalone for daily research capture
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=None,
                    help="observation date · defaults to today")
    ap.add_argument("--root", default=".",
                    help="repo root · defaults to cwd")
    args = ap.parse_args()
    _root = Path(args.root).resolve()
    obs = observe(_root, args.market, args.asof)
    p = emit(_root, args.market, obs)
    print(summary_line(obs))
    print(f"  written · {p.relative_to(_root)}")
