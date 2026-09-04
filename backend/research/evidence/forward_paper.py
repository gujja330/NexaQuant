"""Section D · Forward Paper / Shadow Engine.

Freeze the candidate. Record daily observations. Mature outcomes at 5/10/20/60d.
Never retune during forward collection.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional


MATURITY_HORIZONS_DAYS = (5, 10, 20, 60)


@dataclass(frozen=True)
class FrozenCandidate:
    """A candidate frozen for forward paper/shadow. Never modified after freeze."""
    item_id: str
    market: str
    frozen_utc: str
    parameters_hash: str      # SHA-256 of the frozen parameter set
    parameters: dict
    signal_definition: str    # code path or SHA identifying signal logic
    horizon_days: int
    universe_snapshot: list   # tickers eligible at freeze time
    frozen_by_commit: str

    def to_dict(self) -> dict:
        return asdict(self)


def _hash_parameters(params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def freeze_candidate(root: Path, item_id: str, market: str,
                      parameters: dict, signal_definition: str,
                      horizon_days: int, universe: list[str]) -> FrozenCandidate:
    """Freeze a candidate for forward observation. Immutable · overwrite forbidden."""
    freeze_dir = root / "reports" / "research" / "forward_validation" / item_id / market
    freeze_dir.mkdir(parents=True, exist_ok=True)
    freeze_p = freeze_dir / "frozen_candidate.json"
    if freeze_p.exists():
        # Refuse re-freeze · would retroactively change what was tested
        return FrozenCandidate(**json.loads(freeze_p.read_text(encoding="utf-8")))
    from backend.research.evidence.evidence_log import _git_commit
    fc = FrozenCandidate(
        item_id=item_id, market=market,
        frozen_utc=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        parameters_hash=_hash_parameters(parameters),
        parameters=parameters,
        signal_definition=signal_definition,
        horizon_days=horizon_days,
        universe_snapshot=list(universe),
        frozen_by_commit=_git_commit(root),
    )
    freeze_p.write_text(json.dumps(fc.to_dict(), indent=2, default=str), encoding="utf-8")
    return fc


def append_daily_observation(root: Path, item_id: str, market: str,
                              asof: str, ticker: str,
                              candidate_signal: float | None,
                              r2_signal: float | None,
                              comparator_signal: float | None) -> None:
    """Append one row to the daily ledger. Never overwrite prior observations."""
    ledger_p = (root / "reports" / "research" / "forward_validation" /
                 item_id / market / "daily_ledger.jsonl")
    ledger_p.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "asof": asof, "ticker": ticker,
        "candidate_signal": candidate_signal,
        "r2_signal": r2_signal,
        "comparator_signal": comparator_signal,
        "logged_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "matured": {},          # populated by mature_outcomes()
    }
    with open(ledger_p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def load_daily_ledger(root: Path, item_id: str, market: str) -> list[dict]:
    ledger_p = (root / "reports" / "research" / "forward_validation" /
                 item_id / market / "daily_ledger.jsonl")
    if not ledger_p.exists(): return []
    out = []
    for line in ledger_p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


def compute_matured_return(root: Path, market: str, ticker: str,
                            entry_date: str, horizon_days: int) -> Optional[float]:
    """Return realized % return over horizon · None if not matured yet or missing data."""
    import pandas as pd
    from backend.research._paths import price_parquet_path
    try:
        p = price_parquet_path(root, market, ticker)
        if not p or not p.exists(): return None
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        entry_dt = pd.Timestamp(entry_date)
        after = df[df.index >= entry_dt]
        if after.empty: return None
        entry_price = float(after.iloc[0]["close"])
        if entry_price <= 0: return None
        # Maturity requires horizon calendar days elapsed AND price bar available
        target_dt = after.index[0] + pd.Timedelta(days=int(horizon_days * 1.5))
        exit_slice = df[df.index >= target_dt]
        if exit_slice.empty: return None       # not matured
        exit_price = float(exit_slice.iloc[0]["close"])
        return (exit_price / entry_price - 1.0) * 100.0
    except Exception: return None


def mature_outcomes(root: Path, item_id: str, market: str) -> dict:
    """Walk the ledger · fill matured returns for every horizon where possible.
    Returns summary · does NOT overwrite unmatured rows."""
    ledger = load_daily_ledger(root, item_id, market)
    if not ledger:
        return {"item_id": item_id, "market": market, "n_rows": 0}
    updated_rows = []
    n_newly_matured = {h: 0 for h in MATURITY_HORIZONS_DAYS}
    for row in ledger:
        matured = row.get("matured") or {}
        for h in MATURITY_HORIZONS_DAYS:
            key = f"{h}d"
            if key in matured: continue
            r = compute_matured_return(root, market, row["ticker"], row["asof"], h)
            if r is not None:
                matured[key] = round(r, 4)
                n_newly_matured[h] += 1
        row["matured"] = matured
        updated_rows.append(row)
    # Rewrite the ledger with matured fields filled · this is idempotent (never
    # changes an already-set matured value · only fills empties)
    ledger_p = (root / "reports" / "research" / "forward_validation" /
                 item_id / market / "daily_ledger.jsonl")
    with open(ledger_p, "w", encoding="utf-8") as f:
        for row in updated_rows:
            f.write(json.dumps(row) + "\n")
    total_matured = {h: sum(1 for r in updated_rows
                             if r.get("matured", {}).get(f"{h}d") is not None)
                      for h in MATURITY_HORIZONS_DAYS}
    return {
        "item_id": item_id, "market": market,
        "n_rows": len(updated_rows),
        "n_newly_matured": {f"{h}d": n_newly_matured[h] for h in MATURITY_HORIZONS_DAYS},
        "n_total_matured": {f"{h}d": total_matured[h] for h in MATURITY_HORIZONS_DAYS},
    }
