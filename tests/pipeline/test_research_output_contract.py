from backend.research.multi_layer.momentum_forward_outcomes import measure


def test_momentum_retains_entire_malformed_snapshot(tmp_path):
    snapshots = tmp_path / "reports/research/momentum_snapshots"
    snapshots.mkdir(parents=True)
    path = snapshots / "india_2026-11-23.jsonl"
    original = b'{"ticker":"EXAMPLE"}\n{bad row\n'
    path.write_bytes(original)
    result = measure(tmp_path, "india", "2026-11-26")
    assert result["malformed_snapshots"] == [path.name]
    assert result["n_snapshots_updated"] == 0
    assert path.read_bytes() == original
