"""P0 · Canonical Outcome Dataset builder.

One row per Position ID · immutable identity · frozen initial values ·
horizon returns · running extremes · terminal fields · sample-size tier.

Reads from:
  - reports/position_store/{market}/positions.json
  - usa/reports/position_store/usa/positions.json
  - reports/research/rank_history.jsonl (initial rank/conf/score snapshot)
  - reports/investability_{market}.json (initial investability snapshot)
  - reports/sector_cache.json
  - configs/india_universe_tiers.yaml
  - data/raw/india/*_D1.parquet (India price history)
  - usa/data/raw/us/*_D1.parquet (USA price history)
  - reports/telegram/aegis_history.xlsx (exit event log · fallback)

Writes to:
  - reports/research/outcome_dataset.parquet (canonical)
  - reports/research/outcome_dataset_summary.json (rollup + tiers)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from pathlib import Path


_HORIZONS = [1, 3, 5, 10, 17, 30, 60, 90]


def _load_yaml(p: Path) -> dict:
    import yaml
    if not p.exists(): return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _load_json(p: Path) -> dict | list:
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _positions(root: Path, market: str) -> dict:
    """Load position_store for market · returns {canonical_ticker: record}."""
    base = root / ("usa/reports" if market.lower() == "usa" else "reports")
    p = base / "position_store" / market.lower() / "positions.json"
    d = _load_json(p) or {}
    return d.get("positions") or {}


def _rank_history(root: Path) -> list:
    p = root / "reports" / "research" / "rank_history.jsonl"
    if not p.exists(): return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try: out.append(json.loads(line))
        except Exception: continue
    return out


def _investability(root: Path, market: str) -> dict:
    p = root / "reports" / f"investability_{market.lower()}.json"
    d = _load_json(p) or {}
    return {r["ticker"]: r for r in (d.get("results") or [])}


def _sector_cache(root: Path) -> dict:
    return _load_json(root / "reports" / "sector_cache.json") or {}


def _cap_class(ticker: str, market: str, largecap_set: set) -> str:
    if market.lower() == "usa":
        return "LargeCap"
    short = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
    return "LargeCap" if short in largecap_set else "MidCap"


def _parquet_df(root: Path, ticker: str, market: str):
    """Load parquet · returns DataFrame indexed by date string."""
    import pandas as pd
    short = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
    base = "usa/data/raw/us" if market.lower() == "usa" else "data/raw/india"
    p = root / base / f"{short}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        return df[[col]].rename(columns={col: "close"})
    except Exception:
        return None


def _price_at(df, target_date: str):
    """Return close on target_date · fallback to nearest earlier."""
    if df is None or df.empty: return None
    if target_date in df.index: return float(df.loc[target_date, "close"])
    earlier = [d for d in df.index if d <= target_date]
    return float(df.loc[earlier[-1], "close"]) if earlier else None


def _horizon_date(entry_iso: str, trading_days: int) -> str:
    """Return ISO date entry + trading_days (weekends skipped · holidays not)."""
    try:
        d = date.fromisoformat(entry_iso[:10])
    except (ValueError, TypeError):
        return entry_iso
    added = 0
    while added < trading_days:
        d += timedelta(days=1)
        if d.weekday() < 5: added += 1
    return d.isoformat()


def _find_earliest_rank(rank_hist: list, market: str, runner_key: str,
                                    ticker_bare: str) -> dict:
    """Return earliest rank_history entry for this (market, runner, ticker)."""
    entries = []
    for entry in rank_hist:
        if entry.get("market") != market.lower(): continue
        if entry.get("runner") != runner_key: continue
        t = str(entry.get("ticker") or "").replace(".NS","").replace(".BO","").upper()
        if t == ticker_bare.upper():
            entries.append(entry)
    if not entries: return {}
    entries.sort(key=lambda e: str(e.get("asof") or ""))
    return entries[0]


def _load_exit_events_index(root: Path) -> dict:
    """Index legacy exit observations by market, runner, ticker and entry date."""
    xlsx = root / "reports" / "telegram" / "aegis_history.xlsx"
    if not xlsx.exists(): return {}
    index = {}
    try:
        from openpyxl import load_workbook
        wb = load_workbook(xlsx, read_only=True)
        ws = wb["AEGIS Daily"] if "AEGIS Daily" in wb.sheetnames else wb.active
        h = [c.value for c in ws[1]]
        def col(name):
            try: return h.index(name) + 1
            except ValueError: return None
        c_ctry, c_run, c_tk, c_st, c_dt = col("Country"), col("Run_Type"), col("Ticker"), col("Status"), col("Date")
        c_entry_date = col("Recommended") or col("Entry Date")
        c_pnl, c_reason = col("Exit P&L %"), col("Exit Reason")
        # 2026-08-14 Sprint K Part 28 · also capture Alerts + Stop Loss so
        # P0 outcome dataset can attribute WHY the exit fired · never
        # reconstruct from XLSX again in downstream P1.
        c_alerts, c_stop = col("Alerts"), col("Stop Loss")
        if not all([c_ctry, c_run, c_tk, c_st, c_dt, c_entry_date]):
            wb.close(); return index
        # Binding risk signals · must match configs/priority_matrix.yaml
        _BINDING = ("EMERGENCY_EXIT", "PORTFOLIO_MAX_DD", "HARD_STOP",
                        "STOP_LOSS_HIT", "GAP_EXIT", "TRAILING_STOP_HIT",
                        "CRITICAL_DEEP_LOSS")
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[c_st - 1] != "EXIT": continue
            market = str(row[c_ctry - 1] or "").lower()
            runner = str(row[c_run - 1] or "")
            ticker = str(row[c_tk - 1] or "").upper()
            ticker = ticker.replace(".NS","").replace(".BO","")
            _alerts = str(row[c_alerts - 1] or "").upper() if c_alerts else ""
            # Detect which binding risk signal (if any) drove the exit
            _risk_state = next((s for s in _BINDING if s in _alerts), "CLEAN")
            entry_date = str(row[c_entry_date - 1] or "")[:10]
            exit_date = str(row[c_dt - 1] or "")[:10]
            if not entry_date or not exit_date or exit_date < entry_date:
                continue
            key = (market, runner, ticker, entry_date)
            prior = index.get(key)
            if prior and prior["exit_date"] <= exit_date:
                continue
            index[key] = {
                "exit_date":         exit_date,
                "exit_pnl":          row[c_pnl - 1] if c_pnl else None,
                "exit_reason":       row[c_reason - 1] if c_reason else None,
                "risk_state":        _risk_state,
                "stop_trigger_price": row[c_stop - 1] if c_stop else None,
            }
        wb.close()
    except Exception:
        pass
    return index


def _sample_tier(n: int, tiers: dict | list) -> str:
    entries = tiers.items() if isinstance(tiers, dict) else (
        (tier["label"], tier) for tier in tiers
    )
    for label, bounds in entries:
        ceiling = bounds.get("max")
        if n >= bounds["min"] and (ceiling is None or n <= ceiling):
            return label
    return "unknown"


@dataclass
class OutcomeRow:
    position_id:                  str
    country:                      str
    runner:                       str
    ticker:                       str
    sector:                       str
    cap:                          str
    initial_rank:                 int | None
    initial_confidence:           float | None
    initial_model_score:          float | None
    initial_investability:        float | None
    initial_investability_verdict: str
    entry_date:                   str
    entry_price:                  float | None
    current_price:                float | None
    current_perf_pct:             float | None
    max_gain_pct:                 float | None
    max_drawdown_pct:             float | None
    ret_1d_pct:                   float | None
    ret_3d_pct:                   float | None
    ret_5d_pct:                   float | None
    ret_10d_pct:                  float | None
    ret_17d_pct:                  float | None
    ret_30d_pct:                  float | None
    ret_60d_pct:                  float | None
    ret_90d_pct:                  float | None
    exit_date:                    str
    exit_price:                   float | None
    exit_pnl_pct:                 float | None
    exit_reason:                  str
    win_flag:                     bool | None   # None if open (per governance rule)
    lifecycle:                    str
    is_closed:                    bool
    # 2026-08-14 Sprint K Part 28 · Wave 6 · risk-state provenance for
    # Attribution + Learning. Captures WHY the position exited (which
    # binding risk signal fired · or "clean" if profit target / time
    # exit). Stored per position · immutable after close.
    risk_state:                   str = ""    # STOP_LOSS_HIT / HARD_STOP / CLEAN / etc.
    stop_trigger_price:           float | None = None
    # 2026-08-15 · Section 21 · preserve old {TKR}_{MKT}_{DATE} for migration.
    # Non-authoritative · reference-only field for correlating with rows
    # written before runner-specific position_id landed (commit b5cc3e29 +).
    legacy_position_id:           str = ""
    sample_tier_note:             str = ""


def build(root: Path, markets: tuple[str, ...] = ("india", "usa")) -> list:
    """Build canonical outcome rows from all sources · one per Position ID."""
    tiers_cfg = _load_yaml(root / "configs" / "outcome_dataset_schema.yaml")
    tiers = (tiers_cfg.get("sample_size_tiers") or [])

    india_tiers = _load_yaml(root / "configs" / "india_universe_tiers.yaml")
    largecap_set = set(india_tiers.get("largecap_tickers") or [])
    sector_cache = _sector_cache(root)
    rank_hist = _rank_history(root)

    rows = []
    today_iso = date.today().isoformat()
    exit_index = _load_exit_events_index(root)   # load XLSX ONCE

    for market in markets:
        positions = _positions(root, market)
        inv_map = _investability(root, market)
        market_sector = sector_cache.get(market.lower(), {})

        for canonical_ticker, pos in positions.items():
            ticker_bare = canonical_ticker.replace(".NS","").replace(".BO","").upper()
            entry_date = str(pos.get("first_seen_date") or "")[:10]
            entry_price = pos.get("first_seen_price")

            if not entry_date or not entry_price: continue

            df = _parquet_df(root, ticker_bare, market)
            current_price = _price_at(df, today_iso) if df is not None else None
            current_perf = None
            if entry_price and current_price and entry_price > 0:
                current_perf = round((current_price - entry_price) / entry_price * 100, 2)

            # Running max/min between entry and today
            max_gain = max_dd = None
            if df is not None:
                window = df[(df.index >= entry_date) & (df.index <= today_iso)]
                if not window.empty and entry_price:
                    highest = float(window["close"].max())
                    lowest = float(window["close"].min())
                    max_gain = round((highest - entry_price) / entry_price * 100, 2)
                    max_dd = round((lowest - entry_price) / entry_price * 100, 2)

            # Horizon returns
            horizon_returns = {}
            for h in _HORIZONS:
                target = _horizon_date(entry_date, h)
                if target > today_iso:
                    horizon_returns[h] = None
                    continue
                px = _price_at(df, target) if df is not None else None
                if px and entry_price and entry_price > 0:
                    horizon_returns[h] = round((px - entry_price) / entry_price * 100, 2)
                else:
                    horizon_returns[h] = None

            # Determine runner via rank_history · earliest entry sets runner
            # (rank_history stamps runner per emission)
            r1_earliest = _find_earliest_rank(rank_hist, market, "runner1", ticker_bare)
            r2_earliest = _find_earliest_rank(rank_hist, market, "runner2", ticker_bare)

            for runner_key, earliest, runner_label in [
                ("runner1", r1_earliest, "R1"),
                ("runner2", r2_earliest, "R2"),
            ]:
                if not earliest: continue

                inv = inv_map.get(ticker_bare) or inv_map.get(canonical_ticker) or {}
                sector = market_sector.get(ticker_bare, "") or "Unclassified"
                cap = _cap_class(ticker_bare, market, largecap_set)

                # Look for exit event (indexed lookup · O(1))
                exit_info = exit_index.get((market.lower(), runner_label, ticker_bare, entry_date), {})
                exit_date = exit_info.get("exit_date") or ""
                exit_price = _price_at(df, exit_date) if exit_date else None
                exit_pnl = exit_info.get("exit_pnl")
                if exit_price and entry_price and entry_price > 0 and not exit_pnl:
                    exit_pnl = round((exit_price - entry_price) / entry_price * 100, 2)

                is_closed = bool(exit_date and exit_price)
                # Governance rule: win_flag NULL for open positions
                win_flag = None if not is_closed else (
                    exit_pnl > 0 if isinstance(exit_pnl, (int, float)) else None
                )

                # Lifecycle
                if is_closed:
                    lifecycle = "CLOSED"
                elif entry_date == today_iso:
                    lifecycle = "NEW"
                else:
                    lifecycle = "ACTIVE"

                # 2026-08-15 · operator directive Section 1 · runner-specific
                # Position ID: {R}-{TKR}-{MKT}-{YYYYMMDD}-{sig6}. R1 and R2
                # are independent decision engines · same stock may legit-
                # imately be R1=EXIT and R2=HOLD · position_id must diverge.
                # Old format {TKR}_{MKT}_{YYYYMMDD} preserved in
                # legacy_position_id for migration mapping.
                import hashlib as _hashlib
                mkt_upper = "IND" if market.lower() == "india" else "USA"
                ds = entry_date.replace("-", "")
                _sig = _hashlib.sha256(
                    f"{runner_label}-{ticker_bare}-{mkt_upper}-{ds}".encode()
                ).hexdigest()[:6]
                position_id = f"{runner_label}-{ticker_bare}-{mkt_upper}-{ds}-{_sig}"
                legacy_position_id = f"{ticker_bare}_{mkt_upper}_{ds}"

                row = OutcomeRow(
                    position_id=position_id,
                    country=market.upper(),
                    runner=runner_label,
                    ticker=ticker_bare,
                    sector=sector,
                    cap=cap,
                    initial_rank=earliest.get("rank"),
                    initial_confidence=earliest.get("confidence"),
                    initial_model_score=earliest.get("model_score"),
                    initial_investability=inv.get("score"),
                    initial_investability_verdict=inv.get("verdict", ""),
                    entry_date=entry_date,
                    entry_price=round(float(entry_price), 2) if entry_price else None,
                    current_price=round(current_price, 2) if current_price else None,
                    current_perf_pct=current_perf,
                    max_gain_pct=max_gain,
                    max_drawdown_pct=max_dd,
                    ret_1d_pct=horizon_returns.get(1),
                    ret_3d_pct=horizon_returns.get(3),
                    ret_5d_pct=horizon_returns.get(5),
                    ret_10d_pct=horizon_returns.get(10),
                    ret_17d_pct=horizon_returns.get(17),
                    ret_30d_pct=horizon_returns.get(30),
                    ret_60d_pct=horizon_returns.get(60),
                    ret_90d_pct=horizon_returns.get(90),
                    exit_date=exit_date,
                    exit_price=round(exit_price, 2) if exit_price else None,
                    exit_pnl_pct=exit_pnl if isinstance(exit_pnl, (int, float)) else None,
                    exit_reason=str(exit_info.get("exit_reason") or ""),
                    win_flag=win_flag,
                    lifecycle=lifecycle,
                    is_closed=is_closed,
                    # Sprint K Part 28 · Wave 6 · risk-state provenance
                    risk_state=str(exit_info.get("risk_state") or ("CLEAN" if is_closed else "")),
                    stop_trigger_price=exit_info.get("stop_trigger_price"),
                    # 2026-08-15 · Section 21 migration reference
                    legacy_position_id=legacy_position_id,
                )
                rows.append(row)

    # Attach sample_tier_note per row · based on total count in row's runner
    from collections import Counter
    runner_counts = Counter(r.runner for r in rows)
    for r in rows:
        r.sample_tier_note = _sample_tier(runner_counts[r.runner], tiers)

    return rows


def build_india_lifecycle(root: Path) -> list[OutcomeRow]:
    """Measure the published India episode cohort using the canonical lifecycle."""
    from functools import lru_cache
    from math import isfinite

    from backend.delivery.lifecycle.canonical_daily_lifecycle import RT_REALIZED, load
    from backend.research.opportunity_registry import load_all

    lifecycle = load(root, "india")
    if not lifecycle or lifecycle.get("asof") != date.today().isoformat():
        raise ValueError("India P0 requires today's canonical lifecycle snapshot")
    data_day = lifecycle.get("market_data_asof")
    if not data_day:
        raise ValueError("India P0 requires a verified market data date")
    registry = {p.opportunity_id: p for group in load_all(root).values()
                for p in group if p.market == "india"}
    cohorts = [(row, False) for row in lifecycle["current"]]
    cohorts.extend((row, True) for row in lifecycle["exits"] if row["record_type"] == RT_REALIZED)
    load_bars = lru_cache(maxsize=256)(_parquet_df)
    tiers = _load_yaml(root / "configs" / "outcome_dataset_schema.yaml")["sample_size_tiers"]
    from collections import Counter

    counts = Counter(row["engine"] for row, _ in cohorts)
    rows = []
    for row, closed in cohorts:
        position_id = row["position_id"]
        episode = registry.get(position_id)
        if not episode or episode.created_date != row["entry_date"]:
            raise ValueError(f"India P0 episode lineage is unavailable for {position_id}")
        ticker, entry_day = row["ticker"], row["entry_date"]
        entry_price = row.get("entry_price")
        exit_day = row.get("exit_date", "") if closed else ""
        last_day = min(data_day, exit_day) if closed else min(data_day, row.get("market_data_asof") or data_day)
        frame = load_bars(root, ticker, "india")
        returns = {}
        gain = drawdown = None
        if frame is not None and entry_price and entry_price > 0:
            within = frame.sort_index().loc[entry_day:last_day, "close"].dropna()
            following = within.loc[within.index > entry_day]
            if not within.empty:
                gain = round((float(within.max()) / entry_price - 1) * 100, 2)
                drawdown = round((float(within.min()) / entry_price - 1) * 100, 2)
            for step in (1, 3, 5, 10, 17, 30, 60, 90):
                if len(following) >= step:
                    returns[step] = round((float(following.iloc[step - 1]) / entry_price - 1) * 100, 2)
        pnl = row.get("realized_pnl_pct") if closed else None
        rows.append(OutcomeRow(
            position_id=position_id, country="INDIA", runner=row["engine"],
            ticker=ticker, sector=row.get("sector") or "Unclassified",
            cap=row.get("size") or "Unclassified", initial_rank=episode.initial_rank,
            initial_confidence=row.get("entry_confidence_pct" if closed else "confidence_pct"),
            initial_model_score=episode.initial_score,
            initial_investability=None, initial_investability_verdict="UNAVAILABLE",
            entry_date=entry_day, entry_price=entry_price,
            current_price=None if closed else row.get("current_price"),
            current_perf_pct=None if closed else row.get("pnl_pct"),
            max_gain_pct=gain, max_drawdown_pct=drawdown,
            ret_1d_pct=returns.get(1), ret_3d_pct=returns.get(3), ret_5d_pct=returns.get(5),
            ret_10d_pct=returns.get(10), ret_17d_pct=returns.get(17), ret_30d_pct=returns.get(30),
            ret_60d_pct=returns.get(60), ret_90d_pct=returns.get(90),
            exit_date=exit_day, exit_price=row.get("exit_price") if closed else None,
            exit_pnl_pct=pnl, exit_reason=row.get("exit_reason") or "",
            win_flag=pnl > 0 if isinstance(pnl, (float, int)) and isfinite(pnl) else None,
            lifecycle="CLOSED" if closed else row["action"], is_closed=closed,
            risk_state=row.get("exit_trigger") or "",
            sample_tier_note=_sample_tier(counts[row["engine"]], tiers),
        ))
    if len({row.position_id for row in rows}) != len(rows):
        raise ValueError("India P0 encountered duplicate lifecycle episode IDs")
    return rows


def emit(root: Path, rows: list, output_dir: Path | None = None) -> dict:
    """Write parquet + summary JSON. Returns summary dict."""
    import pandas as pd

    out_dir = output_dir or root / "reports" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = out_dir / "outcome_dataset.parquet"
    summary_path = out_dir / "outcome_dataset_summary.json"

    if not rows:
        return {"n": 0, "note": "no positions found"}

    df = pd.DataFrame([asdict(r) for r in rows])
    df.to_parquet(parquet_path, index=False)

    # Summary rollups
    from collections import Counter
    tiers_cfg = _load_yaml(root / "configs" / "outcome_dataset_schema.yaml")
    tiers = tiers_cfg.get("sample_size_tiers") or []

    by_country = Counter(r.country for r in rows)
    by_runner = Counter(r.runner for r in rows)
    closed_count = sum(1 for r in rows if r.is_closed)
    open_count = sum(1 for r in rows if not r.is_closed)

    # Runner performance (CLOSED positions only · per governance)
    runner_perf = {}
    for runner_label in ("R1", "R2"):
        closed_r = [r for r in rows if r.runner == runner_label and r.is_closed
                            and isinstance(r.exit_pnl_pct, (int, float))]
        if not closed_r:
            runner_perf[runner_label] = {"n_closed": 0, "tier": _sample_tier(0, tiers)}
            continue
        n = len(closed_r)
        wins = sum(1 for r in closed_r if r.win_flag)
        avg = round(sum(r.exit_pnl_pct for r in closed_r) / n, 3)
        runner_perf[runner_label] = {
            "n_closed": n,
            "win_rate_pct": round(wins / n * 100, 1),
            "avg_pnl_pct": avg,
            "median_pnl_pct": round(sorted([r.exit_pnl_pct for r in closed_r])[n//2], 3),
            "tier": _sample_tier(n, tiers),
        }

    summary = {
        "engine":       "outcome_dataset.v1",
        "generated_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "n_positions":  len(rows),
        "n_closed":     closed_count,
        "n_open":       open_count,
        "by_country":   dict(by_country),
        "by_runner":    dict(by_runner),
        "runner_perf_closed_only": runner_perf,
        "parquet_path": str(parquet_path.relative_to(root)),
        "governance":   "win_rate uses CLOSED only · open positions excluded",
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8"
    )
    return summary
