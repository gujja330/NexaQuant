# tools/run_experiment.py
"""
AEGIS experiment automation — the researcher answers "question -> run -> read result"; everything else
(leaderboard append, report archive, dashboard refresh) happens here. NOT framework code; this is the glue.

An experiment script builds result rows + a markdown report, then calls:

    from run_experiment import publish
    publish(program="B-Earnings", report_slug="RC002_earnings_surprise",
            report_md=md, rows=[{...leaderboard row...}])

Rows are appended to LEADERBOARD.csv (never overwritten), the report is archived under
markets/research/experiments/, and RESEARCH_DASHBOARD.md is regenerated. CLI: `python tools/run_experiment.py
result.json` where result.json = {program, report_slug, report_md, rows:[...]}.
"""
import csv, json, subprocess, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "markets" / "research"
LB = RES / "LEADERBOARD.csv"
ARCHIVE = RES / "experiments"


def confidence_score(ir, n):
    """Numeric trust in a verdict (0-100). 40% effective sample (N/12 saturates), 60% IC stability
    (|IR|/3 saturates). A result can't be 'High' without significance, so |IR|<2 caps the score at 60."""
    power = min(1.0, (n or 0) / 12.0)
    consistency = min(1.0, abs(ir or 0) / 3.0)
    raw = 100 * (0.4 * power + 0.6 * consistency)
    if abs(ir or 0) < 2:
        raw = min(raw, 60)
    return round(raw)


def confidence_label(score):
    return "High" if score >= 70 else ("Medium" if score >= 50 else "Low")


def confidence(ir, n):
    """Combined '83 (High)' string for the leaderboard confidence column."""
    s = confidence_score(ir, n)
    return f"{s} ({confidence_label(s)})"


def append_leaderboard(rows):
    header = next(csv.reader(LB.open()))            # preserve existing column order
    with LB.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        for r in rows:
            r.setdefault("date", str(date.today()))
            w.writerow({k: r.get(k, "") for k in header})
    return len(rows)


def archive_report(slug, md):
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    p = ARCHIVE / f"{slug}.md"
    p.write_text(md, encoding="utf-8")
    return p


def refresh_dashboard():
    subprocess.run([sys.executable, str(ROOT / "tools" / "research_dashboard.py")], check=True)


def publish(program, report_slug, report_md, rows):
    for r in rows:
        r.setdefault("program", program)
    n = append_leaderboard(rows)
    p = archive_report(report_slug, report_md)
    refresh_dashboard()
    print(f"  published: +{n} leaderboard row(s) · report {p.relative_to(ROOT)} · dashboard refreshed")


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    d = json.loads(Path(sys.argv[1]).read_text())
    publish(d["program"], d["report_slug"], d["report_md"], d["rows"])


if __name__ == "__main__":
    main()
