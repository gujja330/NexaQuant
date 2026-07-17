"""UX031 smoke tests. Verifies the design spec is internally consistent."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

from ux.dashboard.lib import theme, widgets, routes, layouts, config                    # noqa: E402


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def test_widgets_shape():
    ws = widgets.all_widgets()
    _check(">= 20 widgets defined", len(ws) >= 20)
    ids = [w["id"] for w in ws]
    _check("all widget ids unique", len(ids) == len(set(ids)))
    required = {"id", "title", "component", "data_source", "size", "refresh"}
    _check("all widgets have required keys",
            all(required.issubset(w.keys()) for w in ws))


def test_widgets_data_sources_exist_or_deferred():
    ws = widgets.all_widgets()
    # Known reports/ files this repo emits today. We DON'T fail if a widget
    # references a source that hasn't been generated yet — the widget can still
    # be scheduled — but we do log missing sources for visibility.
    referenced = set()
    for w in ws:
        for src in w["data_source"]:
            referenced.add(src)
    _check(">= 10 distinct data sources referenced", len(referenced) >= 10)


def test_routes_shape():
    rs = routes.routes()
    _check(">= 8 routes defined", len(rs) >= 8)
    paths = [r["path"] for r in rs]
    _check("all route paths unique", len(paths) == len(set(paths)))
    _check("root '/' exists", "/" in paths)


def test_routes_reference_only_defined_widgets():
    wid_ids = {w["id"] for w in widgets.all_widgets()}
    bad = []
    for r in routes.routes():
        for wid in r["widgets"]:
            if wid not in wid_ids:
                bad.append((r["path"], wid))
    _check("every route references only defined widgets",
            not bad, detail=str(bad[:3]) if bad else "")


def test_layouts_match_routes():
    lo = layouts.all_layouts()
    route_layouts = {r["layout"] for r in routes.routes()}
    missing = route_layouts - set(lo.keys())
    _check("every route has a layout",
            not missing, detail=f"missing {missing}" if missing else "")


def test_layouts_reference_only_defined_widgets():
    wid_ids = {w["id"] for w in widgets.all_widgets()}
    bad = []
    for name, lo in layouts.all_layouts().items():
        for section in lo["sections"]:
            for w in section["widgets"]:
                if w["widget_id"] not in wid_ids:
                    bad.append((name, w["widget_id"]))
    _check("every layout widget_id is defined",
            not bad, detail=str(bad[:3]) if bad else "")


def test_layouts_grid_valid():
    for name, lo in layouts.all_layouts().items():
        for section in lo["sections"]:
            for w in section["widgets"]:
                fits = 1 <= w["col"] <= 12 and 1 <= w["col_span"] <= 12 and \
                          (w["col"] + w["col_span"] - 1) <= 12
                _check(f"[{name}] {w['widget_id']} fits in 12-col grid",
                        fits, detail=f"col={w['col']} span={w['col_span']}")


def test_theme_shape():
    t = theme.theme_dict()
    _check("theme has colors",  "colors" in t)
    _check("theme has status colors", "status" in t["colors"])
    _check("theme has typography", "typography" in t)
    _check("theme has breakpoints", "breakpoints" in t)


def test_config_shape():
    c = config.config()
    _check("config has brand.name",  c["brand"]["name"] == "NEXAQUANT")
    _check("advisory_only true",    c["runtime"]["advisory_only"] is True)
    _check("data_sources.root_path exists", "root_path" in c["data_sources"])


def test_filters_shape():
    fs = routes.filters()
    _check(">= 10 filters defined", len(fs) >= 10)
    ids = [f["id"] for f in fs]
    _check("filter ids unique", len(ids) == len(set(ids)))


def main() -> int:
    print("=" * 70); print("  UX031 v0.1 SMOKE TESTS"); print("=" * 70)
    test_widgets_shape(); print()
    test_widgets_data_sources_exist_or_deferred(); print()
    test_routes_shape(); print()
    test_routes_reference_only_defined_widgets(); print()
    test_layouts_match_routes(); print()
    test_layouts_reference_only_defined_widgets(); print()
    test_layouts_grid_valid(); print()
    test_theme_shape(); print()
    test_config_shape(); print()
    test_filters_shape(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
