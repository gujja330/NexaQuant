"""Load published equity market caps from the dated NSE press report."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import requests

from backend.shared.atomic_io import write_text_atomic

PRESS_ARCHIVE = "/archives/equities/bhavcopy/pr/"
SCHEMA = "nse.equity.mcap.press.v1"


def artifact(root: Path, session: str) -> Path:
    return root / "india" / "reports" / "nse_market_cap" / f"{session}.json"


def refresh(root: Path, session: str) -> Path:
    output = artifact(root, session)
    if output.is_file():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing.get("schema") == SCHEMA and existing.get("asof") == session and existing.get("rows"):
            return output
    day = date.fromisoformat(session)
    failures = []
    for host in ("archives.nseindia.com", "nsearchives.nseindia.com"):
        url = f"https://{host}{PRESS_ARCHIVE}PR{day:%d%m%y}.zip"
        try:
            response = requests.get(url, timeout=(10, 35), headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            break
        except requests.RequestException as error:
            failures.append(str(error))
    else:
        raise RuntimeError(f"NSE same-session MCAP archive unavailable for {session}: {failures}")
    caps = {}
    with ZipFile(io.BytesIO(response.content)) as archive:
        member = next(n for n in archive.namelist() if n.lower() == f"mcap{day:%d%m%Y}.csv")
        with archive.open(member) as stream:
            rows = csv.DictReader(io.TextIOWrapper(stream, encoding="latin1"))
            rows.fieldnames = [name.strip() for name in rows.fieldnames]
            for row in rows:
                category = row["Category"].strip()
                if row["Series"].strip() != "EQ" or category not in {"Listed", "Permitted"}:
                    continue
                if datetime.strptime(row["Trade Date"].strip(), "%d %b %Y").date() != day:
                    raise RuntimeError(f"NSE market-cap archive contains a mismatched trade date: {row['Trade Date']}")
                if row["Last Trade Date"].strip() != row["Trade Date"].strip():
                    continue
                symbol = row["Symbol"].strip()
                count = Decimal(row["Issue Size"].strip() or "0")
                close = Decimal(row["Close Price/Paid up value(Rs.)"].strip() or "0")
                cap = Decimal(row["Market Cap(Rs.)"].strip() or "0")
                if all(value.is_finite() and value > 0 for value in (count, close, cap)):
                    if symbol in caps:
                        raise RuntimeError(f"NSE MCAP report contains duplicate EQ symbol: {symbol}")
                    caps[symbol] = {"issued_shares": int(count), "close": float(close),
                                    "market_cap_inr": float(cap), "nse_category": category}
    if not caps:
        raise RuntimeError(f"NSE files contain no same-session equity market caps for {session}")
    output.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(output, json.dumps({"schema": SCHEMA, "asof": session, "source": [{
        "url": url, "member": member, "sha256": hashlib.sha256(response.content).hexdigest(),
    }], "rows": caps}, indent=2) + "\n")
    return output


if __name__ == "__main__":
    from scripts.check_data_freshness import completed_nse_session

    print(refresh(Path.cwd(), completed_nse_session().isoformat()))
