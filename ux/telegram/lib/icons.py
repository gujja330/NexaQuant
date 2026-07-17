"""UX030 · visual iconography.

Central registry of every emoji and visual element used in Telegram messages.
No emoji or icon is hardcoded elsewhere — always import from here so the whole
UX can be re-themed in one place."""
from __future__ import annotations


# ── status ────────────────────────────────────────────────────────────────
STATUS = {
    "buy":       "🟢",
    "hold":      "🟡",
    "exit":      "🔴",
    "watch":     "⚪",
    "alert":     "🚨",
    "info":      "ℹ️",
    "warning":   "⚠",
    "success":   "✅",
    "failure":   "❌",
    "up":        "▲",
    "down":      "▼",
    "flat":      "▬",
}


# ── grades ────────────────────────────────────────────────────────────────
GRADES = {
    "A+": "🟢 A+", "A": "🟢 A", "A-": "🟢 A-",
    "B+": "🟡 B+", "B": "🟡 B", "B-": "🟡 B-",
    "C+": "🟠 C+", "C": "🟠 C", "C-": "🟠 C-",
    "D":  "🔴 D",  "F":  "🔴 F",
}


# ── regime ────────────────────────────────────────────────────────────────
REGIME = {
    "Risk-On":  "🟢 Risk-On",
    "Neutral":  "🟡 Neutral",
    "Risk-Off": "🔴 Risk-Off",
    "Unknown":  "⚪ Unknown",
}


# ── sector icons (tenant-generic; the map is a soft hint, not a filter) ──
SECTOR_ICONS = {
    "Information Technology":     "💻",
    "Financial Services":         "🏦",
    "Health Care":                "⚕",
    "Consumer Staples":           "🛒",
    "Consumer Discretionary":     "🛍",
    "Energy":                     "⚡",
    "Materials":                  "🏗",
    "Industrials":                "🏭",
    "Utilities":                  "💡",
    "Communication Services":     "📡",
    "Real Estate":                "🏠",
}


def sector_icon(name: str) -> str:
    return SECTOR_ICONS.get((name or "").strip(), "•")


# ── confidence badges ────────────────────────────────────────────────────
def confidence_stars(conf_pct: float | None) -> str:
    """conf_pct expected in [0, 100]."""
    if conf_pct is None:
        return "☆☆☆☆☆"
    if conf_pct >= 95: return "★★★★★"
    if conf_pct >= 85: return "★★★★☆"
    if conf_pct >= 75: return "★★★☆☆"
    if conf_pct >= 65: return "★★☆☆☆"
    return "★☆☆☆☆"


# ── progress bar (10 cells) ──────────────────────────────────────────────
def progress_bar(value_pct: float | None, cells: int = 10) -> str:
    if value_pct is None:
        return "░" * cells
    v = max(0.0, min(100.0, float(value_pct)))
    filled = int(round(v / 100.0 * cells))
    return "█" * filled + "░" * (cells - filled)


# ── risk levels ──────────────────────────────────────────────────────────
def risk_icon(level: str | None) -> str:
    return {
        "Low":    "🟢 Low",
        "Medium": "🟡 Medium",
        "High":   "🟠 High",
        "Extreme":"🔴 Extreme",
    }.get((level or "").strip(), "⚪ Unknown")


# ── change arrows ────────────────────────────────────────────────────────
def change_arrow(delta: float | None) -> str:
    if delta is None:
        return "▬"
    if delta > 0.001:
        return "▲"
    if delta < -0.001:
        return "▼"
    return "▬"


# ── recommendation type -> status icon ───────────────────────────────────
REC_ICON = {
    "Strong-Buy":  STATUS["buy"] + " STRONG BUY",
    "Buy":         STATUS["buy"] + " BUY",
    "Accumulate":  STATUS["buy"] + " ACCUMULATE",
    "Hold":        STATUS["hold"] + " HOLD",
    "Reduce":      "🟠 REDUCE",
    "Sell":        STATUS["exit"] + " SELL",
    "Avoid":       STATUS["exit"] + " AVOID",
    "Watchlist":   STATUS["watch"] + " WATCH",
}


def rec_icon(rec: str | None) -> str:
    return REC_ICON.get((rec or "").strip(), rec or "")
