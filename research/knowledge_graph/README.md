# DEV031 — Knowledge Graph & Relationship Intelligence

**Sprint 16 · Knowledge track.** Central intelligence layer that connects
every entity AEGIS reasons about into one queryable graph. No internet
scraping — pure integration of validated `reports/` outputs from DEV017-DEV030.

> Advisory-only per ARCH001A Article V clause 5.1. Deterministic,
> explainable, evidence-based. Reuses DEV017-DEV030 utilities.

---

## What it does

Reads every published `reports/*.json` and `.parquet` from earlier DEVs and
materialises a single weighted graph:

**Entities (10 types):** Company · Industry · Sector · MarketTheme ·
Strategy · Recommendation · Portfolio · Signal · RiskFactor · MarketRegime

**Relations (10 types):**
- Company → Industry
- Industry → Sector
- Company → Portfolio
- Portfolio → Strategy
- Recommendation → Company
- Recommendation → Outcome (winner/loser via DEV025)
- Company → Competitor (same industry, score-similarity)
- Sector → Regime
- Signal → Recommendation (via DEV027 diagnoses)
- Company → MarketTheme (top-20 by decision score)

**Algorithms:** adjacency build · shortest path (Dijkstra on inverse
weights) · degree centrality · weighted degree · deterministic PageRank
(influence) · BFS closeness · subgraph extraction by type.

**Queries:** related companies · strongest competitors · portfolio
dependencies · explain recommendation relationships · sector influence ·
signal propagation.

## Inputs (all optional; graph gracefully degrades)

- `reports/recommendations.json` (DEV023) — companies, sectors, industries
- `reports/portfolio.parquet` (DEV022) — portfolio memberships
- `reports/challenger_scoreboard.json` (DEV030) — strategies
- `reports/regime_comparison.json` (DEV030) — regime windows + champions
- `reports/global_context.json` (DEV017) — market themes
- `reports/strategy_doctor.json` (DEV027) — signals + signal→rec edges
- `reports/learning.parquet` (DEV025) — recommendation outcomes
- `reports/portfolio_monitoring.json` (DEV024) — risk factors
- `reports/sector_intelligence.json` (DEV018), `industry_intelligence.json` (DEV019) — sector/industry attributes

## Outputs (7)

Written to `reports/`:

- **`knowledge_graph.json`** — headline stats + governance
- **`entity_network.json`** — all nodes with influence + degree + strength
- **`relationship_matrix.json`** — full edge list with weights + attributes
- **`company_network.json`** — company subgraph adjacency
- **`sector_network.json`** — sector subgraph adjacency
- **`graph_statistics.json`** — top influencers + entity/relation counts
- **`knowledge_graph.parquet`** — edges as tabular rows for downstream analysis

## Algorithms

| Function | Complexity | Use |
|---|---|---|
| `build_adjacency` | O(E) | Undirected weighted adjacency |
| `shortest_path` | O((V+E) log V) | Dijkstra on 1/weight |
| `degree_centrality` | O(V) | Normalised connectivity |
| `weighted_degree` | O(V+E) | Sum of edge weights per node |
| `eigen_influence` | O(iters·E) | Deterministic PageRank (damping=0.85) |
| `closeness_centrality` | O(V·(V+E)) | Inverse mean path length |
| `neighbours` | O(hops·E) | BFS neighbours up to K hops |
| `subgraph_by_type` | O(V+E) | Prefix-filter subgraph |

## Governance

- No internet scraping; only validated `reports/*` inputs.
- Deterministic (no random seeds; PageRank fixed-point iterations).
- Advisory-only; the graph never mutates any DEV017-DEV030 output.
- Missing inputs degrade gracefully (empty subgraphs; run continues).

## Layout

```
research/knowledge_graph/
  lib/
    entities.py        — extract 10 entity types
    relationships.py   — materialise 10 relation types
    algorithms.py      — pure graph algorithms
    queries.py         — high-level explain-* queries
  compute/
    engine.py          — orchestration
  publish/
    bundle.py          — 7 outputs
  tests/
    test_smoke.py
  run.py
```

## Run

```
python research/knowledge_graph/run.py
python research/knowledge_graph/tests/test_smoke.py
```

## Follow-ups

- Persist historical graph snapshots for graph-drift analysis
- Add `Company → Supplier / Customer` edges once a supply-chain data source
  is available (deliberately deferred — no fabricated relationships)
- Compute community detection (Louvain / Leiden) once graph size warrants
- Expose as a MCP tool so the AI Research Assistant (DEV026) can traverse
