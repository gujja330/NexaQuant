"""Sprint G-F · Sustained News Impact Adapter.

Extends the point-in-time NewsAdapter with rolling 5-day sentiment
persistence. A single-day negative news blip is noise · sustained
negative sentiment across 5 days is real signal.

Reads: reports/context/sector_news.json (today) + reads jsonl history if
sector_news_history.jsonl exists (Sprint H builds the history).

Today's behaviour: since history isn't yet accumulated, falls back to
today's sector_news but applies a persistence weight.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class SustainedNewsAdapter:
    engine_name = "news"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        # Try history first · Sprint H will populate this
        hist_p = root / "reports" / "context" / "sector_news_history.jsonl"
        today_p = root / "reports" / "context" / "sector_news.json"

        rec_sector = str(rec.get("sector") or "")
        if not rec_sector:
            return zero_contribution(self.engine_name + "_sustained",
                                              "rec has no sector")

        # Rolling 5-day sentiment from history
        rolling_sentiments = []
        if hist_p.exists():
            try:
                cutoff = date.fromisoformat(asof) - timedelta(days=5)
                for line in hist_p.read_text(encoding="utf-8").splitlines():
                    if not line.strip(): continue
                    try:  h = json.loads(line)
                    except json.JSONDecodeError: continue
                    if h.get("market") != market: continue
                    try:
                        h_dt = date.fromisoformat(h.get("asof", "")[:10])
                    except (ValueError, TypeError):
                        continue
                    if h_dt < cutoff: continue
                    s = (h.get("sector_sentiment") or {}).get(rec_sector)
                    if isinstance(s, (int, float)): rolling_sentiments.append(s)
            except Exception:
                pass

        # Today's snapshot (always try)
        today_sent = None
        if today_p.exists():
            try:
                d = json.loads(today_p.read_text(encoding="utf-8"))
                today_sent = (d.get("sector_sentiment") or {}).get(rec_sector)
                # Also append today to sustain history (persistence)
                if hist_p.parent.exists() and isinstance(today_sent, (int, float)):
                    entry_key = (asof, market, rec_sector)
                    already = False
                    if hist_p.exists():
                        for ln in hist_p.read_text(encoding="utf-8").splitlines():
                            try:
                                h = json.loads(ln)
                                if h.get("asof") == asof and h.get("market") == market:
                                    already = True; break
                            except json.JSONDecodeError:
                                continue
                    if not already:
                        with hist_p.open("a", encoding="utf-8") as fh:
                            fh.write(json.dumps({
                                "asof": asof, "market": market,
                                "sector_sentiment": d.get("sector_sentiment") or {},
                            }) + "\n")
            except Exception:
                pass

        # Decide contribution
        if not rolling_sentiments and today_sent is None:
            return zero_contribution(self.engine_name + "_sustained",
                                              f"no sector news for {rec_sector}")

        # Prefer rolling avg if we have ≥3 days
        if len(rolling_sentiments) >= 3:
            avg = sum(rolling_sentiments) / len(rolling_sentiments)
            source = f"{len(rolling_sentiments)}d rolling"
            # Sustained impact · amplify the point-in-time thresholds
            if avg < -0.5:   pts, sev = -3.0, "critical"; note = "sustained negative"
            elif avg < -0.3: pts, sev = -1.5, "warning"; note = "persistent soft-negative"
            elif avg > 0.5:  pts, sev = 2.0, "info"; note = "sustained positive"
            elif avg > 0.3:  pts, sev = 1.0, "info"; note = "persistent soft-positive"
            else:
                return zero_contribution(self.engine_name + "_sustained",
                                                  f"{rec_sector} rolling news neutral")
        else:
            # Only today · use lighter thresholds (single-day is noisy)
            avg = today_sent or 0
            source = "1d only"
            if avg < -0.6:   pts, sev = -2.0, "warning"; note = "hard negative today"
            elif avg > 0.6:  pts, sev = 1.5, "info"; note = "strong positive today"
            else:
                return zero_contribution(self.engine_name + "_sustained",
                                                  f"{rec_sector} single-day news too noisy")

        reason = f"{rec_sector} news {source} avg={avg:+.2f} ({note}) → {pts:+.1f}pts"
        return ContextContribution(
            engine_name=self.engine_name + "_sustained", contribution_pts=pts,
            reason=reason, severity=sev, data_available=True,
            metadata={"sector": rec_sector, "rolling_avg": round(avg, 3),
                          "n_days": len(rolling_sentiments) or 1, "source": source},
        )
