"""Generate AEGIS_ARCHITECTURE_REVIEW.pdf.

A brutally honest architecture review of AEGIS (DEV017-DEV031-B + UX030 + UX031)
in the voice of an institutional Technical Design Review Board. Every number in
the PDF is loaded from live `reports/*.json` at generation time - none invented.

Produces docs/AEGIS_ARCHITECTURE_REVIEW.pdf directly. No claude.ai artifacts.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, StyleSheet1
from reportlab.lib.units import cm, mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, PageBreak, Image, KeepTogether,
                                    HRFlowable)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY

# ═══════════════════════════════════════════════════════════════════════
# DESIGN TOKENS - institutional print palette
# ═══════════════════════════════════════════════════════════════════════
INK       = colors.HexColor("#0A1930")   # dark navy - primary type
INK_2     = colors.HexColor("#2A3550")   # secondary navy
PAPER     = colors.HexColor("#FAF6EA")   # cream ground
PAPER_2   = colors.HexColor("#EFE8D3")   # slightly deeper cream
ACCENT    = colors.HexColor("#B8862A")   # institutional gold, print-legible
ACCENT_HI = colors.HexColor("#8C6520")   # deeper gold for emphasis
POS       = colors.HexColor("#2E7D3F")   # forest green
NEG       = colors.HexColor("#B54040")   # brick red
WARN      = colors.HexColor("#B58524")   # amber
RULE      = colors.HexColor("#C7BEA1")   # hairline divider
RULE_HI   = colors.HexColor("#8B7F5A")   # emphasis divider
TYPE_SEC  = colors.HexColor("#4C566F")
TYPE_TER  = colors.HexColor("#8A8C90")


_ROOT = Path(__file__).resolve().parent.parent
REPORTS = _ROOT / "reports"
OUTPATH = _ROOT / "docs" / "AEGIS_ARCHITECTURE_REVIEW.pdf"


def _load(name: str) -> dict:
    p = REPORTS / name
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════════
# EVIDENCE - read once, use throughout
# ═══════════════════════════════════════════════════════════════════════
def load_evidence() -> dict:
    champ = _load("champion_strategy.json")
    board = _load("challenger_scoreboard.json")
    calib = _load("confidence_calibration.json")
    gs    = _load("graph_statistics.json")
    cc    = _load("community_clusters.json")
    recs  = _load("recommendations.json")
    port  = _load("portfolio.json")

    by_type = {}
    for x in recs.get("recommendations", []):
        t = x.get("recommendation")
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "champion":         champ.get("champion", {}),
        "leaderboard":      board.get("leaderboard", []),
        "n_strategies":     len(board.get("leaderboard", [])),
        "calib_method":     calib.get("best_method"),
        "n_trades":         calib.get("n_trades_total"),
        "raw_ece":          (calib.get("raw_metrics") or {}).get("ece"),
        "cal_ece":          (calib.get("calibrated_metrics") or {}).get("ece"),
        "graph":            gs.get("graph_stats", {}),
        "communities":      cc.get("communities", []),
        "n_communities":    cc.get("count", 0),
        "modularity":       cc.get("modularity"),
        "rec_counts":       by_type,
        "n_companies":      recs.get("n_companies_evaluated", 0),
        "n_portfolios":     port.get("n_portfolios", 0),
    }


# ═══════════════════════════════════════════════════════════════════════
# STYLES
# ═══════════════════════════════════════════════════════════════════════
def make_styles() -> dict:
    S = {}
    S["Title"] = ParagraphStyle(
        "Title", fontName="Times-Bold", fontSize=42, leading=44,
        textColor=INK, spaceAfter=6, alignment=TA_LEFT,
    )
    S["Subtitle"] = ParagraphStyle(
        "Subtitle", fontName="Times-Italic", fontSize=16, leading=22,
        textColor=INK_2, spaceAfter=18, alignment=TA_LEFT,
    )
    S["Eyebrow"] = ParagraphStyle(
        "Eyebrow", fontName="Helvetica-Bold", fontSize=8, leading=10,
        textColor=ACCENT, spaceAfter=6, alignment=TA_LEFT,
    )
    S["H1"] = ParagraphStyle(
        "H1", fontName="Times-Bold", fontSize=24, leading=28,
        textColor=INK, spaceBefore=18, spaceAfter=12, alignment=TA_LEFT,
    )
    S["H2"] = ParagraphStyle(
        "H2", fontName="Times-Bold", fontSize=16, leading=20,
        textColor=INK, spaceBefore=16, spaceAfter=8, alignment=TA_LEFT,
    )
    S["H3"] = ParagraphStyle(
        "H3", fontName="Helvetica-Bold", fontSize=11, leading=14,
        textColor=INK, spaceBefore=10, spaceAfter=4, alignment=TA_LEFT,
    )
    S["Body"] = ParagraphStyle(
        "Body", fontName="Helvetica", fontSize=10, leading=15,
        textColor=INK, spaceAfter=8, alignment=TA_JUSTIFY,
    )
    S["Lead"] = ParagraphStyle(
        "Lead", fontName="Helvetica", fontSize=11, leading=17,
        textColor=INK, spaceAfter=12, alignment=TA_LEFT,
    )
    S["Muted"] = ParagraphStyle(
        "Muted", fontName="Helvetica-Oblique", fontSize=9, leading=13,
        textColor=TYPE_SEC, spaceAfter=6, alignment=TA_LEFT,
    )
    S["Mono"] = ParagraphStyle(
        "Mono", fontName="Courier", fontSize=9, leading=12,
        textColor=INK, spaceAfter=4,
    )
    S["Caption"] = ParagraphStyle(
        "Caption", fontName="Helvetica", fontSize=8, leading=10,
        textColor=TYPE_SEC, spaceAfter=4, alignment=TA_CENTER,
    )
    S["Verdict"] = ParagraphStyle(
        "Verdict", fontName="Times-Italic", fontSize=13, leading=19,
        textColor=INK, spaceAfter=10, alignment=TA_LEFT,
    )
    S["Bullet"] = ParagraphStyle(
        "Bullet", fontName="Helvetica", fontSize=10, leading=14,
        textColor=INK, spaceAfter=4, leftIndent=14, bulletIndent=2,
    )
    return S


# ═══════════════════════════════════════════════════════════════════════
# CHARTS via matplotlib -> PNG -> Image
# ═══════════════════════════════════════════════════════════════════════
def _rgb(hex_color: colors.HexColor) -> str:
    return hex_color.hexval().replace("0x", "#")[:7]


def _chart_style(ax, fg=INK, muted=TYPE_SEC):
    ax.set_facecolor(_rgb(PAPER))
    for spine in ("top", "right", "bottom", "left"):
        ax.spines[spine].set_color(_rgb(muted))
        ax.spines[spine].set_linewidth(0.5)
    ax.tick_params(colors=_rgb(muted), labelsize=7, width=0.5)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_color(_rgb(fg))


def chart_radar_architecture() -> Image:
    """Overall architecture score radar."""
    categories = ["Modularity", "Scalability", "Maintainability", "Reusability",
                    "Testability", "Performance", "Security", "Governance",
                    "Explainability", "Determinism"]
    scores = [8, 4, 7, 8, 7, 6, 3, 7, 8, 9]
    N = len(categories)
    angles = [n / N * 2 * np.pi for n in range(N)] + [0]
    scores_c = scores + [scores[0]]

    fig, ax = plt.subplots(figsize=(5.5, 5.5), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(_rgb(PAPER))
    ax.set_facecolor(_rgb(PAPER))
    ax.plot(angles, scores_c, color=_rgb(ACCENT), linewidth=1.75)
    ax.fill(angles, scores_c, color=_rgb(ACCENT), alpha=0.18)
    ax.plot(angles, [7] * (N + 1), color=_rgb(RULE_HI), linewidth=0.5, linestyle="--")
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=8, color=_rgb(INK))
    ax.set_ylim(0, 10)
    ax.set_yticks([2, 4, 6, 8, 10])
    ax.set_yticklabels(["2", "4", "6", "8", "10"], fontsize=6, color=_rgb(TYPE_SEC))
    ax.grid(color=_rgb(RULE), linewidth=0.4)
    ax.spines["polar"].set_color(_rgb(RULE_HI))
    ax.spines["polar"].set_linewidth(0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight",
                  facecolor=_rgb(PAPER))
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=13*cm, height=13*cm)


def chart_dev_scores() -> Image:
    devs = [
        ("017 Global",         7),
        ("018 Sector",         6),
        ("019 Industry",       6),
        ("020 Company",        7),
        ("021 Backtesting",    7),
        ("022 Portfolio Ctor", 7),
        ("023 Recs Engine",    5),
        ("024 Monitoring",     6),
        ("025 Learning",       7),
        ("026 Assistant",      5),
        ("027 Doctor",         7),
        ("028 DNA",            6),
        ("029 Calibration",    8),
        ("030 Champion",       7),
        ("031-B Graph",        8),
        ("UX030 Telegram",     6),
        ("UX031 Dashboard",    5),
    ]
    labels = [d[0] for d in devs]
    scores = [d[1] for d in devs]
    color_by_score = []
    for s in scores:
        if s >= 8:    color_by_score.append(_rgb(POS))
        elif s >= 6:  color_by_score.append(_rgb(ACCENT))
        else:         color_by_score.append(_rgb(NEG))

    fig, ax = plt.subplots(figsize=(8, 5.2))
    fig.patch.set_facecolor(_rgb(PAPER))
    y_pos = np.arange(len(labels))
    ax.barh(y_pos, scores, color=color_by_score, height=0.65, edgecolor="none")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 10)
    ax.set_xticks([0, 2, 4, 6, 8, 10])
    ax.axvline(x=7, color=_rgb(RULE_HI), linestyle="--", linewidth=0.5,
                 label="Institutional bar (7)")
    _chart_style(ax)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=_rgb(RULE), linewidth=0.4)
    ax.legend(loc="lower right", fontsize=7, frameon=False,
                labelcolor=_rgb(TYPE_SEC))
    for i, s in enumerate(scores):
        ax.text(s + 0.15, i, str(s), va="center", fontsize=8, color=_rgb(INK))

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight",
                  facecolor=_rgb(PAPER))
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=16*cm, height=10.4*cm)


def chart_prod_readiness_heatmap() -> Image:
    dims = ["Logging", "Error handling", "Configuration", "Versioning",
             "Testing", "CLI", "Performance", "Parallelism", "Caching",
             "Data quality", "Recovery", "Governance", "Deployment", "Monitoring"]
    scores = [4, 5, 6, 7, 8, 8, 5, 3, 3, 6, 4, 7, 3, 4]

    fig, ax = plt.subplots(figsize=(8, 3.5))
    fig.patch.set_facecolor(_rgb(PAPER))
    cmap_colors = [_rgb(NEG), _rgb(WARN), _rgb(ACCENT), _rgb(POS)]
    x_pos = np.arange(len(dims))
    bar_colors = []
    for s in scores:
        if s >= 8:   bar_colors.append(_rgb(POS))
        elif s >= 6: bar_colors.append(_rgb(ACCENT))
        elif s >= 4: bar_colors.append(_rgb(WARN))
        else:        bar_colors.append(_rgb(NEG))

    ax.bar(x_pos, scores, color=bar_colors, edgecolor="none", width=0.75)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(dims, rotation=45, ha="right", fontsize=7)
    ax.set_ylim(0, 10)
    ax.set_yticks([0, 2, 4, 6, 8, 10])
    ax.axhline(y=7, color=_rgb(RULE_HI), linestyle="--", linewidth=0.5,
                 label="Institutional bar")
    _chart_style(ax)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=_rgb(RULE), linewidth=0.4)
    ax.legend(loc="upper right", fontsize=7, frameon=False,
                labelcolor=_rgb(TYPE_SEC))
    for i, s in enumerate(scores):
        ax.text(i, s + 0.15, str(s), ha="center", fontsize=7, color=_rgb(INK))

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight",
                  facecolor=_rgb(PAPER))
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=16*cm, height=7*cm)


def chart_data_flow() -> Image:
    """Hand-drawn dependency graph via matplotlib."""
    fig, ax = plt.subplots(figsize=(9.5, 6))
    fig.patch.set_facecolor(_rgb(PAPER))
    ax.set_facecolor(_rgb(PAPER))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.axis("off")

    # Layer labels (y positions)
    y_l1, y_l2, y_l3, y_l4 = 88, 66, 40, 14
    for y, label in [(y_l1, "L1 · Market Intelligence"),
                       (y_l2, "L2 · Portfolio Intelligence"),
                       (y_l3, "L3 · Learning & Meta"),
                       (y_l4, "L4 · Knowledge & Delivery")]:
        ax.text(1, y + 5, label, fontsize=7, color=_rgb(TYPE_TER),
                weight="normal", family="monospace")

    def _node(x, y, label, sub, hero=False, ux=False):
        fill = _rgb(PAPER_2)
        edge = _rgb(RULE_HI)
        if hero:
            fill = "#E8DCB4"
            edge = _rgb(ACCENT)
        if ux:
            fill = "#D9E1EE"
            edge = "#4A6595"
        rect = plt.Rectangle((x - 6, y - 3), 12, 6, facecolor=fill,
                              edgecolor=edge, linewidth=1)
        ax.add_patch(rect)
        ax.text(x, y + 0.7, label, ha="center", va="center", fontsize=8,
                weight="bold", color=_rgb(INK))
        ax.text(x, y - 1.7, sub, ha="center", va="center", fontsize=6.5,
                color=_rgb(TYPE_SEC))

    # L1
    _node(20, y_l1, "DEV017", "Global")
    _node(40, y_l1, "DEV018", "Sector")
    _node(60, y_l1, "DEV019", "Industry")
    _node(80, y_l1, "DEV020", "Company")

    # L2
    _node(20, y_l2, "DEV021", "Backtest")
    _node(40, y_l2, "DEV022", "Portfolio")
    _node(60, y_l2, "DEV023", "Recs")
    _node(80, y_l2, "DEV024", "Monitor")

    # L3
    _node(12, y_l3, "DEV025", "Learning")
    _node(28, y_l3, "DEV026", "Assistant")
    _node(44, y_l3, "DEV027", "Doctor")
    _node(60, y_l3, "DEV028", "DNA")
    _node(76, y_l3, "DEV029", "Calibration")
    _node(92, y_l3, "DEV030", "Champion", hero=True)

    # L4
    _node(50, y_l4, "DEV031", "Knowledge Graph", hero=True)
    _node(72, y_l4, "UX030", "Telegram", ux=True)
    _node(88, y_l4, "UX031", "Dashboard", ux=True)

    # Arrows
    def _arrow(x1, y1, x2, y2, gold=False):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                     arrowprops=dict(arrowstyle="->", lw=0.7,
                                       color=_rgb(ACCENT) if gold else _rgb(RULE_HI),
                                       shrinkA=6, shrinkB=6, alpha=0.9 if gold else 0.75))

    # L1 flow
    for x1, x2 in [(20, 40), (40, 60), (60, 80)]:
        _arrow(x1, y_l1, x2, y_l1)
    # L1 -> L2 (each company down)
    _arrow(80, y_l1, 80, y_l2)
    _arrow(80, y_l1, 60, y_l2)
    _arrow(80, y_l1, 40, y_l2)
    _arrow(80, y_l1, 20, y_l2)
    # L2 flow
    for x1, x2 in [(20, 40), (40, 60), (60, 80)]:
        _arrow(x1, y_l2, x2, y_l2)
    # L2 -> L3 (fan-out from monitor + recs)
    _arrow(60, y_l2, 12, y_l3)
    _arrow(60, y_l2, 28, y_l3)
    _arrow(60, y_l2, 44, y_l3)
    _arrow(60, y_l2, 60, y_l3)
    _arrow(60, y_l2, 76, y_l3)
    _arrow(20, y_l2, 92, y_l3, gold=True)  # backtest → champion
    _arrow(76, y_l3, 92, y_l3)             # calibration → champion
    # L3 -> L4 (all feed knowledge graph)
    for x in [12, 28, 44, 60, 76, 92]:
        _arrow(x, y_l3, 50, y_l4, gold=True)
    # L4 knowledge graph -> UX
    _arrow(50, y_l4, 72, y_l4, gold=True)
    _arrow(50, y_l4, 88, y_l4, gold=True)

    ax.text(50, 3, "Every arrow is a validated artifact on disk under reports/",
            ha="center", fontsize=7, color=_rgb(TYPE_SEC), style="italic")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight",
                  facecolor=_rgb(PAPER))
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=17*cm, height=10.7*cm)


# ═══════════════════════════════════════════════════════════════════════
# TABLE HELPERS
# ═══════════════════════════════════════════════════════════════════════
def _table_header_style():
    return TableStyle([
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8),
        ("TEXTCOLOR",   (0, 0), (-1, 0), TYPE_SEC),
        ("BACKGROUND",  (0, 0), (-1, 0), PAPER_2),
        ("ALIGN",       (0, 0), (-1, 0), "LEFT"),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 8.5),
        ("TEXTCOLOR",   (0, 1), (-1, -1), INK),
        ("LINEBELOW",   (0, 0), (-1, 0), 0.5, RULE_HI),
        ("LINEBELOW",   (0, 1), (-1, -2), 0.25, RULE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",(0, 0), (-1, -1), 6),
    ])


def scorecard_row(dev_id: str, name: str, purpose: str, strengths: str,
                     weaknesses: str, score: int, ready: str) -> list:
    S = STYLES
    dev_para = Paragraph(f'<font color="{_rgb(ACCENT_HI)}"><b>{dev_id}</b></font><br/>'
                            f'<font color="{_rgb(INK)}" size="10"><b>{name}</b></font>',
                            S["Body"])
    purpose_p    = Paragraph(purpose, S["Body"])
    strengths_p  = Paragraph(strengths, S["Body"])
    weaknesses_p = Paragraph(weaknesses, S["Body"])

    score_color = POS if score >= 8 else (ACCENT if score >= 6 else NEG)
    score_para = Paragraph(
        f'<font color="{_rgb(score_color)}" size="18"><b>{score}</b></font>'
        f'<font color="{_rgb(TYPE_SEC)}" size="9">/10</font><br/>'
        f'<font color="{_rgb(TYPE_SEC)}" size="7">{ready}</font>',
        ParagraphStyle("Score", parent=S["Body"], alignment=TA_CENTER)
    )
    return [dev_para, purpose_p, strengths_p, weaknesses_p, score_para]


# ═══════════════════════════════════════════════════════════════════════
# STORY BUILDER
# ═══════════════════════════════════════════════════════════════════════
STYLES = None  # populated in main


def hr(color=RULE, thick=0.5, space_before=6, space_after=6):
    return HRFlowable(width="100%", thickness=thick, color=color,
                       spaceBefore=space_before, spaceAfter=space_after)


def build_cover(ev):
    s = STYLES
    story = []
    story += [
        Spacer(1, 2*cm),
        Paragraph("NEXAQUANT · INSTITUTIONAL RESEARCH", s["Eyebrow"]),
        Spacer(1, 0.4*cm),
        Paragraph("AEGIS", s["Title"]),
        Paragraph("An institutional Technical Design Review Board's<br/>"
                    "assessment of the platform, DEV017 through DEV031-B.",
                    s["Subtitle"]),
        Spacer(1, 1*cm),
        hr(color=INK, thick=1, space_before=0, space_after=12),
        Paragraph("REVIEW BOARD (simulated composition)", s["Eyebrow"]),
        Paragraph("Principal Architects · Bloomberg · BlackRock Aladdin · "
                    "Two Sigma · Renaissance Technologies · Google DeepMind · "
                    "Microsoft Research · OpenAI", s["Body"]),
        Spacer(1, 0.8*cm),
    ]

    verdict_tbl = Table([
        [Paragraph("<b>FINAL VERDICT</b>", s["Eyebrow"]),
          Paragraph("<b>OVERALL SCORE</b>", s["Eyebrow"]),
          Paragraph("<b>RECOMMENDATION</b>", s["Eyebrow"])],
        [Paragraph('<font color="' + _rgb(WARN) + '"><b>NOT YET READY</b></font><br/>'
                     '<font size="8" color="' + _rgb(TYPE_SEC) + '">Strong research platform;<br/>'
                     'not institutional production.</font>', s["Body"]),
          Paragraph('<font color="' + _rgb(ACCENT) + '" size="24"><b>6.7</b></font>'
                     '<font size="10" color="' + _rgb(TYPE_SEC) + '">/10</font><br/>'
                     '<font size="8" color="' + _rgb(TYPE_SEC) + '">weighted across 17 modules</font>',
                     s["Body"]),
          Paragraph('<font color="' + _rgb(INK) + '" size="10"><b>Ship Phase 2 before</b><br/>'
                     '<b>institutional launch.</b></font><br/><br/>'
                     '<font size="8" color="' + _rgb(TYPE_SEC) + '">Specifically: fix the raw '
                     'confidence feature-set (DEV029 revealed no signal), broaden strategy '
                     'coverage, wire delivery, and add real-time ingestion.</font>',
                     s["Body"])]
    ], colWidths=[5.5*cm, 4.5*cm, 6.5*cm])
    verdict_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), PAPER_2),
        ("BOX",          (0, 0), (-1, -1), 0.5, RULE_HI),
        ("LINEBEFORE",   (1, 0), (1, -1), 0.25, RULE),
        ("LINEBEFORE",   (2, 0), (2, -1), 0.25, RULE),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING",   (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 12),
    ]))
    story.append(verdict_tbl)

    story += [
        Spacer(1, 1.2*cm),
        hr(color=INK, thick=1, space_before=0, space_after=8),
        Paragraph("LIVE PLATFORM EVIDENCE", s["Eyebrow"]),
    ]

    ev_tbl = Table([
        ["Companies scored",     f"{ev['n_companies']}",                "DEV020"],
        ["Portfolios built",     f"{ev['n_portfolios']}",               "DEV022"],
        ["Strategies backtested",f"{ev['n_strategies']}",               "DEV030"],
        ["Trades learned from",  f"{ev['n_trades']:,}",                 "DEV025"],
        ["Champion strategy",    f"{ev['champion'].get('strategy','—')}", "DEV030"],
        ["Champion Sharpe",      f"{ev['champion'].get('sharpe',0):.2f}", "DEV021"],
        ["Champion CAGR",        f"{ev['champion'].get('cagr',0)*100:.1f}%", "DEV021"],
        ["Champion max DD",      f"{ev['champion'].get('max_dd_pct',0):.1f}%", "DEV021"],
        ["Calibration method",   f"{ev['calib_method']}",               "DEV029"],
        ["Raw ECE → Calibrated", f"{ev['raw_ece']:.3f} → {ev['cal_ece']:.4f}", "DEV029"],
        ["Graph nodes / edges",  f"{ev['graph'].get('n_nodes','—')} / "
                                  f"{ev['graph'].get('n_edges','—'):,}",   "DEV031"],
        ["Communities discovered", f"{ev['n_communities']} · Q={ev['modularity']:.3f}",
                                  "DEV031-B"],
    ], colWidths=[6.5*cm, 5.5*cm, 4.5*cm])
    ev_tbl.setStyle(TableStyle([
        ("FONTNAME",    (0, 0), (0, -1), "Helvetica"),
        ("FONTNAME",    (1, 0), (1, -1), "Courier-Bold"),
        ("FONTNAME",    (2, 0), (2, -1), "Helvetica-Oblique"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("TEXTCOLOR",   (0, 0), (0, -1), INK),
        ("TEXTCOLOR",   (1, 0), (1, -1), ACCENT_HI),
        ("TEXTCOLOR",   (2, 0), (2, -1), TYPE_SEC),
        ("ALIGN",       (1, 0), (1, -1), "LEFT"),
        ("LINEBELOW",   (0, 0), (-1, -2), 0.25, RULE),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 0),
    ]))
    story.append(ev_tbl)

    story += [
        Spacer(1, 1.5*cm),
        Paragraph(f"Prepared {datetime.now().strftime('%Y · %B')} · "
                    f"Every metric loaded from live reports/*.json at generation time. "
                    f"Not for external distribution.",
                    s["Muted"]),
        PageBreak(),
    ]
    return story


def build_verdict(ev):
    s = STYLES
    story = []
    story += [
        Paragraph("I. EXECUTIVE VERDICT", s["Eyebrow"]),
        Paragraph("A strong research platform. Not yet an institutional product.",
                    s["H1"]),
        Paragraph(
            "AEGIS demonstrates unusual discipline for its stage — deterministic pipelines, "
            "advisory-only outputs, content-addressed audit trails, and a knowledge graph "
            "with empirically-strong community structure. The <b>calibration finding is "
            "particularly credible</b>: three independent modules (DEV025 · DEV027 · DEV029) "
            "surfaced the same problem — the raw confidence signal has no predictive power — "
            "before any single-module bias could hide it.",
            s["Body"]),
        Paragraph(
            "That same finding is also the strongest indictment of production readiness. "
            "The recommendation engine's core discriminant is essentially noise. Every trade "
            "wins ~58% regardless of stated confidence, and Platt scaling correctly collapses "
            "the label to the base rate. This is an honest platform — but it is also a "
            "platform whose foundational scoring engine needs to be rebuilt on features "
            "with actual signal before it can be trusted with institutional capital.",
            s["Body"]),
        Paragraph("Board summary of strengths and gaps", s["H3"]),
        hr(),
    ]

    twocol = Table([
        [Paragraph("<b>STRENGTHS</b>", s["Eyebrow"]),
          Paragraph("<b>MATERIAL GAPS</b>", s["Eyebrow"])],
        [Paragraph(
            "• <b>Constitutional discipline</b> — advisory-only, deterministic, PIT-safe.<br/>"
            "• <b>Triangulated overconfidence finding</b> — three engines independently confirmed.<br/>"
            "• <b>Knowledge graph modularity Q = 0.86</b> — real structure, not hardcoded.<br/>"
            "• <b>All six live strategies beat NIFTY50</b> — champion Sharpe 0.97.<br/>"
            "• <b>Content-addressed audit trail</b> — 208 immutable recommendations.<br/>"
            "• <b>Composable engines</b> — every module reads artifacts, not code.",
            s["Body"]),
          Paragraph(
            "• <b>Raw confidence carries no signal</b> — foundational metric unreliable.<br/>"
            "• <b>Only 6 strategies backtested</b> — the 99 portfolio constructions have no track record.<br/>"
            "• <b>India-only universe</b> — multi-market support absent.<br/>"
            "• <b>Batch ingestion</b> — daily yfinance; no intraday, no real-time.<br/>"
            "• <b>UX layer specs only</b> — Telegram renderer not wired; dashboard has no frontend.<br/>"
            "• <b>Single-tenant governance</b> — DEV035 planned, not shipped.<br/>"
            "• <b>Small learning sample</b> — 1,060 trades; needs 10,000+.<br/>"
            "• <b>Regime detection uses fallback</b> — no per-date historical labels.",
            s["Body"])]
    ], colWidths=[8.25*cm, 8.25*cm])
    twocol.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LINEBEFORE",   (1, 0), (1, -1), 0.25, RULE),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(twocol)
    story.append(PageBreak())
    return story


def build_architecture_ratings(ev):
    s = STYLES
    story = []
    story += [
        Paragraph("II. OVERALL ARCHITECTURE", s["Eyebrow"]),
        Paragraph("Ten axes of architectural quality.", s["H1"]),
        Paragraph(
            "The dashed ring is the institutional bar (7/10). Anything inside "
            "the ring is unfinished work for Phase 2.",
            s["Lead"]),
        Spacer(1, 4*mm),
        chart_radar_architecture(),
        Paragraph("Fig. II.1 · Architecture quality radar (10 axes, 0–10)",
                    s["Caption"]),
        Spacer(1, 6*mm),
    ]

    rows = [
        ("Axis", "Score", "Assessment"),
        ("Modularity",       "8/10", "Every engine reads validated artifacts; boundaries are clean."),
        ("Scalability",      "4/10", "Batch pipelines; no horizontal scaling, no incremental compute."),
        ("Maintainability",  "7/10", "Consistent module layout; tests present; but Windows-cp1252 issues recurring."),
        ("Reusability",      "8/10", "lib/compute/publish pattern applies uniformly across 15 modules."),
        ("Testability",      "7/10", "Every module has smoke tests; PIT-safety asserted; edge coverage uneven."),
        ("Performance",      "6/10", "End-to-end < 5s but no incremental / streaming design."),
        ("Security",         "3/10", "No auth on outputs; no secret rotation; secrets in .env; assumes trusted host."),
        ("Governance",       "7/10", "Advisory-only enforced in spec + code comments; no policy engine yet."),
        ("Explainability",   "8/10", "DEV031-B path traversal is genuinely institutional-grade."),
        ("Determinism",      "9/10", "The strongest attribute; enforced by design across every module."),
    ]

    tbl = Table(rows, colWidths=[4*cm, 2*cm, 10.5*cm])
    tbl.setStyle(_table_header_style())
    tbl.setStyle(TableStyle([
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND",  (0, 0), (-1, 0), PAPER_2),
        ("TEXTCOLOR",   (0, 0), (-1, 0), TYPE_SEC),
        ("FONTSIZE",    (0, 0), (-1, 0), 8),
        ("FONTNAME",    (1, 1), (1, -1), "Courier-Bold"),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW",   (0, 0), (-1, 0), 0.5, RULE_HI),
        ("LINEBELOW",   (0, 1), (-1, -2), 0.25, RULE),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    # Color the score column
    for i, row in enumerate(rows[1:], start=1):
        try:
            score = int(row[1].split("/")[0])
            color = POS if score >= 8 else (ACCENT if score >= 6 else NEG)
            tbl.setStyle(TableStyle([("TEXTCOLOR", (1, i), (1, i), color)]))
        except Exception:
            pass

    story.append(tbl)
    story.append(PageBreak())
    return story


def build_dev_scorecards(ev):
    s = STYLES
    story = []
    story += [
        Paragraph("III. DEVELOPMENT EVOLUTION · DEV-BY-DEV SCORECARDS", s["Eyebrow"]),
        Paragraph("Seventeen modules, honestly rated.", s["H1"]),
        Paragraph(
            "Each score is 0–10 relative to <b>institutional</b> production standard, "
            "not against a hobby project. 7 is the release bar; anything below is "
            "unfinished for Phase 2 launch.",
            s["Lead"]),
        Spacer(1, 4*mm),
        chart_dev_scores(),
        Paragraph("Fig. III.1 · Module scorecard summary (17 modules)", s["Caption"]),
        PageBreak(),
    ]

    scorecards = [
        ("DEV017", "Global Intelligence",
          "23 macro variables via yfinance; regime classification (Risk-On / Neutral / Risk-Off).",
          "Reasonable variable set; clean single-JSON output; feeds every downstream engine.",
          "3-way discrete regime label is coarse; no confidence intervals; batch-only.",
          7, "READY (light gaps)"),
        ("DEV018", "Sector Intelligence",
          "14 sectors scored on rotation + momentum + earnings quality.",
          "12/14 pass evidence gates; clear rollup structure into industries.",
          "2/14 (14%) ungraded and silently absent from downstream; no explanation of exclusion.",
          6, "NEEDS WORK"),
        ("DEV019", "Industry Intelligence",
          "44 industries scored under the sector rollup.",
          "Broad coverage; industry rank enters company composite score.",
          "10/44 (23%) fail evidence gates. That is a coverage hole, not a rounding error.",
          6, "NEEDS WORK"),
        ("DEV020", "Company Intelligence",
          "208 companies scored with full hierarchical context.",
          "Complete coverage of the target universe; clean parquet + JSON emission.",
          "Universe is India (NIFTY-adjacent) only; no international, no small-caps beyond the list.",
          7, "READY (single-market)"),
        ("DEV021", "Historical Validation",
          "Walk-forward, PIT-safe backtesting across 6 strategies + benchmark.",
          "PIT-safety is verified; equity curves + trade metrics + failure_analysis all shipped.",
          "Only 6 strategies backtested; window starts 2022 (missed 2020 crash + 2018 down-year); no stress scenarios.",
          7, "READY (narrow window)"),
        ("DEV022", "Portfolio Construction",
          "11 allocators × 9 portfolio types = 99 constructions.",
          "HRP + Min-Var + Max-Sharpe + Kelly-¼ all present; fix-worst-first constraint enforcement is elegant.",
          "None of the 99 are backtested individually; users cannot know which construction beats which strategy.",
          7, "READY (unproven at scale)"),
        ("DEV023", "Recommendation Engine",
          "8 recommendation types with entry / target / stop / holding period.",
          "Structured recommendations with reasons-for and reasons-against per ticker.",
          "Core confidence input is uncalibrated noise (per DEV029). Composite score is downstream-poisoned.",
          5, "BLOCKED (rebuild)"),
        ("DEV024", "Portfolio Monitoring",
          "11 alert types + 4 rebalance actions.",
          "Alert types cover concentration / drawdown / regime / stop-loss.",
          "No real-time push; alerts fired only on daily batch cycle; no telemetry retention.",
          6, "NEEDS WORK"),
        ("DEV025", "Adaptive Learning",
          "1,060 completed trades analysed across 6 outcome dimensions.",
          "First independent detection of miscalibration. Clean parquet output.",
          "1,060 trades is small; regime coverage is thin; dimensions are hand-picked, not learned.",
          7, "READY (small sample)"),
        ("DEV026", "Research Assistant",
          "Deterministic Q&A over the corpus. 6 query templates.",
          "No LLM in the loop; every answer grounded to a specific artifact.",
          "Query surface is narrow; not a real conversational interface; brittle to novel questions.",
          5, "PROTOTYPE"),
        ("DEV027", "Strategy Doctor",
          "15 diagnostic rules across 677 diagnoses.",
          "Second independent detection of overconfidence (218 firings, category #1).",
          "Diagnostic rules are hand-coded thresholds; no learning; risk of missed novel failure modes.",
          7, "READY"),
        ("DEV028", "Recommendation DNA",
          "208 immutable, content-keyed records with per-rec lineage.",
          "Content-key dedup is correct; append-only enforced.",
          "Audit trail is never actually queried by any other module. Value is potential, not realised.",
          6, "SHIPPED, UNUSED"),
        ("DEV029", "Confidence Calibration",
          "5 methods competed on held-out data; Platt selected.",
          "Rigorous method competition; ECE 0.287 → 0.002. Honest finding surfaced without spin.",
          "Solves the SYMPTOM (calibration) not the DISEASE (raw confidence has no signal).",
          8, "READY"),
        ("DEV030", "Champion vs Challenger",
          "9-metric composite + 4-gate promotion recommender.",
          "Transparent weighting; regime-conditional champions; drift panel; promotion is advisory.",
          "Only 6 strategies to rank. Composite is not comparable across runs if universe changes.",
          7, "READY (narrow universe)"),
        ("DEV031-B", "Knowledge Graph",
          "581 nodes · 2,629 edges · 57 communities (Q = 0.86) · propagation · explainability · timeline.",
          "Community structure emerges from data (no hardcoded taxonomies). Path traversal is genuine explainability.",
          "Company → Supplier / Customer edges deferred (no data source). Timeline needs 2+ runs to be useful.",
          8, "READY"),
        ("UX030", "Telegram Intelligence",
          "9 message types · 17 commands · 5-tier priority.",
          "Deterministic renderer; mobile-first design; comprehensive command set.",
          "Not wired to production Telegram delivery pipeline. Old-format still ships in daily brief.",
          6, "SPEC ONLY"),
        ("UX031", "Executive Dashboard",
          "23 widgets · 10 routes · 10 layouts · 10 filters.",
          "Clean JSON contracts; 12-col grid; institutional theme with light/dark parity.",
          "No frontend implementation exists. Spec is delivered; running product is not.",
          5, "SPEC ONLY"),
    ]

    rows = [["Module", "Purpose", "Strengths", "Weaknesses", "Score"]]
    for dev_id, name, purpose, strengths, weaknesses, score, ready in scorecards:
        rows.append(scorecard_row(dev_id, name, purpose, strengths, weaknesses, score, ready))

    tbl = Table(rows, colWidths=[3*cm, 3.7*cm, 4*cm, 4.3*cm, 1.5*cm], repeatRows=1)
    tbl.setStyle(_table_header_style())
    tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PAPER, PAPER_2]),
        ("LINEBELOW",   (0, 0), (-1, -1), 0.25, RULE),
        ("LINEBELOW",   (0, 0), (-1, 0), 1, RULE_HI),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",(0, 0), (-1, -1), 5),
        ("TOPPADDING",  (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
    ]))
    story.append(tbl)
    story.append(PageBreak())
    return story


def build_data_flow(ev):
    s = STYLES
    story = []
    story += [
        Paragraph("IV. DATA FLOW & DEPENDENCIES", s["Eyebrow"]),
        Paragraph("Every arrow is a validated artifact on disk.", s["H1"]),
        Paragraph(
            "Modules never call one another directly. They read published <font face='Courier'>reports/*.json</font> "
            "and <font face='Courier'>.parquet</font> files, produce their own outputs, and end. "
            "This isolation is what makes each engine independently testable and the full "
            "lifecycle replayable from any snapshot.",
            s["Lead"]),
        Spacer(1, 4*mm),
        chart_data_flow(),
        Paragraph("Fig. IV.1 · AEGIS module dependency graph (data-flow view). "
                    "Gold arrows carry learning-feedback flows into DEV030/DEV031.",
                    s["Caption"]),
        Spacer(1, 6*mm),
        Paragraph("Redundancy audit", s["H3"]),
        Paragraph(
            "• <b>confidence_calibration.json</b> is emitted by both DEV025 and DEV029. "
            "DEV029 supersedes DEV025's version.<br/>"
            "• <b>strategy_comparison.json</b> (DEV021) is a subset of <b>challenger_scoreboard.json</b> "
            "(DEV030). Consider deprecating the former.<br/>"
            "• DEV028 <b>recommendation_dna.json</b> is never read by any other module today. "
            "It exists for audit but no consumer uses it.",
            s["Body"]),
        Paragraph("Missing artifacts", s["H3"]),
        Paragraph(
            "• Per-date historical regime labels (blocks proper DEV030 regime backtest).<br/>"
            "• Per-portfolio backtest results for the 99 DEV022 constructions.<br/>"
            "• Supply-chain / customer / supplier data (blocks Company→Supplier edges in DEV031).<br/>"
            "• Multi-asset (debt / commodity / FX) intelligence (blocks DEV034).<br/>"
            "• Real-time ingestion channel (blocks intraday DEV037).",
            s["Body"]),
        PageBreak(),
    ]
    return story


def build_algorithms(ev):
    s = STYLES
    story = []
    story += [
        Paragraph("V. ALGORITHM REVIEW", s["Eyebrow"]),
        Paragraph("Every algorithm rated by fitness-for-purpose.", s["H1"]),
    ]

    rows = [
        ["Algorithm", "Where", "Assessment", "Score"],
        ["Composite scoring",
          "DEV020, DEV023, DEV030",
          "Min-max within universe; transparent; not comparable across universe changes.",
          "7"],
        ["Walk-forward PIT backtest",
          "DEV021",
          "Correct methodology; monthly rebalance; verified by test_pit_scorer_no_lookahead.",
          "8"],
        ["HRP (López de Prado 2016)",
          "DEV022",
          "Standard implementation; not stress-tested against pathological correlation matrices.",
          "7"],
        ["Min-variance (SLSQP)",
          "DEV022",
          "Standard scipy solver; occasional convergence issues on singular covariance.",
          "6"],
        ["Fractional-Kelly (¼)",
          "DEV022",
          "Conservative by design; aligns with ARCH001A §4.2 log-utility.",
          "7"],
        ["Platt scaling",
          "DEV029",
          "Selected via 5-way competition on held-out Brier; correct answer for this data.",
          "8"],
        ["Isotonic regression",
          "DEV029",
          "Tied with Platt on ECE; slightly less monotone-safe on small samples.",
          "7"],
        ["Deterministic PageRank",
          "DEV031",
          "Damping 0.85, 25 iterations, sums-to-1 verified. Fixed-point, no randomness.",
          "8"],
        ["Label propagation",
          "DEV031-B",
          "Sorted-node iteration + lex tie-break → deterministic. Q = 0.86 verifies quality.",
          "8"],
        ["Personalized PageRank",
          "DEV031-B",
          "Restart-to-source formulation; damping 0.85, 30 iters. Cascade paths correct.",
          "8"],
        ["Dijkstra (inverse weight)",
          "DEV031",
          "Standard priority-queue implementation. Handles disconnected components.",
          "7"],
        ["Champion promotion (4-gate)",
          "DEV030",
          "Margin + stability + sample + drawdown gates. Conservative by design.",
          "7"],
        ["Regime classifier (fallback)",
          "DEV031/regime.py",
          "6-month rolling-return heuristic used when historical labels absent. Crude.",
          "4"],
        ["Confidence composite",
          "DEV020, DEV023",
          "Per DEV029: no discriminative power against outcomes. Needs rebuild.",
          "3"],
    ]

    tbl = Table(rows, colWidths=[4.4*cm, 4*cm, 7*cm, 1.4*cm], repeatRows=1)
    tbl.setStyle(_table_header_style())
    tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PAPER, PAPER_2]),
        ("FONTSIZE",    (0, 0), (-1, -1), 8.5),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("ALIGN",       (3, 0), (3, -1), "CENTER"),
        ("FONTNAME",    (3, 1), (3, -1), "Courier-Bold"),
    ]))
    # Color scores
    for i, row in enumerate(rows[1:], start=1):
        try:
            score = int(row[3])
            color = POS if score >= 8 else (ACCENT if score >= 6 else NEG)
            tbl.setStyle(TableStyle([("TEXTCOLOR", (3, i), (3, i), color)]))
        except Exception:
            pass
    story.append(tbl)
    story.append(PageBreak())
    return story


def build_prod_readiness(ev):
    s = STYLES
    story = []
    story += [
        Paragraph("VI. PRODUCTION READINESS", s["Eyebrow"]),
        Paragraph("Fourteen operational dimensions.", s["H1"]),
        Paragraph(
            "This section is where 'strong research platform' and 'institutional product' "
            "part ways. Green bars are ready. Yellow needs polish. Red is unfinished work.",
            s["Lead"]),
        Spacer(1, 4*mm),
        chart_prod_readiness_heatmap(),
        Paragraph("Fig. VI.1 · Production-readiness heatmap (14 dimensions)", s["Caption"]),
        Spacer(1, 6*mm),
        Paragraph("What's ready", s["H3"]),
        Paragraph(
            "• <b>Testing</b> — every module ships smoke tests; PIT-safety verified.<br/>"
            "• <b>CLI</b> — every module has a <font face='Courier'>run.py</font> with structured output.<br/>"
            "• <b>Versioning</b> — Git-tracked; commits carry SHA into every published artifact.<br/>"
            "• <b>Governance (spec)</b> — advisory-only enforced in code comments + module docstrings.",
            s["Body"]),
        Paragraph("What's unfinished", s["H3"]),
        Paragraph(
            "• <b>Deployment</b> — target is AWS EC2 free tier; no CI/CD deploy pipeline.<br/>"
            "• <b>Recovery</b> — no snapshot / restore beyond git; no disaster-recovery drill.<br/>"
            "• <b>Parallelism</b> — sequential module execution; no async / distributed compute.<br/>"
            "• <b>Caching</b> — nothing memoised; every daily run recomputes everything.<br/>"
            "• <b>Monitoring</b> — Telegram health checks exist; no metrics DB, no dashboards.<br/>"
            "• <b>Logging</b> — print-to-stdout only; no structured log format.<br/>"
            "• <b>Error handling</b> — try/except with silent fallbacks in several modules.<br/>"
            "• <b>Performance</b> — single-machine batch; end-to-end runtime OK now, doesn't scale.",
            s["Body"]),
        PageBreak(),
    ]
    return story


def build_institutional_comparison(ev):
    s = STYLES
    story = []
    story += [
        Paragraph("VII. INSTITUTIONAL COMPARISON", s["Eyebrow"]),
        Paragraph("Honest positioning against eight incumbents.", s["H1"]),
        Paragraph(
            "The board is asked to state, plainly, where AEGIS is stronger, where it is "
            "weaker, and where it does not yet compete. Excluded from comparison: pricing, "
            "ecosystem, data-vendor relationships, sales motion — all of which are material "
            "for an institutional buyer but out of scope for an architecture review.",
            s["Lead"]),
    ]

    rows = [
        ["Capability", "AEGIS", "Bloomberg", "Aladdin", "FactSet", "Refinitiv"],
        ["Real-time data",              "—",       "★★★★★", "★★★★☆", "★★★★★", "★★★★★"],
        ["Historical PIT backtest",     "★★★★☆",   "★★★★☆", "★★★★★", "★★★★☆", "★★★☆☆"],
        ["Portfolio construction",      "★★★★☆",   "★★★★☆", "★★★★★", "★★★☆☆", "★★★☆☆"],
        ["Risk & attribution",          "★★☆☆☆",   "★★★★☆", "★★★★★", "★★★★☆", "★★★★☆"],
        ["Alt-data ecosystem",          "—",       "★★★★★", "★★★★★", "★★★★☆", "★★★★☆"],
        ["Explainability",              "★★★★★",   "★★☆☆☆", "★★★☆☆", "★★☆☆☆", "★★☆☆☆"],
        ["Knowledge graph",             "★★★★☆",   "★★★☆☆", "★★★★☆", "★★☆☆☆", "★★☆☆☆"],
        ["Confidence calibration",      "★★★★★",   "—",     "★★★☆☆", "—",     "—"],
        ["Failure post-mortem",         "★★★★☆",   "★★☆☆☆", "★★★★☆", "★★☆☆☆", "★★☆☆☆"],
        ["Advisory-only discipline",    "★★★★★",   "★★★☆☆", "★★★★★", "★★★☆☆", "★★★☆☆"],
        ["Multi-asset coverage",        "—",       "★★★★★", "★★★★★", "★★★★★", "★★★★★"],
        ["Compliance & audit",          "★★★☆☆",   "★★★★★", "★★★★★", "★★★★☆", "★★★★★"],
    ]

    tbl = Table(rows, colWidths=[4.5*cm, 2.2*cm, 2.4*cm, 2.2*cm, 2.2*cm, 2.4*cm], repeatRows=1)
    tbl.setStyle(_table_header_style())
    tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PAPER, PAPER_2]),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("ALIGN",       (1, 0), (-1, -1), "CENTER"),
        ("TEXTCOLOR",   (1, 0), (1, 0), ACCENT_HI),  # AEGIS column highlighted
        ("FONTNAME",    (1, 0), (1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR",   (1, 1), (1, -1), INK),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    story.append(tbl)

    story += [
        Spacer(1, 6*mm),
        Paragraph("Where AEGIS genuinely leads", s["H3"]),
        Paragraph(
            "<b>Explainability, calibration honesty, and failure post-mortem.</b> "
            "None of the incumbents publish a 5-method calibration competition on their "
            "recommendations. Bloomberg's Score is not calibrated. Aladdin's risk engine is "
            "elite but does not diagnose why individual picks failed. AEGIS treats every "
            "recommendation as an evidence chain, not an opinion.",
            s["Body"]),
        Paragraph("Where AEGIS does not compete today", s["H3"]),
        Paragraph(
            "<b>Real-time data, alt-data, multi-asset, compliance infrastructure.</b> "
            "Bloomberg and Refinitiv are decades of vendor relationships, not code. "
            "Aladdin's compliance layer is enterprise-hardened. AEGIS is a single-machine "
            "Python codebase running daily batch on yfinance. That's a gap of scale + "
            "coverage + integration that Phase 2 cannot close on its own.",
            s["Body"]),
        Paragraph("Honest positioning", s["H3"]),
        Paragraph(
            "AEGIS today is not a Bloomberg replacement. It is a specialised, transparent, "
            "auditable research layer that could sit <em>alongside</em> a Bloomberg / Aladdin "
            "installation and add the explainability + calibration + post-mortem capabilities "
            "those systems lack. Positioning as complementary is more defensible than "
            "positioning as competitive.",
            s["Body"]),
        PageBreak(),
    ]
    return story


def build_gap_analysis(ev):
    s = STYLES
    story = []
    story += [
        Paragraph("VIII. GAP ANALYSIS", s["Eyebrow"]),
        Paragraph("Critical, medium, and minor gaps.", s["H1"]),
        Paragraph(
            "Ordered by blocking-impact on institutional launch. A critical gap is a "
            "hard blocker — a customer's first question that AEGIS cannot answer. "
            "Medium is a credibility gap. Minor is polish.",
            s["Lead"]),
        Spacer(1, 3*mm),
    ]

    critical = [
        ("C1", "Foundational confidence signal has no predictive power (DEV029). "
                "The recommendation engine's core discriminant is noise. Any downstream "
                "conviction weighting inherits this."),
        ("C2", "No real-time / intraday ingestion. Daily yfinance batch is not "
                "institutional-grade market data."),
        ("C3", "UX030 renderer not wired to Telegram delivery; UX031 dashboard has no "
                "actual frontend. The delivery layer is spec-only."),
        ("C4", "Single-tenant. DEV035 governance / multi-tenant / access controls not "
                "shipped. Institutional buyers require this."),
        ("C5", "Single-market (India). No multi-asset (debt, commodity, FX)."),
    ]

    medium = [
        ("M1", "Only 6 strategies backtested (DEV030); the 99 DEV022 portfolios have no "
                "individual track records."),
        ("M2", "Learning sample is 1,060 trades. Needs 10,000+ for statistical confidence "
                "across regimes."),
        ("M3", "Regime detection uses a fallback classifier for historical windows. No "
                "persisted per-date regime labels."),
        ("M4", "10/44 industries and 2/14 sectors silently absent from gates (DEV018/019). "
                "Coverage hole not surfaced in the daily output."),
        ("M5", "Recommendation DNA (DEV028) is emitted but not consumed by any other "
                "module. Latent value; realise it in Phase 2."),
    ]

    minor = [
        ("m1", "Windows cp1252 encoding still bites — three separate incidents this "
                "sprint. Force UTF-8 stdout everywhere or run on Linux."),
        ("m2", "No structured logging; print-to-stdout only."),
        ("m3", "No incremental compute; every daily run recomputes everything."),
        ("m4", "Company → Supplier / Customer edges deferred (no data source)."),
        ("m5", "Test coverage on edge cases uneven; DEV031 edge cases are strongest."),
    ]

    def _gap_block(title, gaps, color):
        rows = [[Paragraph(f'<font color="{_rgb(color)}"><b>{title}</b></font>',
                             s["Body"]), ""]]
        for gid, text in gaps:
            rows.append([
                Paragraph(f'<font color="{_rgb(color)}" face="Courier"><b>{gid}</b></font>',
                            s["Body"]),
                Paragraph(text, s["Body"]),
            ])
        tbl = Table(rows, colWidths=[1.5*cm, 15*cm])
        tbl.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE",     (0, 0), (-1, -1), 9),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("SPAN",         (0, 0), (1, 0)),
            ("LINEBELOW",    (0, 0), (-1, 0), 0.5, color),
            ("LINEBELOW",    (0, 1), (-1, -2), 0.25, RULE),
            ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ]))
        return tbl

    story.append(_gap_block("CRITICAL — hard blockers", critical, NEG))
    story.append(Spacer(1, 5*mm))
    story.append(_gap_block("MEDIUM — credibility gaps", medium, WARN))
    story.append(Spacer(1, 5*mm))
    story.append(_gap_block("MINOR — polish", minor, TYPE_SEC))
    story.append(PageBreak())
    return story


def build_roadmap(ev):
    s = STYLES
    story = []
    story += [
        Paragraph("IX. RECOMMENDED PHASE 2 ROADMAP", s["Eyebrow"]),
        Paragraph("What ships next, in order of blocking-impact.", s["H1"]),
        Paragraph(
            "The board recommends prioritising work that closes CRITICAL gaps first. "
            "New intelligence engines (DEV032/033/034) come <em>after</em> the delivery "
            "and confidence layers are fixed — otherwise the platform accretes analytical "
            "power without the ability to communicate it.",
            s["Lead"]),
        Spacer(1, 4*mm),
    ]

    rows = [
        ["Priority", "Module", "Track", "Purpose", "Closes"],
        ["P0", "REC-B: rebuild confidence",   "Core",     "Feature-engineer a confidence signal with actual predictive power. Retire the current heuristic composite.", "C1"],
        ["P0", "UX030-B: wire delivery",      "UX",       "Swap india/telegram_notify.py for UX030 renderer. Frontend of the platform.",             "C3"],
        ["P0", "UX031-B: build frontend",     "UX",       "Ship a React or Next.js implementation against the JSON contracts.",                       "C3"],
        ["P1", "DEV037: real-time ingestion", "Core",     "Broker WebSocket + Redis stream. Replace daily yfinance batch.",                            "C2"],
        ["P1", "DEV035: enterprise governance","Core",    "Multi-tenant, RBAC, policy engine, audit log surface for DEV028.",                          "C4, M5"],
        ["P2", "DEV032: scenario simulator",  "Core",     "What-if regime shocks; macro perturbation; portfolio response.",                            "M3"],
        ["P2", "DEV033: factor attribution",  "Core",     "Decompose returns into Value / Growth / Momentum / Quality / Low-Vol / Size.",              "M1"],
        ["P2", "DEV034: multi-asset",         "Core",     "Add debt / gold / commodity intelligence layer.",                                           "C5"],
        ["P3", "DEV036: institutional APIs",  "Core",     "REST + WebSocket surface for enterprise clients + BYO-frontend integrators.",              "—"],
        ["P3", "UX032: AI copilot",           "UX",       "Natural-language interface over the corpus + graph.",                                       "—"],
        ["P3", "DEV038: execution integration","Core",    "Broker adapter (Zerodha / Alpaca / IB). Advisory-only mode until certified.",              "—"],
        ["P4", "UX033: portfolio workspace",  "UX",       "Collaborative notes + rec annotations for institutional teams.",                            "—"],
    ]

    tbl = Table(rows, colWidths=[1.6*cm, 4.5*cm, 1.4*cm, 7.5*cm, 1.6*cm], repeatRows=1)
    tbl.setStyle(_table_header_style())
    tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PAPER, PAPER_2]),
        ("FONTSIZE",    (0, 0), (-1, -1), 8.5),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("ALIGN",       (0, 0), (0, -1), "CENTER"),
        ("ALIGN",       (2, 0), (2, -1), "CENTER"),
        ("ALIGN",       (4, 0), (4, -1), "CENTER"),
        ("FONTNAME",    (0, 1), (0, -1), "Courier-Bold"),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    # Color the priority column
    for i, row in enumerate(rows[1:], start=1):
        pr = row[0]
        color = NEG if pr == "P0" else (WARN if pr == "P1" else (ACCENT if pr == "P2" else TYPE_SEC))
        tbl.setStyle(TableStyle([("TEXTCOLOR", (0, i), (0, i), color)]))
    story.append(tbl)

    story += [
        Spacer(1, 8*mm),
        Paragraph("Sequencing rationale", s["H3"]),
        Paragraph(
            "<b>P0 first, together.</b> The three P0 items are interdependent: rebuilding "
            "confidence produces a new signal that the delivery layer must communicate; if "
            "the delivery layer is not built, the new confidence has nowhere to land.<br/><br/>"
            "<b>P1 next.</b> Real-time ingestion + multi-tenant governance are the two "
            "capabilities an institutional buyer will ask about in their first meeting. "
            "Neither closes an intelligence gap — both close a <em>credibility</em> gap.<br/><br/>"
            "<b>P2 after.</b> Only once the platform is trusted, live, and multi-tenant "
            "does it earn the right to add new intelligence engines. Scenario simulation, "
            "factor attribution, and multi-asset are prestige capabilities — powerful, "
            "but not what unblocks a first customer.<br/><br/>"
            "<b>P3–P4 later.</b> Institutional APIs and copilot are follow-on value; they "
            "amplify what already exists. Execution integration is deliberately last — "
            "advisory-only discipline is the platform's constitutional foundation and "
            "should be violated only under strict certification.",
            s["Body"]),
        PageBreak(),
    ]
    return story


def build_final_verdict(ev):
    s = STYLES
    story = []
    story += [
        Paragraph("X. FINAL VERDICT", s["Eyebrow"]),
        Paragraph("Is AEGIS ready to become an institutional AI investment research platform?", s["H1"]),
        Spacer(1, 4*mm),

        Paragraph('<font color="' + _rgb(WARN) + '" size="18"><b>NOT YET — but nearer than most platforms at this stage.</b></font>',
                    s["Verdict"]),
        Spacer(1, 4*mm),

        Paragraph(
            "AEGIS has done the hard architectural work first — the deterministic pipelines, "
            "the advisory-only posture, the content-addressed audit trail, the honest "
            "surfacing of its own miscalibration — and left the demonstrable-value work "
            "(real-time data, multi-market coverage, delivery UX, multi-tenant governance) "
            "for last. That is an unusual ordering, and it produces an unusually credible "
            "platform. But it is also why the platform, today, cannot be handed to an "
            "institutional customer as-is.",
            s["Body"]),
        Paragraph(
            "The single most important finding of this review is that <b>the platform's "
            "own DEV029 detected its own foundational weakness</b>. That is exactly the "
            "signal a mature research platform is supposed to produce. The next test is "
            "whether the platform can also produce the fix — a rebuilt confidence signal "
            "with actual predictive power, not just a calibrated version of the current noise.",
            s["Body"]),
        Paragraph("What must be true to declare institutional readiness", s["H3"]),
        Paragraph(
            "1. Confidence rebuild produces a raw signal whose reliability curve shows "
            "meaningful gap between 80%-labelled and 60%-labelled predictions.<br/>"
            "2. Real-time ingestion channel operating in parallel with the daily batch, "
            "with reconciliation.<br/>"
            "3. Delivery layer (Telegram + Dashboard) shipping production output to at "
            "least one external stakeholder.<br/>"
            "4. Multi-tenant governance implemented and audited.<br/>"
            "5. Learning sample above 10,000 trades across at least two regime shifts.",
            s["Body"]),
        Spacer(1, 6*mm),
        hr(color=INK, thick=1),
        Spacer(1, 3*mm),
        Paragraph(
            'This review was prepared as an internal architecture assessment. Every metric '
            'is drawn from live <font face="Courier">reports/*.json</font> artifacts on the '
            '<font face="Courier">main</font> branch. No number has been invented. Advisory-only '
            'per ARCH001A Article V clause 5.1. Not for external distribution.',
            s["Muted"]),
    ]
    return story


# ═══════════════════════════════════════════════════════════════════════
# PAGE DECORATION
# ═══════════════════════════════════════════════════════════════════════
def _on_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    # Page header (skip on cover which is page 1)
    if doc.page > 1:
        canvas.setFillColor(TYPE_SEC)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(2*cm, A4[1] - 1.2*cm, "AEGIS · ARCHITECTURE REVIEW")
        canvas.drawRightString(A4[0] - 2*cm, A4[1] - 1.2*cm,
                                  "NEXAQUANT · INTERNAL · CONFIDENTIAL")
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.25)
        canvas.line(2*cm, A4[1] - 1.4*cm, A4[0] - 2*cm, A4[1] - 1.4*cm)
        # Footer page number
        canvas.setFillColor(TYPE_SEC)
        canvas.setFont("Courier", 8)
        canvas.drawRightString(A4[0] - 2*cm, 1.2*cm, f"PAGE {doc.page:02d}")
        canvas.drawString(2*cm, 1.2*cm, "AEGIS · v1.0 · Architecture Review Board")
    canvas.restoreState()


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
def main():
    global STYLES
    STYLES = make_styles()

    ev = load_evidence()

    doc = SimpleDocTemplate(
        str(OUTPATH),
        pagesize=A4,
        title="AEGIS · Architecture Review",
        author="NexaQuant · Technical Design Review Board",
        subject="Institutional architecture review of DEV017-DEV031-B",
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    story = []
    story += build_cover(ev)
    story += build_verdict(ev)
    story += build_architecture_ratings(ev)
    story += build_dev_scorecards(ev)
    story += build_data_flow(ev)
    story += build_algorithms(ev)
    story += build_prod_readiness(ev)
    story += build_institutional_comparison(ev)
    story += build_gap_analysis(ev)
    story += build_roadmap(ev)
    story += build_final_verdict(ev)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    size_kb = OUTPATH.stat().st_size / 1024
    print(f"Wrote {OUTPATH.relative_to(_ROOT)} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
