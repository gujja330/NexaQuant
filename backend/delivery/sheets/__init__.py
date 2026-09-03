"""New sheet builders for Sprint A · staged for wiring into the shipped workbook.

Wiring into scripts/build_aegis_3sheet_workbook.py is a separate follow-up
step gated by S18 (file lockdown) + S20 (CEO dry-run). These modules emit
the sheet CONTENT (rows/columns/styles) · the workbook builder invokes them
when the runner_registry declares the sheet.
"""
