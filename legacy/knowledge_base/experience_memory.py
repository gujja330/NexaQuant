import os
import yaml
import pandas as pd
import numpy as np
import faiss
import pickle
from typing import Dict, Any, List, Tuple
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ExperienceMemory:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Persistent replay memory with intelligent experience replay and similarity-based retrieval using FAISS.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.output_dir = "./knowledge_base/experiences/"
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initialize FAISS index
        self.embedding_dim = self.config.get("experience_memory", {}).get("embedding_dim", 128)
        self.index = faiss.IndexFlatL2(self.embedding_dim)
        self.experiences = []
        self._load_existing_memory()

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def _load_existing_memory(self):
        """Load existing memory from disk if available."""
        memory_path = os.path.join(self.output_dir, "memory.pkl")
        if os.path.exists(memory_path):
            try:
                with open(memory_path, 'rb') as f:
                    data = pickle.load(f)
                    self.experiences = data["experiences"]
                    if len(self.experiences) > 0:
                        embeddings = np.array([exp["embedding"] for exp in self.experiences]).astype('float32')
                        self.index.add(embeddings)
                logger.info(f"Loaded {len(self.experiences)} experiences from memory")
            except Exception as e:
                logger.warning(f"Failed to load memory: {e}")

    def store_experiences(self, experiences: List[Dict[str, Any]]) -> None:
        """
        Structured experience storage with metadata and FAISS indexing.
        """
        for exp in experiences:
            # Generate embedding if not present
            if "embedding" not in exp:
                exp["embedding"] = self._generate_embedding(exp)
            
            # Add metadata
            exp["timestamp"] = pd.Timestamp.now().isoformat()
            exp["symbol"] = exp.get("symbol", "UNKNOWN")
            
            self.experiences.append(exp)
            embedding = np.array([exp["embedding"]]).astype('float32')
            self.index.add(embedding)
        
        # Save to disk
        self._save_memory()
        logger.info(f"Stored {len(experiences)} new experiences")

    def _generate_embedding(self, experience: Dict[str, Any]) -> np.ndarray:
        """Generate embedding using simple feature vector (in production, use neural encoder)."""
        # Create feature vector from experience
        features = []
        for key in ["state", "action", "reward", "next_state"]:
            if key in experience:
                if isinstance(experience[key], (int, float)):
                    features.append(float(experience[key]))
                elif isinstance(experience[key], (list, np.ndarray)):
                    features.extend([float(x) for x in experience[key][:10]])  # Limit to 10 features
                else:
                    features.append(0.0)
            else:
                features.append(0.0)
        
        # Pad or truncate to embedding dimension
        if len(features) < self.embedding_dim:
            features.extend([0.0] * (self.embedding_dim - len(features)))
        elif len(features) > self.embedding_dim:
            features = features[:self.embedding_dim]
        
        return np.array(features)

    def retrieve_similar_patterns(self, query_experience: Dict[str, Any], k: int = 5) -> List[Dict[str, Any]]:
        """
        Similarity-based pattern matching and retrieval using FAISS.
        """
        if len(self.experiences) == 0:
            return []
        
        # Generate query embedding
        query_embedding = self._generate_embedding(query_experience)
        query_vector = np.array([query_embedding]).astype('float32')
        
        # Search FAISS index
        distances, indices = self.index.search(query_vector, k)
        
        # Return similar experiences
        similar_experiences = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.experiences):
                exp = self.experiences[idx].copy()
                exp["similarity_score"] = float(1.0 / (1.0 + distances[0][i]))  # Convert distance to similarity
                similar_experiences.append(exp)
        
        logger.info(f"Retrieved {len(similar_experiences)} similar experiences")
        return similar_experiences

    def prioritized_replay(self, batch_size: int = 32) -> List[Dict[str, Any]]:
        """
        Importance-weighted experience sampling based on TD error or recency.
        """
        if len(self.experiences) == 0:
            return []
        
        # Simple prioritization: recent experiences have higher priority
        recent_count = min(batch_size * 2, len(self.experiences))
        recent_experiences = self.experiences[-recent_count:]
        
        # Sample from recent experiences
        sampled_indices = np.random.choice(len(recent_experiences), size=min(batch_size, len(recent_experiences)), replace=False)
        sampled_experiences = [recent_experiences[i] for i in sampled_indices]
        
        logger.info(f"Sampled {len(sampled_experiences)} experiences for replay")
        return sampled_experiences

    def knowledge_distillation(self, symbol: str = None) -> Dict[str, Any]:
        """
        Compact knowledge representation for fast access and transfer learning.
        """
        # Filter experiences by symbol if specified
        relevant_experiences = self.experiences
        if symbol:
            relevant_experiences = [exp for exp in self.experiences if exp.get("symbol") == symbol]
        
        if len(relevant_experiences) == 0:
            return {"error": "No experiences found"}
        
        # Calculate statistics
        rewards = [exp["reward"] for exp in relevant_experiences if "reward" in exp]
        actions = [exp["action"] for exp in relevant_experiences if "action" in exp]
        
        distilled_knowledge = {
            "symbol": symbol,
            "total_experiences": len(relevant_experiences),
            "avg_reward": float(np.mean(rewards)) if rewards else 0.0,
            "reward_std": float(np.std(rewards)) if len(rewards) > 1 else 0.0,
            "action_distribution": self._calculate_action_distribution(actions),
            "win_rate": float(len([r for r in rewards if r > 0]) / len(rewards)) if rewards else 0.0,
            "timestamp": pd.Timestamp.now().isoformat()
        }
        
        logger.info(f"Distilled knowledge for {symbol or 'all symbols'}")
        return distilled_knowledge

    def _calculate_action_distribution(self, actions: List[int]) -> Dict[str, float]:
        """Calculate action distribution from experience."""
        if not actions:
            return {}
        
        unique_actions, counts = np.unique(actions, return_counts=True)
        total = len(actions)
        distribution = {}
        for action, count in zip(unique_actions, counts):
            distribution[f"action_{action}"] = float(count / total)
        
        return distribution

    def _save_memory(self):
        """Save memory to disk."""
        memory_path = os.path.join(self.output_dir, "memory.pkl")
        try:
            with open(memory_path, 'wb') as f:
                pickle.dump({"experiences": self.experiences}, f)
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")