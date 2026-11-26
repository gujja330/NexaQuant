"""Official NSE daily price-index archives for sector feeds with sparse vendor history."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from math import isfinite
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import requests

from global_intelligence.lib.schema import RawObservation
from scripts.check_data_freshness import completed_nse_session


SOURCE = "nse_index_archive.v1"
INDEX_NAMES = {
    "sector.india.financial_svc": "Nifty Financial Services",
    "sector.india.healthcare": "Nifty Healthcare Index",
    "sector.india.media": "Nifty Media",
}
URL = "https://archives.nseindia.com/content/indices/ind_close_all_{:%d%m%Y}.csv"
PRESS_URL = "https://archives.nseindia.com/archives/equities/bhavcopy/pr/PR{:%d%m%y}.zip"
PRESS_NAMES = dict(zip(INDEX_NAMES, ("NIFTY FIN SERVICE", "NIFTY HEALTHCARE", "NIFTY MEDIA")))


def _session_observations(session, code_sha):
    url = URL.format(session)
    response = requests.get(url, timeout=(6, 12), headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    frame = pd.read_csv(BytesIO(response.content))
    frame["Index Name"] = frame["Index Name"].str.strip()
    rows = []
    for key, name in INDEX_NAMES.items():
        index = frame.loc[frame["Index Name"] == name]
        if len(index) != 1:
            raise ValueError(f"missing or duplicate official index {name} for {session}")
        entry = index.iloc[0]
        if datetime.strptime(entry["Index Date"], "%d-%m-%Y").date() != session:
            raise ValueError(f"official archive date disagrees for {name}")
        close = float(entry["Closing Index Value"])
        if not isfinite(close) or close <= 0:
            raise ValueError(f"invalid official close for {name}")
        volume = pd.to_numeric(entry["Volume"], errors="coerce")
        rows.append(RawObservation(
            variable_key=key + ".close", asof_utc=session.strftime("%Y-%m-%dT00:00:00.000000Z"),
            value=close, unit="index_pts", source_id=SOURCE, code_sha=code_sha,
            source_row={"Open": float(entry["Open Index Value"]), "High": float(entry["High Index Value"]),
                        "Low": float(entry["Low Index Value"]), "Close": close,
                        "Volume": float(volume) if pd.notna(volume) else None},
            retrieval_url=url,
        ))
    return rows


def _press_observations(session, code_sha):
    url = PRESS_URL.format(session)
    response = requests.get(url, timeout=(6, 15), headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    name = f"pr{session:%d%m%Y}.csv"
    with ZipFile(BytesIO(response.content)) as archive:
        with archive.open(next(member for member in archive.namelist() if member.lower() == name)) as stream:
            frame = pd.read_csv(stream, encoding="latin1", skipinitialspace=True)
    frame = frame[frame["IND_SEC"].str.strip().eq("Y") & frame["MKT"].str.strip().eq("Y")]
    names = frame["SECURITY"].str.strip().str.upper()
    observations = []
    for key, name in PRESS_NAMES.items():
        record = frame.loc[names.eq(name)]
        if len(record) != 1:
            raise ValueError(f"missing or duplicate NSE press index {name} for {session}")
        row = record.iloc[0]
        values = {key: float(row[column]) for key, column in (
            ("Open", "OPEN_PRICE"), ("High", "HIGH_PRICE"), ("Low", "LOW_PRICE"), ("Close", "CLOSE_PRICE"),
        )}
        if any(not isfinite(value) or value <= 0 for value in values.values()):
            raise ValueError(f"invalid NSE press OHLC for {name}")
        observations.append(RawObservation(
            variable_key=key + ".close", asof_utc=session.strftime("%Y-%m-%dT00:00:00.000000Z"),
            value=values["Close"], unit="index_pts", source_id=SOURCE, code_sha=code_sha,
            source_row={**values, "Volume": None}, retrieval_url=url + f"#{session:%d%m%Y}",
        ))
    return observations


def fetch(root: Path, raw: pd.DataFrame, code_sha: str) -> tuple[list[RawObservation], dict]:
    """Backfill a bounded reference window, then collect new completed sessions only."""
    latest = completed_nse_session()
    bars = pd.read_parquet(root / "data/raw/india/NSEI_D1.parquet", columns=[])
    dates = sorted({day.date() for day in pd.to_datetime(bars.index) if day.date() <= latest})[-205:]
    if len(dates) < 200 or dates[-1] != latest:
        raise ValueError("Nifty reference calendar lacks the completed sessions for sector history")
    previous = {key: {} for key in INDEX_NAMES}
    if not raw.empty:
        source = raw.loc[raw["source_id"] == SOURCE]
        for record in source.itertuples():
            key = record.variable_key.removesuffix(".close")
            if key in previous:
                previous[key][pd.Timestamp(record.asof_utc).date()] = float(record.value)
    pending = [day for day in dates if any(day not in values for values in previous.values())]

    def fetch_session(day):
        try:
            return _session_observations(day, code_sha)
        except (requests.RequestException, ValueError, KeyError):
            try:
                return _press_observations(day, code_sha)
            except (requests.RequestException, ValueError, KeyError, StopIteration):
                return []

    with ThreadPoolExecutor(max_workers=6) as pool:
        new = [row for result in pool.map(fetch_session, pending) for row in result]
    for row in new:
        day = datetime.fromisoformat(row.asof_utc).date()
        previous[row.variable_key.removesuffix(".close")][day] = row.value
    for key, values in previous.items():
        if sum(day in values for day in dates) < 200 or latest not in values:
            raise ValueError(f"official NSE archive is incomplete for {INDEX_NAMES[key]}")
    return new, previous
