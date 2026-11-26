"""Learning corpus — append-only parquet ledger of closed recommendations.

Natural key: (market, ticker, rec_asof). Append-only. Once a LearningRow
lands with the (market, ticker, rec_asof) tuple, future runs skip that
tuple even if the outcome would recompute — the ORIGINAL close is
what walk-forward needs to reproduce.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from backend.learning.types import LearningRow
from backend.shared.atomic_io import write_bytes_atomic


CORPUS_FILE = "learning_corpus.parquet"
REC_HISTORY_FILE = "recommendation_history.parquet"


def corpus_path(repo_root: Path, market: str) -> Path:
    if market == "usa":
        return Path(repo_root) / "usa" / "reports" / CORPUS_FILE
    return Path(repo_root) / "reports" / CORPUS_FILE


def rec_history_path(repo_root: Path, market: str) -> Path:
    if market == "usa":
        return Path(repo_root) / "usa" / "reports" / REC_HISTORY_FILE
    return Path(repo_root) / "reports" / REC_HISTORY_FILE


def read_corpus(repo_root: Path, market: str) -> pd.DataFrame:
    p = corpus_path(repo_root, market)
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def corpus_asof(corpus: pd.DataFrame, asof) -> pd.DataFrame:
    """The corpus as it was knowable on `asof`.

    CEO 2026-11-03 · a learning corpus row becomes knowable when its
    position CLOSED, so the cut is `close_asof <= asof`. Without it,
    LearningEngine.run(asof=...) reported statistics, calibration and
    failure clusters computed from outcomes that had not happened yet -
    `run(asof=2020-01-01)` was returning rows closed in late 2026.

    Legacy rows are eligible only when the original recommendation date
    and persisted observed duration establish a valid close date.
    """
    if corpus is None or corpus.empty:
        return pd.DataFrame() if corpus is None else corpus
    cut = pd.Timestamp(str(asof)[:10])
    explicit = corpus.get("close_asof", pd.Series(pd.NA, index=corpus.index))
    closed = pd.to_datetime(explicit, errors="coerce")
    if {"rec_asof", "horizon_days", "horizon_close_date"}.issubset(corpus.columns):
        # Legacy rows saved the scheduled date, but horizon_days counted
        # through the actual price observation, including any weekend gap.
        rec_dates = pd.to_datetime(corpus["rec_asof"], errors="coerce")
        days = pd.to_numeric(corpus["horizon_days"], errors="coerce")
        valid_days = days.where(days.between(1, 36500) & days.mod(1).eq(0))
        observed = rec_dates + pd.to_timedelta(valid_days, unit="D")
        scheduled = pd.to_datetime(corpus["horizon_close_date"], errors="coerce")
        closed = closed.where(explicit.notna(), observed.where(observed >= scheduled))
    return corpus[closed.notna() & (closed <= cut)]


def _row_to_dict(row: LearningRow) -> dict:
    """Serialise to a parquet-friendly dict.

    Empty dict fields would confuse pyarrow (no struct schema to infer),
    so we JSON-encode dict/list fields as strings. Downstream reads can
    json.loads() them.
    """
    d = asdict(row)
    d["rec_asof"] = row.rec_asof.isoformat()
    d["horizon_close_date"] = row.horizon_close_date.isoformat()
    d["close_asof"] = d["horizon_close_date"]
    # JSON-encode complex fields for parquet compatibility
    for k in ("feature_attribution", "model_attribution", "model_stamp_at_rec"):
        d[k] = json.dumps(d.get(k) or {}, default=str)
    for k in ("top_models", "top_features"):
        d[k] = json.dumps(d.get(k) or [], default=str)
    return d


def append_corpus(repo_root: Path, market: str,
                    new_rows: list[LearningRow]) -> tuple[Path, int]:
    """Append LearningRow list to the corpus. Dedupe on natural key.

    Returns (path, n_new_rows_actually_added).
    """
    if not new_rows:
        p = corpus_path(repo_root, market)
        return p, 0

    p = corpus_path(repo_root, market)
    p.parent.mkdir(parents=True, exist_ok=True)

    keys = ["market", "ticker", "rec_asof"]
    df_new = pd.DataFrame([_row_to_dict(r) for r in new_rows]).drop_duplicates(keys)
    if p.exists():
        df_old = pd.read_parquet(p)
        df_new = df_new.loc[~pd.MultiIndex.from_frame(df_new[keys]).isin(
            pd.MultiIndex.from_frame(df_old[keys])
        )]
        if df_new.empty:
            return p, 0
        combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        combined = df_new
    ordered = combined.sort_values(["market", "rec_asof", "ticker"])
    write_bytes_atomic(p, ordered.to_parquet(index=False))
    return p, int(len(df_new))


def load_recommendation_history(repo_root: Path, market: str) -> pd.DataFrame:
    """Load the historical recommendation ledger (append-only, parquet).

    In production this is written by the Recommendation Engine each day.
    Absent → empty DataFrame — that's honest (no recs yet).
    """
    p = rec_history_path(repo_root, market)
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)
