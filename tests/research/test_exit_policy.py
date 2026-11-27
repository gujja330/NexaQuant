"""Exit advisor + exit policy replay. CEO 2026-11-26.

What must hold:
  * fills are conservative - a gap fills at the open, a bar touching both
    barriers is scored as the STOP
  * volatility is point-in-time - bars after entry cannot move a barrier
  * the advisor only advises: no stop written, no registry touched
  * the dynamic barrier is ON only where the replay supported it (USA),
    and OFF where it did not (India)
  * stale entry-time targets no longer fire TAKE PROFIT by default
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest
import yaml

from backend.research import exit_policy_replay as R
from backend.risk import exit_advisor as A

_ROOT = Path(__file__).resolve().parents[2]


def _ep(o, h, l, c, entry=100.0, sigma=0.02, atr=2.0):
    return R.Episode(oid="X", ticker="X", entry_date="2026-01-01", entry=entry,
                     sigma=sigma, atr=atr, o=o, h=h, l=l, c=c,
                     dates=["d%d" % i for i in range(len(c))],
                     base_ret=(c[-1] / entry - 1) * 100, base_days=len(c),
                     base_open=False)


TB10 = {"kind": "TB", "h": 10, "k_tp": 1.0, "k_sl": 1.0}
SPAN = 0.02 * math.sqrt(10)
SL = 100 * math.exp(-SPAN)
TP = 100 * math.exp(SPAN)


class TestFillsAreConservative:

    def test_gap_through_the_stop_fills_at_the_open(self):
        r = R.simulate(_ep([90], [91], [89], [90]), TB10, 0.0)
        assert r.reason == "STOP_GAP" and r.ret == pytest.approx(-10.0)

    def test_a_bar_touching_both_barriers_is_the_stop(self):
        r = R.simulate(_ep([100], [TP + 1], [SL - 1], [100]), TB10, 0.0)
        assert r.reason == "STOP", "ambiguous bars must never be scored as wins"

    def test_take_profit_fills_at_the_barrier_not_the_high(self):
        r = R.simulate(_ep([100], [TP + 5], [99], [TP + 2]), TB10, 0.0)
        assert r.reason == "TAKE_PROFIT"
        assert r.ret == pytest.approx((TP / 100 - 1) * 100)

    def test_time_barrier_exits_at_the_close_of_bar_h(self):
        n = 12
        r = R.simulate(_ep([100] * n, [100.5] * n, [99.5] * n, [100.2] * n), TB10, 0.0)
        assert r.reason == "TIME" and r.days == 10

    def test_costs_are_deducted(self):
        a = R.simulate(_ep([90], [91], [89], [90]), TB10, 0.0)
        b = R.simulate(_ep([90], [91], [89], [90]), TB10, 20.0)
        assert b.ret == pytest.approx(a.ret - 0.2)


class TestVolatilityIsPointInTime:

    def test_bars_after_entry_cannot_change_sigma(self):
        idx = pd.date_range("2026-01-01", periods=60, freq="B").strftime("%Y-%m-%d")
        base = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                             "close": [100 + (i % 3) for i in range(60)]}, index=idx)
        entry = idx[30]
        s1, a1 = R.pit_sigma_atr(base, entry)
        wild = base.copy()
        wild.loc[wild.index > entry, ["high", "low", "close"]] = [500.0, 1.0, 250.0]
        s2, a2 = R.pit_sigma_atr(wild, entry)
        assert (s1, a1) == (s2, a2), "a future bar leaked into the entry barrier"


class TestAdvisorRules:

    CFG = dict(A.DEFAULTS)

    def test_signal_exit_beats_everything(self):
        row = {"ticker": "Z", "entry_price": 100, "current_price": 150,
               "stop": 90, "target": 120, "pnl_pct": 50, "holding_days": 5}
        a = A.advise(row, {"Z": {"if_holding": "EXIT", "action": "SELL"}}, {"Z"}, self.CFG)
        assert a["exit_advice"] == A.ADVICE_SIGNAL_EXIT

    def test_stale_static_target_no_longer_fires_by_default(self):
        row = {"ticker": "PNB", "entry_price": 100, "current_price": 148.61,
               "stop": 140, "target": 117.92, "pnl_pct": 48.6, "holding_days": 51}
        a = A.advise(row, {}, {"PNB"}, self.CFG)
        assert a["exit_advice"] != A.ADVICE_TAKE_PROFIT

    def test_unprotected_winner_is_told_to_lock(self):
        row = {"ticker": "KOTAK", "entry_price": 100, "current_price": 128.2,
               "stop": 97.3, "target": None, "pnl_pct": 28.2, "holding_days": 114}
        a = A.advise(row, {}, {"KOTAK"}, self.CFG)
        assert a["exit_advice"] == A.ADVICE_LOCK
        assert a["suggested_stop"] == pytest.approx(110.0)

    def test_a_dynamic_call_takes_precedence_over_tiers(self):
        row = {"ticker": "Q", "entry_price": 100, "current_price": 80,
               "stop": 70, "pnl_pct": -20, "holding_days": 30,
               "_dyn": {"exit_advice": A.ADVICE_DYN_STOP,
                        "exit_advice_detail": "x", "suggested_stop": 94}}
        assert A.advise(row, {}, {"Q"}, self.CFG)["exit_advice"] == A.ADVICE_DYN_STOP


class TestAdvisoryOnly:

    def test_the_advisor_never_writes_a_stop_or_the_registry(self):
        src = (_ROOT / "backend" / "risk" / "exit_advisor.py").read_text(encoding="utf-8")
        for forbidden in ("opportunity_registry import close", "oreg.close",
                          "row[\"stop\"] =", "r[\"stop\"] =", "_append("):
            assert forbidden not in src, forbidden

    def test_annotate_does_not_change_the_stop(self, tmp_path):
        rows = [{"ticker": "Z", "entry_price": 100, "current_price": 130,
                 "stop": 95, "pnl_pct": 30, "holding_days": 40, "reason": "r"}]
        A.annotate(tmp_path, "india", "2026-11-26", rows)
        assert rows[0]["stop"] == 95


class TestPerMarketSwitches:

    def _cfg(self):
        d = yaml.safe_load((_ROOT / "configs" / "opportunity_registry.yaml")
                           .read_text(encoding="utf-8"))
        return d["risk_engine"]["exit_advisor"]

    def test_usa_dynamic_is_on_with_the_replay_parameters(self):
        u = self._cfg()["dynamic"]["usa"]
        assert u["enabled"] is True and u["h"] == 10
        assert u["k_sl"] == 1.0 and u["k_tp"] == 1.0

    def test_india_dynamic_is_off_because_the_replay_did_not_support_it(self):
        assert self._cfg()["dynamic"]["india"]["enabled"] is False

    def test_static_targets_are_off(self):
        assert self._cfg()["static_target_take_profit"] is False


class TestNestedCvNeverScoresOnItsOwnTrainingDates:

    def test_choose_only_sees_train_episodes(self, monkeypatch):
        seen = []
        real = R._choose

        def spy(eps, cost, sev, kinds=None):
            seen.append({e.entry_date for e in eps})
            return real(eps, cost, sev, kinds=kinds)

        monkeypatch.setattr(R, "_choose", spy)
        eps = []
        for d in range(12):
            ep = _ep([100] * 25, [101] * 25, [99] * 25, [100 + d % 3] * 25)
            ep.entry_date = "2026-01-%02d" % (d + 1)
            eps.append(ep)
        out = R.run_cv(Path("."), "usa", "2026-11-26", eps=eps)
        for f, train_dates in zip(out["folds"], seen):
            lo, hi = f["dates"].split("..")
            assert not any(lo <= d <= hi for d in train_dates)


class TestDynamicHoldPeriod:
    """CEO 2026-11-26 · a winner may run longer only if it EARNS it."""

    def test_efficiency_ratio_is_one_for_a_straight_line_and_low_for_chop(self):
        assert R.efficiency_ratio(100, [101, 102, 103, 104]) == pytest.approx(1.0)
        assert R.efficiency_ratio(100, [105, 95, 105, 101]) < 0.1

    def test_a_clean_trend_is_allowed_to_run_past_the_target(self):
        n = 40
        c = [100 + 1.0 * (i + 1) for i in range(n)]
        ep = _ep([x - 0.2 for x in c], [x + 0.3 for x in c], [x - 0.3 for x in c], c)
        pol = {"kind": "TB_ADAPT", "h": 10, "k_tp": 1.0, "k_sl": 1.0,
               "k_trail": 2.0, "h_max": 30, "er_min": 0.5}
        r = R.simulate(ep, pol, 0.0)
        assert r.reason == "MAX_HOLD" and r.days == 30, (
            "a straight-line winner should be held to the cap, not booked")

    def test_a_choppy_position_is_exited_at_h_not_held(self):
        n = 40
        c = [100 + (1.0 if i % 2 else -1.0) for i in range(n)]
        ep = _ep(c, [x + 0.5 for x in c], [x - 0.5 for x in c], c)
        pol = {"kind": "TB_ADAPT", "h": 10, "k_tp": 1.0, "k_sl": 1.0,
               "k_trail": 2.0, "h_max": 30, "er_min": 0.5}
        r = R.simulate(ep, pol, 0.0)
        assert r.reason == "TIME" and r.days == 10, "chop must not earn an extension"

    def test_trend_quality_never_reads_future_bars(self):
        """Altering bars after the decision cannot change the decision."""
        n = 40
        c = [100 + 1.0 * (i + 1) for i in range(n)]
        pol = {"kind": "TB_ADAPT", "h": 10, "k_tp": 5.0, "k_sl": 1.0,
               "k_trail": 50.0, "h_max": 11, "er_min": 0.5}
        a = R.simulate(_ep(c, c, c, c), pol, 0.0)
        c2 = c[:10] + [c[9]] * 30
        b = R.simulate(_ep(c2, c2, c2, c2), pol, 0.0)
        assert a.reason == b.reason == "MAX_HOLD"


class TestFallbackBlocksDoNotCount:

    def test_a_block_that_fell_back_to_aegis_is_excluded_from_the_pooled_score(self):
        src = (_ROOT / "backend" / "research" / "exit_policy_replay.py").read_text(encoding="utf-8")
        assert "if not fallback:" in src
        assert '"n_fallback_folds"' in src


class TestSelfCalibration:
    """CEO 2026-11-26 · barrier settings come from the latest validated
    replay, not from numbers copied into config by hand."""

    def _write(self, root, market, **rep):
        import json
        p = root / "reports" / "research" / ("exit_policy_replay_%s.json" % market)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rep), encoding="utf-8")

    CFG = {"dynamic": {"usa": {"calibration": "auto", "max_age_days": 35,
                               "enabled": True, "h": 10, "k_sl": 1.0, "k_tp": 1.0}}}

    def test_a_supported_replay_sets_the_live_parameters(self, tmp_path):
        self._write(tmp_path, "usa", asof="2026-11-20", tb_verdict="SUPPORTED",
                    recommended_policy={"kind": "TB", "h": 15, "k_sl": 1.5,
                                        "k_tp": 2.0, "label": "TB h=15d"})
        d = A.calibrate(tmp_path, "usa", self.CFG, "2026-11-26")
        assert (d["enabled"], d["h"], d["k_sl"], d["k_tp"]) == (True, 15, 1.5, 2.0)
        assert d["params_source"].startswith("replay 2026-11-20")

    def test_an_unsupported_replay_switches_the_barriers_off(self, tmp_path):
        self._write(tmp_path, "usa", asof="2026-11-20", tb_verdict="NOT SUPPORTED",
                    recommended_policy=None)
        assert A.calibrate(tmp_path, "usa", self.CFG, "2026-11-26")["enabled"] is False

    def test_a_stale_replay_falls_back_to_config_and_says_so(self, tmp_path):
        self._write(tmp_path, "usa", asof="2026-09-01", tb_verdict="SUPPORTED",
                    recommended_policy={"kind": "TB", "h": 30, "k_sl": 2.0, "k_tp": 3.0})
        d = A.calibrate(tmp_path, "usa", self.CFG, "2026-11-26")
        assert d["h"] == 10 and "days old" in d["params_source"]

    def test_manual_mode_ignores_the_replay(self, tmp_path):
        cfg = {"dynamic": {"usa": {"calibration": "manual", "h": 10}}}
        self._write(tmp_path, "usa", asof="2026-11-25", tb_verdict="SUPPORTED",
                    recommended_policy={"kind": "TB", "h": 30, "k_sl": 2.0, "k_tp": 3.0})
        assert A.calibrate(tmp_path, "usa", cfg, "2026-11-26")["h"] == 10


class TestTheAdviceIsVisible:
    """CEO 2026-11-26 · the advice was written at the END of a one-line
    Reason cell while Exit Decision showed HOLD on 153 of 161 rows."""

    def test_exit_decision_shows_the_advice(self):
        from backend.delivery.sheets.workbook_two import _decision_cells
        cells = _decision_cells({"exit_advice": "DYNAMIC STOP", "exit_decision": "HOLD"}, "usa")
        assert "DYNAMIC STOP" in cells and "HOLD" not in cells

    def test_hold_falls_back_to_the_engine_decision(self):
        from backend.delivery.sheets.workbook_two import _decision_cells
        cells = _decision_cells({"exit_advice": "HOLD", "exit_decision": "HOLD"}, "usa")
        assert "HOLD" in cells

    def test_reason_starts_with_the_advice(self, tmp_path, monkeypatch):
        monkeypatch.setattr(A, "load_config", lambda root: {**A.DEFAULTS})
        rows = [{"ticker": "Z", "entry_price": 100, "current_price": 140, "stop": 95,
                 "pnl_pct": 40.0, "holding_days": 40, "reason": "BUY · held 40d"}]
        A.annotate(tmp_path, "india", "2026-11-26", rows)
        assert rows[0]["reason"].startswith("LOCK PROFIT")
        assert "ADVISORY" not in rows[0]["reason"]


class TestCalibrationRunsInsideTheDailyPipeline:
    """CEO 2026-11-26 · "I cannot run every time multiple py files"."""

    SRC = (_ROOT / "scripts" / "aegis_run_all.py").read_text(encoding="utf-8")

    def test_the_stage_exists_for_every_market(self):
        assert 'run_stage(f"exit-calibration:{market}"' in self.SRC

    def test_it_runs_before_the_contract_that_reads_it(self):
        assert self.SRC.find('"exit-calibration:') < self.SRC.find('f"contract:{market}"')

    def test_it_runs_in_live_mode_with_a_freshness_skip(self):
        i = self.SRC.find('"exit-calibration:')
        stage = self.SRC[i:i + 300]
        assert '"--live"' in stage and '"--if-older-than", "5"' in stage

    def test_a_calibration_failure_cannot_block_delivery(self):
        s = (_ROOT / "scripts" / "exit_policy_replay.py").read_text(encoding="utf-8")
        tail = s[s.find('if __name__ == "__main__":'):]
        assert "except Exception" in tail and "SystemExit(0)" in tail


class TestFreshnessSkip:

    def test_age_is_measured_from_the_report_asof(self, tmp_path):
        import json
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "epr", _ROOT / "scripts" / "exit_policy_replay.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        p = tmp_path / "r.json"
        p.write_text(json.dumps({"asof": "2026-11-20"}), encoding="utf-8")
        assert mod._age_days(p, "2026-11-26") == 6
        assert mod._age_days(tmp_path / "missing.json", "2026-11-26") is None
