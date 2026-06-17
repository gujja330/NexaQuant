import os
import yaml
import pandas as pd
import numpy as np
from typing import Dict, Any
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, Input, Output
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Dashboard:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Dynamic visualization system with intelligent information prioritization and adaptive layout.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.output_dir = "./interface/dashboards/"
        os.makedirs(self.output_dir, exist_ok=True)
        self.app = None

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def create_performance_dashboard(self, performance_data: pd.DataFrame, agent_data: Dict[str, Any]) -> str:
        """
        Create comprehensive performance dashboard with agent health and risk metrics.
        """
        if performance_data.empty:
            logger.warning("No performance data for dashboard")
            return ""
        
        # Create subplot
        fig = make_subplots(
            rows=3, cols=2,
            subplot_titles=(
                "Equity Curve", "Win Rate Over Time",
                "Sharpe Ratio", "Agent Confidence",
                "Drawdown", "Risk Exposure"
            ),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]]
        )
        
        # Equity curve
        if 'equity' in performance_data.columns:
            fig.add_trace(
                go.Scatter(x=performance_data.index, y=performance_data['equity'], 
                          mode='lines', name='Equity'),
                row=1, col=1
            )
        
        # Win rate over time
        if 'win_rate' in performance_data.columns:
            fig.add_trace(
                go.Scatter(x=performance_data.index, y=performance_data['win_rate'], 
                          mode='lines', name='Win Rate'),
                row=1, col=2
            )
        
        # Sharpe ratio
        if 'sharpe_ratio' in performance_data.columns:
            fig.add_trace(
                go.Scatter(x=performance_data.index, y=performance_data['sharpe_ratio'], 
                          mode='lines', name='Sharpe Ratio'),
                row=2, col=1
            )
        
        # Agent confidence (simplified)
        agent_confidences = []
        agent_names = []
        for agent_name, agent_info in agent_data.items():
            if isinstance(agent_info, dict) and 'confidence' in agent_info:
                agent_confidences.append(agent_info['confidence'])
                agent_names.append(agent_name)
        
        if agent_confidences:
            fig.add_trace(
                go.Bar(x=agent_names, y=agent_confidences, name='Agent Confidence'),
                row=2, col=2
            )
        
        # Drawdown
        if 'drawdown' in performance_data.columns:
            fig.add_trace(
                go.Scatter(x=performance_data.index, y=performance_data['drawdown'], 
                          mode='lines', name='Drawdown', line=dict(color='red')),
                row=3, col=1
            )
        
        # Risk exposure (simplified)
        risk_exposure = [0.5] * len(self.symbols)  # Placeholder
        fig.add_trace(
            go.Bar(x=self.symbols, y=risk_exposure, name='Risk Exposure'),
            row=3, col=2
        )
        
        # Update layout
        fig.update_layout(
            title="Multi-Agent RL Trading System - Performance Dashboard",
            height=1000,
            showlegend=True
        )
        
        # Save dashboard
        dashboard_path = os.path.join(self.output_dir, "performance_dashboard.html")
        fig.write_html(dashboard_path)
        logger.info(f"Performance dashboard saved: {dashboard_path}")
        return dashboard_path

    def create_interactive_dashboard(self) -> dash.Dash:
        """
        Create interactive Dash application with real-time updates and drill-down capabilities.
        """
        self.app = dash.Dash(__name__)
        
        self.app.layout = html.Div([
            html.H1("MARL Trading System Dashboard", style={'textAlign': 'center'}),
            html.Div([
                html.Div([
                    html.H3("System Health"),
                    dcc.Graph(id='health-graph')
                ], className="six columns"),
                html.Div([
                    html.H3("Performance Metrics"),
                    dcc.Graph(id='performance-graph')
                ], className="six columns")
            ], className="row"),
            html.Div([
                html.Div([
                    html.H3("Agent Status"),
                    dcc.Graph(id='agent-graph')
                ], className="six columns"),
                html.Div([
                    html.H3("Risk Metrics"),
                    dcc.Graph(id='risk-graph')
                ], className="six columns")
            ], className="row"),
            dcc.Interval(
                id='interval-component',
                interval=30*1000,  # 30 seconds
                n_intervals=0
            )
        ])
        
        @self.app.callback(
            [Output('health-graph', 'figure'),
             Output('performance-graph', 'figure'),
             Output('agent-graph', 'figure'),
             Output('risk-graph', 'figure')],
            [Input('interval-component', 'n_intervals')]
        )
        def update_dashboard(n):
            # This would typically fetch real-time data
            # For now, return placeholder figures
            health_fig = go.Figure()
            performance_fig = go.Figure()
            agent_fig = go.Figure()
            risk_fig = go.Figure()
            
            return health_fig, performance_fig, agent_fig, risk_fig
        
        logger.info("Interactive dashboard created")
        return self.app

    def generate_adaptive_layout(self, user_preferences: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Generate context-aware dashboard layout based on user preferences and system state.
        """
        layout_config = {
            "layout_type": "comprehensive",
            "priority_metrics": ["equity", "sharpe_ratio", "win_rate", "drawdown"],
            "refresh_interval": 30,  # seconds
            "alert_thresholds": {
                "max_drawdown": 0.20,
                "min_sharpe": 0.8,
                "min_win_rate": 0.45
            },
            "symbols": self.symbols,
            "agents": ["trend", "sentiment", "risk", "execution", "volatility"]
        }
        
        # Apply user preferences if provided
        if user_preferences:
            layout_config.update(user_preferences)
        
        # Save layout configuration
        layout_path = os.path.join(self.output_dir, "dashboard_layout.json")
        import json
        with open(layout_path, 'w') as f:
            json.dump(layout_config, f, indent=2)
        
        logger.info(f"Adaptive layout generated: {layout_path}")
        return layout_config

    def prioritize_information(self, system_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intelligent information ranking based on system health and performance anomalies.
        """
        priorities = {
            "critical_alerts": [],
            "high_priority": [],
            "medium_priority": [],
            "low_priority": []
        }
        
        # Check for critical issues
        if system_state.get("drawdown", 0) > 0.25:
            priorities["critical_alerts"].append("MAX_DRAWDOWN_EXCEEDED")
        
        if system_state.get("sharpe_ratio", 1.0) < 0.5:
            priorities["critical_alerts"].append("SHARPE_RATIO_CRITICAL")
        
        if system_state.get("win_rate", 0.5) < 0.4:
            priorities["high_priority"].append("WIN_RATE_DEGRADATION")
        
        if system_state.get("agent_health", {}).get("trend", 1.0) < 0.6:
            priorities["high_priority"].append("TREND_AGENT_DEGRADED")
        
        logger.info(f"Information prioritization completed: {len(priorities['critical_alerts'])} critical alerts")
        return priorities

    def save_dashboard_state(self, dashboard_state: Dict[str, Any]) -> str:
        """
        Save current dashboard state for session persistence and audit trails.
        """
        state = {
            "dashboard_id": f"DASH_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": pd.Timestamp.now().isoformat(),
            "state": dashboard_state,
            "symbols": self.symbols
        }
        
        state_path = os.path.join(self.output_dir, f"dashboard_state_{state['dashboard_id']}.json")
        import json
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)
        
        logger.info(f"Dashboard state saved: {state_path}")
        return state_path