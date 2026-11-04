"""The canonical feature snapshot is authoritative. CEO 2026-11-04.

WHY THIS EXISTS
---------------
On 2026-11-04 the 2026-11-03 snapshots were rebuilt in an isolated root,
passed seven acceptance checks, were copied into `features/<market>/`
and hash-verified byte-for-byte. None of that reached scoring.

`read_snapshot` preferred the newest `.rebuilt_HHMMSS.parquet` sibling -
"the freshest computation" - so the promoted canonical file was never
read. Production was served `2026-11-03.rebuilt_073223.parquet` (India)
and `.rebuilt_073239.parquet` (USA): files nobody promoted, carrying
`macro_move` resolved from an undated snapshot under a historical asof.

The promotion was real. The authority was not. These tests pin the
contract that makes them the same thing.

Every test uses tmp_path. No live snapshot directory is read or written.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from backend.feature_store.feature_history import (
    SNAPSHOT_MISSING, SNAPSHOT_SERVED, list_snapshots, promote_candidate,
    read_snapshot, read_snapshot_detail, rebuild_candidates, snapshot_path,
    undated_features_present, write_snapshot)

ASOF = date(2026, 11, 3)
OTHER = date(2026, 11, 2)


def _frame(n=3, tag="canonical", move=None):
    d = {"ticker": ["T%02d" % i for i in range(n)],
         "asof": [ASOF.isoformat()] * n,
         "tag": [tag] * n}
    if move is not None:
        d["macro_move"] = [move] * n
    return pd.DataFrame(d)


def _write(root, market, asof, df):
    p = snapshot_path(root, market, asof)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)
    return p


def _write_candidate(root, market, asof, df, stamp):
    p = snapshot_path(root, market, asof)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = p.with_suffix(".rebuilt_%s.parquet" % stamp)
    df.to_parquet(c, index=False)
    return c


# ── 1 · canonical plus one rebuilt sibling ──────────────────────────
class TestCanonicalWins:
    def test_canonical_is_served_when_a_rebuilt_sibling_exists(self, tmp_path):
        _write(tmp_path, "india", ASOF, _frame(tag="canonical"))
        _write_candidate(tmp_path, "india", ASOF, _frame(tag="rebuilt"),
                         "073223")
        df = read_snapshot(tmp_path, "india", ASOF)
        assert list(df["tag"].unique()) == ["canonical"], (
            "the rebuilt sibling was served - this is the exact 2026-11-03 "
            "defect")

    def test_the_read_reports_the_candidate_it_declined(self, tmp_path):
        _write(tmp_path, "india", ASOF, _frame())
        c = _write_candidate(tmp_path, "india", ASOF, _frame(tag="r"), "073223")
        r = read_snapshot_detail(tmp_path, "india", ASOF)
        assert r.status == SNAPSHOT_SERVED
        assert r.candidates == (c,)


# ── 2 · several rebuilt siblings ────────────────────────────────────
class TestMultipleCandidates:
    def test_five_candidates_do_not_displace_the_canonical_file(self, tmp_path):
        """USA had exactly five on 2026-11-03."""
        _write(tmp_path, "usa", ASOF, _frame(tag="canonical"))
        for s in ("023511", "055855", "055916", "073218", "073239"):
            _write_candidate(tmp_path, "usa", ASOF, _frame(tag="r" + s), s)
        r = read_snapshot_detail(tmp_path, "usa", ASOF)
        assert list(r.frame["tag"].unique()) == ["canonical"]
        assert len(r.candidates) == 5

    def test_candidates_are_listed_oldest_first(self, tmp_path):
        _write(tmp_path, "usa", ASOF, _frame())
        for s in ("073239", "023511", "055855"):
            _write_candidate(tmp_path, "usa", ASOF, _frame(), s)
        got = [p.name for p in rebuild_candidates(tmp_path, "usa", ASOF)]
        assert got == sorted(got)
        assert "023511" in got[0]


# ── 3 · missing canonical ───────────────────────────────────────────
class TestMissingCanonical:
    def test_missing_canonical_is_explicit_not_a_fallback(self, tmp_path):
        _write_candidate(tmp_path, "india", ASOF, _frame(tag="rebuilt"),
                         "073223")
        r = read_snapshot_detail(tmp_path, "india", ASOF)
        assert r.status == SNAPSHOT_MISSING
        assert r.frame is None
        assert r.reason and "NOT served implicitly" in r.reason
        assert len(r.candidates) == 1

    def test_the_thin_wrapper_returns_none_rather_than_a_candidate(self, tmp_path):
        _write_candidate(tmp_path, "india", ASOF, _frame(), "073223")
        assert read_snapshot(tmp_path, "india", ASOF) is None

    def test_no_directory_at_all_is_missing_not_an_exception(self, tmp_path):
        r = read_snapshot_detail(tmp_path, "india", ASOF)
        assert r.status == SNAPSHOT_MISSING
        assert r.candidates == ()


# ── 4 · wrong-date canonical ────────────────────────────────────────
class TestExactDateOnly:
    def test_a_neighbouring_date_is_never_substituted(self, tmp_path):
        _write(tmp_path, "india", OTHER, _frame(tag="yesterday"))
        r = read_snapshot_detail(tmp_path, "india", ASOF)
        assert r.status == SNAPSHOT_MISSING, (
            "yesterday's snapshot was served for today - the failure the "
            "contract gate exists to catch")

    def test_the_requested_date_is_echoed_back(self, tmp_path):
        _write(tmp_path, "india", ASOF, _frame())
        assert read_snapshot_detail(tmp_path, "india", ASOF).asof == ASOF


# ── 5 · explicit promotion ──────────────────────────────────────────
class TestExplicitPromotion:
    def test_promotion_makes_the_candidate_canonical(self, tmp_path):
        _write(tmp_path, "india", ASOF, _frame(tag="old"))
        c = _write_candidate(tmp_path, "india", ASOF, _frame(tag="new"),
                             "073223")
        res = promote_candidate(tmp_path, "india", ASOF, c)
        assert res["state"] == "PROMOTED"
        assert list(read_snapshot(tmp_path, "india", ASOF)["tag"]) == ["new"] * 3

    def test_the_superseded_file_is_archived_not_destroyed(self, tmp_path):
        _write(tmp_path, "india", ASOF, _frame(tag="old"))
        c = _write_candidate(tmp_path, "india", ASOF, _frame(tag="new"), "0732")
        res = promote_candidate(tmp_path, "india", ASOF, c)
        arch = Path(res["superseded"])
        assert arch.exists()
        assert list(pd.read_parquet(arch)["tag"].unique()) == ["old"]

    def test_a_validator_can_refuse_and_nothing_moves(self, tmp_path):
        _write(tmp_path, "india", ASOF, _frame(tag="old"))
        c = _write_candidate(tmp_path, "india", ASOF, _frame(tag="new"), "0732")
        res = promote_candidate(tmp_path, "india", ASOF, c,
                                validator=lambda d: (False, "row count floor"))
        assert res["state"] == "REFUSED"
        assert res["reason"] == "row count floor"
        assert list(read_snapshot(tmp_path, "india", ASOF)["tag"]) == ["old"] * 3

    def test_promotion_reports_the_hash_it_wrote(self, tmp_path):
        c = _write_candidate(tmp_path, "india", ASOF, _frame(), "0732")
        res = promote_candidate(tmp_path, "india", ASOF, c)
        assert res["state"] == "PROMOTED"
        assert res["superseded"] is None
        got = read_snapshot_detail(tmp_path, "india", ASOF)
        assert got.sha256 == res["sha256"]

    def test_a_missing_candidate_fails_without_touching_canonical(self, tmp_path):
        _write(tmp_path, "india", ASOF, _frame(tag="old"))
        res = promote_candidate(tmp_path, "india", ASOF,
                                tmp_path / "nope.parquet")
        assert res["state"] == "FAILED"
        assert list(read_snapshot(tmp_path, "india", ASOF)["tag"]) == ["old"] * 3


# ── 6 + 7 · undated values under a historical asof ──────────────────
class TestUndatedDataIsReported:
    def test_a_populated_macro_move_is_flagged_as_undated(self, tmp_path):
        """macro_move has no dated source · only an undated snapshot."""
        _write(tmp_path, "india", ASOF, _frame(move=100.36))
        r = read_snapshot_detail(tmp_path, "india", ASOF)
        assert "macro_move" in r.undated_features

    def test_an_abstaining_macro_move_is_not_flagged(self, tmp_path):
        _write(tmp_path, "india", ASOF, _frame())
        assert read_snapshot_detail(tmp_path, "india",
                                    ASOF).undated_features == ()

    def test_an_all_null_macro_move_column_is_not_flagged(self, tmp_path):
        df = _frame()
        df["macro_move"] = [None, None, None]
        _write(tmp_path, "india", ASOF, df)
        assert read_snapshot_detail(tmp_path, "india",
                                    ASOF).undated_features == ()

    def test_a_candidate_built_when_its_asof_was_current_is_still_flagged(
            self, tmp_path):
        """Case 7. The 073223/073239 files were built while 2026-11-03 was
        today, so the resolver allowed macro_move. Promoting one later
        does not make the value dated - the read says so either way."""
        c = _write_candidate(tmp_path, "india", ASOF, _frame(move=100.36),
                             "073223")
        res = promote_candidate(tmp_path, "india", ASOF, c)
        assert res["state"] == "PROMOTED"
        r = read_snapshot_detail(tmp_path, "india", ASOF)
        assert "macro_move" in r.undated_features, (
            "a promoted candidate carrying an undated value must still be "
            "reported, whenever it was built")

    def test_the_helper_is_driven_by_the_series_registry_not_a_literal(self):
        from backend.feature_store.macro_series import SUMMARY_SYMBOL
        df = pd.DataFrame({k: [1.0] for k in SUMMARY_SYMBOL})
        assert set(undated_features_present(df)) == set(SUMMARY_SYMBOL)


# ── 8 · deterministic exact-date selection ──────────────────────────
class TestDeterminism:
    def test_repeated_reads_serve_the_same_path_and_hash(self, tmp_path):
        _write(tmp_path, "usa", ASOF, _frame(n=5))
        for s in ("023511", "073239"):
            _write_candidate(tmp_path, "usa", ASOF, _frame(n=9), s)
        a = read_snapshot_detail(tmp_path, "usa", ASOF)
        b = read_snapshot_detail(tmp_path, "usa", ASOF)
        assert (a.path, a.sha256, a.n_rows) == (b.path, b.sha256, b.n_rows)
        assert a.n_rows == 5

    def test_adding_a_newer_candidate_does_not_change_what_is_served(self,
                                                                    tmp_path):
        _write(tmp_path, "usa", ASOF, _frame(n=5))
        before = read_snapshot_detail(tmp_path, "usa", ASOF).sha256
        _write_candidate(tmp_path, "usa", ASOF, _frame(n=99), "235959")
        after = read_snapshot_detail(tmp_path, "usa", ASOF)
        assert after.sha256 == before
        assert after.n_rows == 5


# ── 9 · no silent fallback, anywhere ────────────────────────────────
class TestNoSilentFallback:
    def test_write_snapshot_does_not_clobber_the_canonical_file(self, tmp_path):
        _write(tmp_path, "india", ASOF, _frame(tag="canonical"))
        out = write_snapshot(tmp_path, "india", ASOF, _frame(tag="second"))
        assert ".rebuilt_" in out.name
        assert list(read_snapshot(tmp_path, "india", ASOF)["tag"]) == \
            ["canonical"] * 3

    def test_a_rebuild_changes_nothing_until_promoted(self, tmp_path):
        _write(tmp_path, "india", ASOF, _frame(tag="canonical"))
        before = read_snapshot_detail(tmp_path, "india", ASOF).sha256
        write_snapshot(tmp_path, "india", ASOF, _frame(tag="second"))
        assert read_snapshot_detail(tmp_path, "india", ASOF).sha256 == before

    def test_candidates_and_archives_are_absent_from_list_snapshots(self,
                                                                    tmp_path):
        _write(tmp_path, "india", ASOF, _frame())
        _write_candidate(tmp_path, "india", ASOF, _frame(), "073223")
        p = snapshot_path(tmp_path, "india", ASOF)
        _frame().to_parquet(
            p.with_suffix(".superseded_20261104T000000Z.parquet"), index=False)
        assert list_snapshots(tmp_path, "india") == [ASOF]

    def test_the_reader_source_holds_no_rebuilt_preference(self):
        """The 'freshest wins' rule must not come back by edit.

        AST, not grep. A line scan matches the docstring that EXPLAINS the
        rule and fails on its own explanation - the same false positive
        that tripped the macro no-fabrication tests.
        """
        import ast
        import backend.feature_store.feature_history as fh
        tree = ast.parse(Path(fh.__file__).read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "read_snapshot_detail")
        body = list(fn.body)
        if ast.get_docstring(fn) is not None:
            body = body[1:]                      # drop the docstring node
        code = "\n".join(ast.unparse(n) for n in body)
        assert "rebuilt_" not in code, (
            "read_snapshot_detail must not glob or prefer rebuilt files; it "
            "delegates to rebuild_candidates purely to report them")

    def test_markets_do_not_borrow_from_each_other(self, tmp_path):
        _write(tmp_path, "usa", ASOF, _frame(tag="usa"))
        assert read_snapshot(tmp_path, "india", ASOF) is None
        assert list(read_snapshot(tmp_path, "usa", ASOF)["tag"]) == ["usa"] * 3


class TestLiveRepositoryIsUnaffectedByImport:
    def test_the_promoted_2026_11_03_files_are_what_the_live_root_serves(self):
        """Read-only check against the real repository."""
        root = Path(__file__).resolve().parents[2]
        for market, n in (("india", 228), ("usa", 516)):
            r = read_snapshot_detail(root, market, ASOF)
            if r.status == SNAPSHOT_MISSING:
                pytest.skip("no canonical %s snapshot for %s" % (market, ASOF))
            assert r.path.name == "2026-11-03.parquet"
            assert r.n_rows == n
            assert "macro_move" not in r.undated_features, (
                "the served %s snapshot carries an undated macro_move" % market)
