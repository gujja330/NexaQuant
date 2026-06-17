# intelligence/multi_agent_brain.py
import os
import numpy as np
from typing import Dict, Any, List, Tuple
import logging

logger = logging.getLogger(__name__)

class MultiAgentBrain:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.xgb_orchestrator = None
        self.rl_position_sizer = None
        self.conflict_resolver = None
        self._components_initialized = False

    def _lazy_init_components(self):
        if self._components_initialized:
            return

        # XGBoost (should load fine)
        from intelligence.xgboost_orchestrator import XGBoostOrchestrator
        self.xgb_orchestrator = XGBoostOrchestrator(self.config)
        logger.info("✅ XGBoost orchestrator loaded")

        # Conflict resolver (pure scipy — no issue)
        from intelligence.conflict_resolver import ConflictResolver
        self.conflict_resolver = ConflictResolver(self.config)

        # RL Position Sizer — import HERE, not at top
        try:
            from intelligence.rl_position_sizer import RLPositionSizer
            self.rl_position_sizer = RLPositionSizer(self.config)
            logger.info("✅ RL position sizer loaded")
        except Exception as e:
            logger.error("❌ RL position sizer failed to load", exc_info=True)
            raise  # Re-raise to comply with your "no fallback" rule

        self._components_initialized = True

    def act(self, state: np.ndarray, regime: int, feature_names: List[str], **kwargs) -> Tuple[int, Dict[str, Any]]:
        self._lazy_init_components()

        # Get action from XGBoost
        action, meta = self.xgb_orchestrator.predict_action(state, feature_names)

        # Resolve conflicts
        agent_signals = [action, action * 0.9, action * 1.1]
        agent_confidences = [0.8, 0.7, 0.75]
        resolved_action = self.conflict_resolver.implement_game_theoretic_solutions(agent_signals, agent_confidences)
        final_action = np.sign(resolved_action) if abs(resolved_action) > 0.3 else 0

        # Get position size from RL
        position_ratio = self.rl_position_sizer.get_position_ratio(state)

        meta.update({
            "resolved_action": float(resolved_action),
            "position_ratio": float(position_ratio),
            "regime": int(regime),
            "feature_count": len(feature_names),
            "model_used": "xgboost+conflict+rl"
        })
        return int(final_action), meta