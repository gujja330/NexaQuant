"""UX031 · dashboard routes.

Every URL route maps to a layout composed of widget IDs (from `widgets.py`)
plus its own set of applicable filters."""
from __future__ import annotations


def routes() -> list[dict]:
    return [
        {
            "path":     "/",
            "name":     "Executive Overview",
            "icon":     "layout-dashboard",
            "widgets":  [
                "market_regime", "portfolio_grade", "champion_strategy", "confidence_gauge",
                "top_opportunities", "todays_actions",
                "sector_allocation", "risk_alerts",
                "equity_curve",
            ],
            "filters":  [],
            "layout":   "executive_overview",
        },
        {
            "path":     "/market",
            "name":     "Market Overview",
            "icon":     "globe",
            "widgets":  [
                "market_regime",
                "sector_allocation", "industry_allocation",
                "performance_heatmap",
                "regime_champions",
            ],
            "filters":  ["market_regime", "sector"],
            "layout":   "market_overview",
        },
        {
            "path":     "/portfolio",
            "name":     "Portfolio",
            "icon":     "briefcase",
            "widgets":  [
                "portfolio_value", "portfolio_grade",
                "sector_allocation", "industry_allocation",
                "holdings_table",
                "portfolio_dependency_graph",
            ],
            "filters":  ["portfolio", "sector", "industry"],
            "layout":   "portfolio",
        },
        {
            "path":     "/recommendations",
            "name":     "Recommendations",
            "icon":     "target",
            "widgets":  [
                "top_opportunities", "todays_actions",
                "recommendation_timeline",
                "holdings_table",
            ],
            "filters":  ["confidence", "recommendation", "sector"],
            "layout":   "recommendations",
        },
        {
            "path":     "/risk",
            "name":     "Risk",
            "icon":     "shield-alert",
            "widgets":  [
                "risk_alerts", "risk_radar",
                "drawdown_curve",
                "portfolio_grade",
            ],
            "filters":  ["portfolio", "sector"],
            "layout":   "risk",
        },
        {
            "path":     "/performance",
            "name":     "Performance",
            "icon":     "trending-up",
            "widgets":  [
                "equity_curve",
                "win_rate",
                "drawdown_curve",
                "performance_heatmap",
                "challenger_scoreboard",
            ],
            "filters":  ["date", "strategy"],
            "layout":   "performance",
        },
        {
            "path":     "/champion",
            "name":     "Champion Strategy",
            "icon":     "trophy",
            "widgets":  [
                "champion_strategy",
                "challenger_scoreboard",
                "regime_champions",
                "drift_panel",
                "equity_curve",
            ],
            "filters":  ["strategy", "market_regime"],
            "layout":   "champion",
        },
        {
            "path":     "/knowledge",
            "name":     "Knowledge Graph",
            "icon":     "share-2",
            "widgets":  [
                "knowledge_graph",
                "top_influencers",
                "portfolio_dependency_graph",
            ],
            "filters":  ["entity_type", "relation_type"],
            "layout":   "knowledge",
        },
        {
            "path":     "/historical",
            "name":     "Historical Performance",
            "icon":     "clock",
            "widgets":  [
                "equity_curve",
                "recommendation_timeline",
                "performance_heatmap",
                "drift_panel",
            ],
            "filters":  ["date", "strategy"],
            "layout":   "historical",
        },
        {
            "path":     "/health",
            "name":     "Portfolio Health",
            "icon":     "activity",
            "widgets":  [
                "portfolio_grade", "confidence_gauge",
                "risk_alerts", "risk_radar",
                "drift_panel",
            ],
            "filters":  ["portfolio"],
            "layout":   "health",
        },
    ]


def filters() -> list[dict]:
    return [
        {"id": "portfolio",      "label": "Portfolio",      "type": "select",
          "source": "reports/portfolio.json.portfolios[].portfolio_display"},
        {"id": "sector",         "label": "Sector",         "type": "select",
          "source": "reports/recommendations.json.recommendations[].sector"},
        {"id": "industry",       "label": "Industry",       "type": "select",
          "source": "reports/recommendations.json.recommendations[].industry"},
        {"id": "market_regime",  "label": "Market Regime",  "type": "toggle_group",
          "options": ["Risk-On", "Neutral", "Risk-Off"]},
        {"id": "date",           "label": "Date range",     "type": "date_range"},
        {"id": "confidence",     "label": "Confidence",     "type": "range",
          "min": 0, "max": 100, "unit": "%"},
        {"id": "recommendation", "label": "Recommendation", "type": "multi_select",
          "options": ["Strong-Buy", "Buy", "Accumulate", "Hold",
                        "Reduce", "Sell", "Avoid", "Watchlist"]},
        {"id": "strategy",       "label": "Strategy",       "type": "select",
          "source": "reports/challenger_scoreboard.json.leaderboard[].strategy"},
        {"id": "entity_type",    "label": "Entity Type",    "type": "multi_select",
          "options": ["Company", "Industry", "Sector", "MarketTheme", "Strategy",
                        "Recommendation", "Portfolio", "Signal", "RiskFactor", "MarketRegime"]},
        {"id": "relation_type",  "label": "Relation Type",  "type": "multi_select",
          "options": ["COMPANY_TO_INDUSTRY", "INDUSTRY_TO_SECTOR",
                        "COMPANY_TO_PORTFOLIO", "PORTFOLIO_TO_STRATEGY",
                        "RECOMMENDATION_TO_COMPANY", "RECOMMENDATION_TO_OUTCOME",
                        "COMPANY_TO_COMPETITOR", "SECTOR_TO_REGIME",
                        "SIGNAL_TO_RECOMMENDATION", "COMPANY_TO_THEME"]},
    ]
