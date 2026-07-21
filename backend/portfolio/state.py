"""Portfolio state — load prior, save current, append-only history."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from backend.portfolio.types import Position, PortfolioSnapshot


def _state_path(repo_root: Path, market: str) -> Path:
    if market == "usa":
        return Path(repo_root) / "usa" / "reports" / "portfolio_state.json"
    return Path(repo_root) / "reports" / "portfolio_state.json"


def _history_path(repo_root: Path, market: str) -> Path:
    if market == "usa":
        return Path(repo_root) / "usa" / "reports" / "portfolio_state_history.jsonl"
    return Path(repo_root) / "reports" / "portfolio_state_history.jsonl"


def _load_position(d: dict) -> Position:
    """Rebuild a Position from a serialised dict."""
    return Position(
        market=d.get("market", ""),
        ticker=d.get("ticker", ""),
        weight=float(d.get("weight", 0.0)),
        notional=float(d.get("notional", 0.0)),
        entry_date=d.get("entry_date", ""),
        entry_price=d.get("entry_price"),
        current_price=d.get("current_price"),
        days_held=int(d.get("days_held", 0)),
        action_source=d.get("action_source", ""),
        sector=d.get("sector", ""),
        stop_loss_pct=d.get("stop_loss_pct"),
        model_stamp=dict(d.get("model_stamp") or {}),
    )


def load_prior_state(repo_root: Path, market: str) -> PortfolioSnapshot | None:
    """Load yesterday's portfolio state, if it exists."""
    p = _state_path(repo_root, market)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    positions = [_load_position(pd) for pd in raw.get("positions", [])]
    return PortfolioSnapshot(
        market=raw.get("market", market),
        asof=date.fromisoformat(raw.get("asof")) if raw.get("asof") else date.today(),
        engine_version=raw.get("engine_version", "v1.0"),
        n_positions=int(raw.get("n_positions", len(positions))),
        total_weight=float(raw.get("total_weight", 0.0)),
        cash_pct=float(raw.get("cash_pct", 0.0)),
        cash_reserve_target=float(raw.get("cash_reserve_target", 0.05)),
        positions=positions,
        hhi=float(raw.get("hhi", 0.0)),
        effective_n=float(raw.get("effective_n", 0.0)),
        top_5_pct=float(raw.get("top_5_pct", 0.0)),
        per_sector_pct=dict(raw.get("per_sector_pct") or {}),
        n_sectors=int(raw.get("n_sectors", 0)),
        schema_fingerprint=raw.get("schema_fingerprint", ""),
        feature_set_version=raw.get("feature_set_version", ""),
        model_stamp=dict(raw.get("model_stamp") or {}),
        regime_at_construction=raw.get("regime_at_construction", "unknown"),
        notes=list(raw.get("notes") or []),
    )


def _snapshot_to_dict(snap: PortfolioSnapshot) -> dict:
    d = asdict(snap)
    d["asof"] = snap.asof.isoformat() if isinstance(snap.asof, date) else str(snap.asof)
    return d


def save_current_state(repo_root: Path, snap: PortfolioSnapshot) -> Path:
    """Overwrite the CURRENT state file (this is idempotent; history is append-only)."""
    p = _state_path(repo_root, snap.market)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_snapshot_to_dict(snap), indent=2, default=str), encoding="utf-8")
    return p


def append_state_history(repo_root: Path, snap: PortfolioSnapshot) -> Path:
    """Append TODAY's snapshot to the history ledger (append-only, walk-forward substrate)."""
    p = _history_path(repo_root, snap.market)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_snapshot_to_dict(snap), default=str) + "\n")
    return p
