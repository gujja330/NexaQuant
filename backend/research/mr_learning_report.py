"""AEGIS · Sprint M-R · Learning Report ('what AEGIS learned in 45 days').

CEO handover 2026-08-27:
> "After that, we have one clean answer to 'what has AEGIS actually
>  learned from 45 days of predictions?' · winners vs losers · R1 vs R2
>  vs Momentum · sector · large/mid cap · RSI · MA20 · rank ·
>  investability/quality · stop-loss · MFE/MAE · avoidable losses ·
>  missed profits · E1/E2/E3 cohorts."

Reads the evidence layer (history_evidence + exit_evidence) and produces
ONE consolidated learning report at reports/research/reports/
LEARNING_REPORT.md · sectioned by CEO's exact list.

Under M-R sandbox rules. Zero production changes.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median

from backend.research.mr_runner import ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_learning_report.v0.1"


def _load_jsonl(root: Path, rel: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / rel
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _agg(rows: list, filter_fn=None, key: str = "fwd_5d_pct") -> dict:
    subset = [r for r in rows if (filter_fn is None or filter_fn(r))]
    vals = [r.get(key) for r in subset if isinstance(r.get(key), (int, float))]
    if not vals:
        return {"n": 0}
    wins = sum(1 for v in vals if v > 0.5)
    losses = sum(1 for v in vals if v < -0.5)
    return {
        "n":         len(vals),
        "wr_pct":    round(wins/len(vals)*100, 2),
        "avg_pct":   round(mean(vals), 3),
        "median_pct":round(median(vals), 3),
        "wins":      wins,
        "losses":    losses,
    }


def _fmt(v, digits=2, suffix=""):
    if v is None: return "—"
    if isinstance(v, (int, float)): return f"{v:.{digits}f}{suffix}"
    return str(v)


def build(root: Path) -> dict:
    # Load evidence per market
    india = _load_jsonl(root, "evidence/india/history_evidence.jsonl")
    usa = _load_jsonl(root, "evidence/usa/history_evidence.jsonl")
    exits_i = _load_jsonl(root, "evidence/india/exit_evidence.jsonl")
    exits_u = _load_jsonl(root, "evidence/usa/exit_evidence.jsonl")

    def _market_learning(rows: list, exits: list, market: str) -> dict:
        # Baseline
        base = _agg(rows)
        # Winners vs losers
        wins = _agg(rows, lambda r: r.get("outcome_label_5d") == "WIN")
        losers = _agg(rows, lambda r: r.get("outcome_label_5d") == "LOSS")
        # R1 vs R2 vs Momentum
        by_runner: dict = {}
        for run in ("R1","R2","MOMENTUM"):
            m = _agg(rows, lambda r, run=run: str(r.get("runner","")).upper() == run)
            if m.get("n"): by_runner[run] = m
        # Sector
        by_sector: dict = {}
        sectors = Counter(r.get("sector") for r in rows if r.get("sector"))
        for sec, _ in sectors.most_common():
            if not sec: continue
            m = _agg(rows, lambda r, sec=sec: r.get("sector") == sec)
            if m.get("n", 0) >= 15: by_sector[sec] = m
        # Cap
        by_cap: dict = {}
        for cap in ("LARGE","MID","SMALL"):
            m = _agg(rows, lambda r, cap=cap: r.get("cap_bucket") == cap)
            if m.get("n"): by_cap[cap] = m
        # RSI
        by_rsi: dict = {}
        for b in ("OVERSOLD","WEAK","NEUTRAL","STRONG","OVERBOUGHT"):
            m = _agg(rows, lambda r, b=b: r.get("rsi_bucket") == b)
            if m.get("n"): by_rsi[b] = m
        # MA20
        by_ma20: dict = {}
        for b in ("lt-5","-5_-1","-1_+1","+1_+5","ge+5"):
            m = _agg(rows, lambda r, b=b: r.get("ma20_bucket") == b)
            if m.get("n"): by_ma20[b] = m
        # Rank slot
        by_rank: dict = {}
        for b in ("top3","rank_4_7","rank_8_15","rank_16plus"):
            m = _agg(rows, lambda r, b=b: r.get("rank_slot") == b)
            if m.get("n"): by_rank[b] = m
        # Investability
        by_band: dict = {}
        for b in ("QUALITY","OK","MARGINAL","AVOID"):
            m = _agg(rows, lambda r, b=b: r.get("investability_band") == b)
            if m.get("n"): by_band[b] = m
        # Stop-loss + MFE/MAE aggregates
        mfe_vals = [r.get("mfe_pct") for r in rows if isinstance(r.get("mfe_pct"), (int,float))]
        mae_vals = [r.get("mae_pct") for r in rows if isinstance(r.get("mae_pct"), (int,float))]
        stop_hits = [r for r in rows if r.get("stop_hit_within_20d") is True]
        stop_evaluated = [r for r in rows if r.get("stop_hit_within_20d") is not None]
        stop_stats = {
            "avg_mfe_pct": round(mean(mfe_vals),3) if mfe_vals else None,
            "avg_mae_pct": round(mean(mae_vals),3) if mae_vals else None,
            "stop_hit_rate_pct": round(len(stop_hits)/max(1,len(stop_evaluated))*100, 2)
                                 if stop_evaluated else None,
        }
        # Avoidable losses
        avoidable = sum(1 for r in exits if r.get("avoidable_loss") is True)
        total_loss = sum(1 for r in exits if r.get("outcome") == "LOSS")
        avoidable_pct = round(avoidable/max(1,total_loss)*100, 2) if total_loss else None
        # Missed profits (MFE >= 2% but realized <= 0.5%)
        missed = sum(1 for r in exits
                     if isinstance(r.get("mfe_pct"), (int,float)) and r["mfe_pct"] >= 2.0
                     and isinstance(r.get("entry_to_exit_pct"), (int,float))
                     and r["entry_to_exit_pct"] <= 0.5)
        missed_pct = round(missed/max(1,len(exits))*100, 2) if exits else None
        # E1/E2/E3 cohorts (retro signals in history)
        by_e: dict = {}
        for e in ("E1_REJECT_R1_WEAK","E2_BOOST_R2_STRONG","E3_TIME_EXIT_ADVISORY"):
            m = _agg(rows, lambda r, e=e: e in (r.get("research_signals") or []))
            if m.get("n"): by_e[e] = m
        return {
            "n_predictions": len(rows),
            "baseline":      base,
            "winners":       wins,
            "losers":        losers,
            "by_runner":     by_runner,
            "by_sector":     by_sector,
            "by_cap":        by_cap,
            "by_rsi":        by_rsi,
            "by_ma20":       by_ma20,
            "by_rank_slot":  by_rank,
            "by_band":       by_band,
            "stop_stats":    stop_stats,
            "avoidable_losses_pct": avoidable_pct,
            "avoidable_losses_count": avoidable,
            "total_losses":  total_loss,
            "missed_profits_pct": missed_pct,
            "missed_profits_count": missed,
            "n_exits":       len(exits),
            "by_e_cohort":   by_e,
        }

    india_l = _market_learning(india, exits_i, "INDIA")
    usa_l = _market_learning(usa, exits_u, "USA")
    return {
        "engine":         ENGINE_ID,
        "generated_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_date": date.today().isoformat(),
        "india":          india_l,
        "usa":            usa_l,
    }


def render_markdown(res: dict) -> str:
    L = [f"# What has AEGIS actually learned in 45 days?\n"]
    L.append(f"_Sprint M-R Learning Report · consolidated from history + "
             f"exit evidence_\n")
    L.append(f"**Generated:** {res['generated_utc']}\n\n---\n")

    for mk, key in (("INDIA","india"),("USA","usa")):
        d = res[key]
        L.append(f"\n## {mk} · n_predictions = {d['n_predictions']}\n")
        b = d["baseline"]
        w = d["winners"]; loss = d["losers"]
        L.append(f"**Baseline 5D:** n={b.get('n')} · WR={_fmt(b.get('wr_pct'),2,'%')} "
                 f"· avg={_fmt(b.get('avg_pct'),3,'%')}")
        L.append(f"**Winners:** n={w.get('n')} · avg={_fmt(w.get('avg_pct'),3,'%')}  ·  "
                 f"**Losers:** n={loss.get('n')} · avg={_fmt(loss.get('avg_pct'),3,'%')}\n")
        # R1 vs R2 vs Momentum
        L.append(f"### {mk} · R1 vs R2 vs Momentum")
        L.append(f"| Runner | n | 5D WR | avg |")
        L.append(f"|---|---:|---:|---:|")
        for r, m in d["by_runner"].items():
            L.append(f"| {r} | {m['n']} | {m['wr_pct']}% | {m['avg_pct']}% |")
        if "MOMENTUM" not in d["by_runner"]:
            L.append(f"| MOMENTUM | 0 | — | — · historical corpus empty |")

        # Sector
        L.append(f"\n### {mk} · Sector (min n=15)")
        L.append(f"| Sector | n | 5D WR | avg |")
        L.append(f"|---|---:|---:|---:|")
        for s, m in sorted(d["by_sector"].items(), key=lambda kv: -kv[1]["wr_pct"]):
            L.append(f"| {s} | {m['n']} | {m['wr_pct']}% | {m['avg_pct']}% |")

        # Cap
        L.append(f"\n### {mk} · Market cap")
        L.append(f"| Cap | n | 5D WR | avg |")
        L.append(f"|---|---:|---:|---:|")
        for c, m in d["by_cap"].items():
            L.append(f"| {c} | {m['n']} | {m['wr_pct']}% | {m['avg_pct']}% |")

        # RSI
        L.append(f"\n### {mk} · RSI bucket")
        L.append(f"| RSI | n | 5D WR | avg |")
        L.append(f"|---|---:|---:|---:|")
        for k, m in d["by_rsi"].items():
            L.append(f"| {k} | {m['n']} | {m['wr_pct']}% | {m['avg_pct']}% |")

        # MA20
        L.append(f"\n### {mk} · MA20-dist bucket")
        L.append(f"| MA20 | n | 5D WR | avg |")
        L.append(f"|---|---:|---:|---:|")
        for k, m in d["by_ma20"].items():
            L.append(f"| {k} | {m['n']} | {m['wr_pct']}% | {m['avg_pct']}% |")

        # Rank
        L.append(f"\n### {mk} · Rank slot")
        L.append(f"| Rank | n | 5D WR | avg |")
        L.append(f"|---|---:|---:|---:|")
        for k, m in d["by_rank_slot"].items():
            L.append(f"| {k} | {m['n']} | {m['wr_pct']}% | {m['avg_pct']}% |")

        # Investability
        L.append(f"\n### {mk} · Investability/quality band")
        L.append(f"| Band | n | 5D WR | avg |")
        L.append(f"|---|---:|---:|---:|")
        for k, m in d["by_band"].items():
            L.append(f"| {k} | {m['n']} | {m['wr_pct']}% | {m['avg_pct']}% |")

        # Stop-loss + MFE/MAE
        L.append(f"\n### {mk} · Stop-loss · MFE/MAE")
        s = d["stop_stats"]
        L.append(f"- avg MFE = **{s['avg_mfe_pct']}%**")
        L.append(f"- avg MAE = **{s['avg_mae_pct']}%**")
        L.append(f"- stop-hit rate = **{s['stop_hit_rate_pct']}%**")

        # Avoidable losses + missed profits
        L.append(f"\n### {mk} · Avoidable losses + missed profits")
        L.append(f"- total losses = **{d['total_losses']}**")
        L.append(f"- avoidable losses = **{d['avoidable_losses_count']}** "
                 f"({_fmt(d['avoidable_losses_pct'],2,'%')} of losses)")
        L.append(f"- missed profits (MFE >= 2% but realized <= 0.5%) = "
                 f"**{d['missed_profits_count']}** "
                 f"({_fmt(d['missed_profits_pct'],2,'%')} of exits)")

        # E1/E2/E3 cohorts
        L.append(f"\n### {mk} · E1/E2/E3 cohort retro-scan")
        L.append(f"| Signal | n | 5D WR | avg |")
        L.append(f"|---|---:|---:|---:|")
        for k, m in d["by_e_cohort"].items():
            L.append(f"| {k} | {m['n']} | {m['wr_pct']}% | {m['avg_pct']}% |")

    L.append(f"\n---\n\n## Compliance\n")
    L.append(f"- Zero production changes")
    L.append(f"- Zero XLSX/canonical/R1/R2/Registry touches")
    L.append(f"- Historical rows APPEND-ONLY · never restamped")
    L.append(f"- E1/E2/E3 shadow rules run only for retro-scanning · production")
    L.append(f"  R1/R2 decisions unchanged")
    L.append(f"- Failed / superseded / archived items retained in `archive/`")
    L.append(f"  · never deleted")
    return "\n".join(L)


def emit(root: Path, res: dict, md: str) -> tuple:
    p_md = root / ALLOWED_WRITE_ROOT / "reports" / "LEARNING_REPORT.md"
    p_md.parent.mkdir(parents=True, exist_ok=True)
    p_md.write_text(md, encoding="utf-8")
    p_json = root / ALLOWED_WRITE_ROOT / "mr_learning_report.json"
    p_json.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return (p_md, p_json)


if __name__ == "__main__":
    root = Path(".").resolve()
    res = build(root)
    md = render_markdown(res)
    p_md, p_json = emit(root, res, md)
    print(f"[learning_report] wrote {p_md} · {len(md)} bytes · "
          f"{md.count(chr(10))} lines")
    for mk in ("india","usa"):
        d = res[mk]
        b = d["baseline"]
        print(f"  {mk.upper()}: n_pred={d['n_predictions']} · "
              f"baseline WR={b.get('wr_pct','—')}% · "
              f"avoidable losses {d['avoidable_losses_count']}/{d['total_losses']} · "
              f"missed profits {d['missed_profits_count']}/{d['n_exits']}")
