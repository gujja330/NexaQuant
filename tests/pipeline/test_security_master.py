from datetime import datetime, timedelta, timezone

from backend.ingest.security_master import populations, update
from usa.scripts.refresh_universe import _extract_tickers


def test_constituent_parser_ignores_other_tables_and_preserves_class_shares():
    page = """
    <table><tr><td><a>NOISE</a></td></tr></table>
    <table id="constituents">
      <tr><th>Symbol</th><th>Issuer</th></tr>
      <tr><td><a>BRK.B</a></td><td>Berkshire</td></tr>
      <tr><td>BF.B</td><td>Brown-Forman</td></tr>
    </table>"""
    assert _extract_tickers(page) == ["BRK.B", "BF.B"]


def test_reference_falls_back_after_duplicate_candidate_and_restores_verified_archive(tmp_path):
    now = datetime(2026, 11, 26, tzinfo=timezone.utc)

    def candidate(asof, members):
        return {"market": "usa", "index": "test", "members": members, "observed_utc": asof.isoformat()}

    verified, good = update(tmp_path, "usa", "test", ["BRK.B", "AAPL"],
                            lambda: candidate(now, ["BRK.B", "AAPL"]), now=now)
    assert good["status"] == "VERIFIED"
    (tmp_path / "test.json").write_text("corrupt", encoding="utf-8")
    tomorrow = now + timedelta(days=1)
    retained, decision = update(tmp_path, "usa", "test", ["BRK.B", "AAPL"],
                                lambda: candidate(tomorrow, ["AAPL", "AAPL"]), now=tomorrow)
    assert retained == verified
    assert decision["status"] == "FALLBACK"
    assert decision["observed_utc"] == now.isoformat()


def test_population_retains_removed_held_position_and_separates_provider_symbol(tmp_path):
    result = populations(tmp_path, "usa", ["AAPL"], ["BRK.B"], ["^GSPC"], ["BF.B"])
    assert result["configured"] == ["AAPL"]
    assert result["held_outside_configured"] == ["BRK.B"]
    assert result["pending"] == ["BF.B"]
    assert result["provider_symbols"] == {
        "AAPL": "AAPL", "BRK.B": "BRK-B", "BF.B": "BF-B", "^GSPC": "^GSPC"}
