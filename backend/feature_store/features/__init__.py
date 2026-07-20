"""Per-category feature computers. Each module exposes:

    compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str) -> dict[ticker -> dict[feature -> value]]

The computer only fills features it owns (declared in feature_registry). The
builder joins per-ticker dicts across all computers to produce the final vector.
"""
