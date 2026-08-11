"""AEGIS Research module · canonical outcome dataset + interaction analyses.

CEO-locked P0 (2026-08-11): every research query sources from
outcome_dataset.parquet · never from XLSX. This prevents the class of bug
where different analyses of the same data produce contradictory numbers
(the Investability 75%-vs-25% mismatch that triggered this lock).
"""
