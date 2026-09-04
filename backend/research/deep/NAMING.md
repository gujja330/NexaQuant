# Deep Research File Naming Convention

Per AEGIS Master v2 · 2026-09-03 · §D.1.1 authoritative table.
This supersedes the earlier draft that assigned `N20` to narrative and `X19` to a
cross-signal prefix · V2 corrects to code-implemented numbering.

| Prefix | Meaning | Domains |
|--------|---------|---------|
| **F**  | Fundamentals | F01-F05 (business quality · balance sheet · accounting quality · valuation · growth) |
| **S**  | Sector / Industry | D06 (kept D-prefix in code — S is the semantic label) |
| **T**  | Technicals | T09 (deep technical) |
| **M**  | Macro / Regime / Cross-market | D07, D17 (kept D-prefix in code — M is the semantic label) |
| **R**  | Risk | D14 (kept D-prefix in code — R is the semantic label) |
| **P**  | Portfolio | D15 (kept D-prefix in code — P is the semantic label) |
| **E**  | Exit / Execution | D16 (kept D-prefix in code — E is the semantic label) |
| **G**  | Governance | D11 (kept D-prefix in code — G is the semantic label) |
| **N**  | Narrative | D12 (kept D-prefix in code — N is the semantic label · **not N20**) |
| _(unprefixed)_ | Corporate events · KG/ownership · flows/crowding · data integrity · statistical robustness · failure research | D08, D10, D13, D18, D19, D20 |

**Rule** · new domain files use the semantic prefix + zero-padded number where the
prefix cleanly maps (F01-F05 · T09). For domains where semantic-prefix rename
would break existing imports without benefit, keep the `dNN_*.py` filename and
carry the semantic prefix only as a label in this table.

**Explicitly retired** · the earlier draft mapping `N20 = narrative` and
`X19 = cross-signal` — V2 §D.1.1 confirms narrative is D12 and D19 is
statistical robustness, not an X-prefixed cross-signal category.
