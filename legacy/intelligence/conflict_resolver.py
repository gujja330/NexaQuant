# intelligence/conflict_resolver.py
import os
import yaml
import numpy as np
from typing import Dict, Any, List, Tuple
from scipy.optimize import minimize
import networkx as nx
from sklearn.cluster import KMeans
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConflictResolver:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbols = config["system"]["symbols"]

    def analyze_disagreement_patterns(self, agent_signals: List[float], agent_confidences: List[float]) -> Dict[str, Any]:
        features = np.column_stack([agent_signals, agent_confidences])
        n_clusters = min(2, len(agent_signals))
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        clusters = kmeans.fit_predict(features)
        
        cluster_stats = {}
        for i in range(n_clusters):
            cluster_mask = clusters == i
            cluster_signals = np.array(agent_signals)[cluster_mask]
            cluster_confs = np.array(agent_confidences)[cluster_mask]
            cluster_stats[f"cluster_{i}"] = {
                "mean_signal": float(np.mean(cluster_signals)),
                "mean_confidence": float(np.mean(cluster_confs)),
                "size": int(np.sum(cluster_mask))
            }
        
        disagreement_magnitude = np.std(agent_signals)
        is_severe = disagreement_magnitude > self.config.get("conflict_resolution", {}).get("severe_threshold", 1.0)
        
        return {
            "disagreement_magnitude": float(disagreement_magnitude),
            "is_severe": bool(is_severe),
            "clusters": cluster_stats,
            "cluster_assignments": clusters.tolist()
        }

    def simulate_adversarial_scenarios(self, base_signals: List[float], stress_level: float = 0.5) -> List[List[float]]:
        num_agents = len(base_signals)
        num_scenarios = self.config.get("conflict_resolution", {}).get("adversarial_scenarios", 10)
        scenarios = []
        for _ in range(num_scenarios):
            perturbed = [signal + np.random.normal(0, stress_level * 2.0) for signal in base_signals]
            scenarios.append(perturbed)
        logger.info(f"Generated {num_scenarios} adversarial scenarios at stress level {stress_level}")
        return scenarios

    def implement_game_theoretic_solutions(self, agent_signals: List[float], agent_confidences: List[float]) -> float:
        def cooperative_objective(weights):
            confidence_weighted = np.dot(weights, agent_confidences)
            diversity_penalty = np.var(weights)
            return -(confidence_weighted - 0.1 * diversity_penalty)

        constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
        bounds = [(0, 1) for _ in agent_signals]
        initial_weights = np.ones(len(agent_signals)) / len(agent_signals)
        result = minimize(cooperative_objective, initial_weights, method='SLSQP', bounds=bounds, constraints=constraints)
        optimal_weights = result.x if result.success else initial_weights
        resolved_signal = np.dot(optimal_weights, agent_signals)
        logger.info(f"Game-theoretic resolution: signal={resolved_signal:.4f}")
        return float(resolved_signal)

    def manage_agent_coalitions(self, agent_signals: List[float], agent_confidences: List[float]) -> Dict[str, Any]:
        pattern_analysis = self.analyze_disagreement_patterns(agent_signals, agent_confidences)
        if not pattern_analysis["is_severe"]:
            return {"coalitions": {"all": list(range(len(agent_signals)))}, "resolution_needed": False}
        clusters = pattern_analysis["cluster_assignments"]
        coalitions = {}
        for i, cluster_id in enumerate(clusters):
            coalition_key = f"coalition_{cluster_id}"
            if coalition_key not in coalitions:
                coalitions[coalition_key] = []
            coalitions[coalition_key].append(i)
        return {"coalitions": coalitions, "resolution_needed": True}

    def detect_herd_behavior(self, agent_signals: List[float], market_stress: float) -> bool:
        signal_std = np.std(agent_signals)
        stress_threshold = self.config.get("conflict_resolution", {}).get("herd_behavior_threshold", 0.5)
        is_herd = market_stress > stress_threshold and signal_std < 0.5
        if is_herd:
            logger.warning("Herd behavior detected - activating diversity protocols")
        return bool(is_herd)