"""Learning corpus — append-only parquet ledger of closed recommendations.

Natural key: (market, ticker, rec_asof). Append-only. Once a LearningRow
lands with the (market, ticker, rec_asof) tuple, future runs skip that
tuple even if the outcome would recompute — the ORIGINAL close is
what walk-forward needs to reproduce.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from backend.learning.types import LearningRow


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
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()


def corpus_asof(corpus: pd.DataFrame, asof) -> pd.DataFrame:
    """The corpus as it was knowable on `asof`.

    CEO 2026-11-03 · a learning corpus row becomes knowable when its
    position CLOSED, so the cut is `close_asof <= asof`. Without it,
    LearningEngine.run(asof=...) reported statistics, calibration and
    failure clusters computed from outcomes that had not happened yet -
    `run(asof=2020-01-01)` was returning rows closed in late 2026.

    Rows whose `close_asof` is missing or unparseable are EXCLUDED, not
    kept: an outcome with no close date cannot be shown to have been
    available, and keeping it would restore the leak for exactly the rows
    least able to justify themselves. A corpus without a `close_asof`
    column cannot be cut at all, so it is returned empty rather than
    whole, for the same reason.
    """
    if corpus is None or corpus.empty:
        return pd.DataFrame() if corpus is None else corpus
    if "close_asof" not in corpus.columns:
        return corpus.iloc[0:0]
    cut = pd.Timestamp(str(asof)[:10])
    closed = pd.to_datetime(corpus["close_asof"], errors="coerce")
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

    df_new = pd.DataFrame([_row_to_dict(r) for r in new_rows])
    if p.exists():
        try:
            df_old = pd.read_parquet(p)
            # Natural key dedup
            keys_old = set(zip(df_old["market"], df_old["ticker"], df_old["rec_asof"]))
            keys_new = set(zip(df_new["market"], df_new["ticker"], df_new["rec_asof"]))
            fresh_keys = keys_new - keys_old
            df_fresh = df_new[df_new.apply(
                lambda r: (r["market"], r["ticker"], r["rec_asof"]) in fresh_keys, axis=1)]
            combined = pd.concat([df_old, df_fresh], ignore_index=True) \
                          .sort_values(["market", "rec_asof", "ticker"]).reset_index(drop=True)
            combined.to_parquet(p, index=False)
            return p, int(len(df_fresh))
        except Exception:
            df_new.to_parquet(p, index=False)
            return p, int(len(df_new))
    df_new.to_parquet(p, index=False)
    return p, int(len(df_new))


def load_recommendation_history(repo_root: Path, market: str) -> pd.DataFrame:
    """Load the historical recommendation ledger (append-only, parquet).

    In production this is written by the Recommendation Engine each day.
    Absent → empty DataFrame — that's honest (no recs yet).
    """
    p = rec_history_path(repo_root, market)
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()
