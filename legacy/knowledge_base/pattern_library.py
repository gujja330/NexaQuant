import os
import yaml
import pandas as pd
import numpy as np
import faiss
import pickle
from typing import Dict, Any, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PatternLibrary:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Intelligent pattern storage and retrieval system with similarity-based matching and reuse optimization.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.output_dir = "./knowledge_base/patterns/"
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initialize FAISS index for pattern similarity
        self.pattern_dim = self.config.get("pattern_library", {}).get("embedding_dim", 64)
        self.index = faiss.IndexFlatL2(self.pattern_dim)
        self.patterns = []
        self._load_existing_patterns()

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def _load_existing_patterns(self):
        """Load existing patterns from disk if available."""
        pattern_path = os.path.join(self.output_dir, "patterns.pkl")
        if os.path.exists(pattern_path):
            try:
                with open(pattern_path, 'rb') as f:
                    data = pickle.load(f)
                    self.patterns = data["patterns"]
                    if len(self.patterns) > 0:
                        embeddings = np.array([pat["embedding"] for pat in self.patterns]).astype('float32')
                        self.index.add(embeddings)
                logger.info(f"Loaded {len(self.patterns)} patterns from library")
            except Exception as e:
                logger.warning(f"Failed to load patterns: {e}")

    def store_pattern(self, pattern: Dict[str, Any]) -> None:
        """
        Store validated market patterns with metadata and embedding representation.
        """
        # Generate embedding if not present
        if "embedding" not in pattern:
            pattern["embedding"] = self._generate_pattern_embedding(pattern)
        
        # Add metadata
        pattern["timestamp"] = pd.Timestamp.now().isoformat()
        pattern["symbol"] = pattern.get("symbol", "UNKNOWN")
        pattern["pattern_type"] = pattern.get("pattern_type", "unknown")
        pattern["performance_score"] = pattern.get("performance_score", 0.0)
        
        self.patterns.append(pattern)
        embedding = np.array([pattern["embedding"]]).astype('float32')
        self.index.add(embedding)
        
        # Save to disk
        self._save_patterns()
        logger.info(f"Stored pattern: {pattern['pattern_type']} for {pattern['symbol']}")

    def _generate_pattern_embedding(self, pattern: Dict[str, Any]) -> np.ndarray:
        """Generate embedding from pattern features."""
        features = []
        
        # Extract numerical features
        for key in ["entry_price", "exit_price", "stop_loss", "take_profit", "duration", "performance_score"]:
            if key in pattern and isinstance(pattern[key], (int, float)):
                features.append(float(pattern[key]))
            else:
                features.append(0.0)
        
        # Extract categorical features as one-hot (simplified)
        pattern_types = ["bullish_engulfing", "bearish_engulfing", "head_shoulders", "double_top", "double_bottom", "fvg", "order_block"]
        if "pattern_type" in pattern:
            for pt in pattern_types:
                features.append(1.0 if pattern["pattern_type"] == pt else 0.0)
        else:
            features.extend([0.0] * len(pattern_types))
        
        # Pad or truncate to embedding dimension
        if len(features) < self.pattern_dim:
            features.extend([0.0] * (self.pattern_dim - len(features)))
        elif len(features) > self.pattern_dim:
            features = features[:self.pattern_dim]
        
        return np.array(features)

    def retrieve_similar_patterns(self, query_pattern: Dict[str, Any], k: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieve similar patterns using FAISS similarity search with performance filtering.
        """
        if len(self.patterns) == 0:
            return []
        
        # Generate query embedding
        query_embedding = self._generate_pattern_embedding(query_pattern)
        query_vector = np.array([query_embedding]).astype('float32')
        
        # Search FAISS index
        distances, indices = self.index.search(query_vector, k)
        
        # Return similar patterns with performance filtering
        similar_patterns = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.patterns):
                pat = self.patterns[idx].copy()
                pat["similarity_score"] = float(1.0 / (1.0 + distances[0][i]))
                similar_patterns.append(pat)
        
        # Sort by performance score
        similar_patterns.sort(key=lambda x: x.get("performance_score", 0), reverse=True)
        
        logger.info(f"Retrieved {len(similar_patterns)} similar patterns")
        return similar_patterns

    def validate_pattern_reuse(self, pattern: Dict[str, Any]) -> bool:
        """
        Validate pattern reuse eligibility based on performance and recency.
        """
        min_performance = self.config.get("pattern_library", {}).get("min_performance_score", 0.6)
        max_age_days = self.config.get("pattern_library", {}).get("max_pattern_age_days", 90)
        
        performance_ok = pattern.get("performance_score", 0) >= min_performance
        
        # Check recency
        pattern_time = pd.to_datetime(pattern.get("timestamp", pd.Timestamp.now()))
        age_days = (pd.Timestamp.now() - pattern_time).days
        recency_ok = age_days <= max_age_days
        
        is_valid = performance_ok and recency_ok
        if not is_valid:
            logger.warning(f"Pattern reuse validation failed: performance={performance_ok}, recency={recency_ok}")
        
        return is_valid

    def cluster_patterns(self) -> Dict[str, List[int]]:
        """
        Cluster patterns into groups using K-means for strategic grouping.
        """
        if len(self.patterns) < 2:
            return {"cluster_0": list(range(len(self.patterns)))}
        
        # Extract embeddings
        embeddings = np.array([pat["embedding"] for pat in self.patterns]).astype('float32')
        
        # Simple clustering using FAISS K-means
        n_clusters = min(5, len(self.patterns))
        kmeans = faiss.Kmeans(d=self.pattern_dim, k=n_clusters, niter=20, verbose=False)
        kmeans.train(embeddings)
        _, labels = kmeans.index.search(embeddings, 1)
        
        # Group patterns by cluster
        clusters = {}
        for i, label in enumerate(labels.flatten()):
            cluster_key = f"cluster_{label}"
            if cluster_key not in clusters:
                clusters[cluster_key] = []
            clusters[cluster_key].append(i)
        
        logger.info(f"Clustered patterns into {len(clusters)} groups")
        return clusters

    def generate_pattern_insights(self) -> Dict[str, Any]:
        """
        Generate strategic insights from pattern library for agent learning.
        """
        if len(self.patterns) == 0:
            return {"error": "No patterns available"}
        
        # Calculate statistics
        performances = [pat["performance_score"] for pat in self.patterns if "performance_score" in pat]
        pattern_types = [pat["pattern_type"] for pat in self.patterns if "pattern_type" in pat]
        
        insights = {
            "total_patterns": len(self.patterns),
            "avg_performance": float(np.mean(performances)) if performances else 0.0,
            "best_pattern_type": self._get_most_successful_pattern_type(pattern_types, performances),
            "pattern_diversity": len(set(pattern_types)) if pattern_types else 0,
            "recent_patterns": len([p for p in self.patterns if (pd.Timestamp.now() - pd.to_datetime(p["timestamp"])).days <= 30]),
            "timestamp": pd.Timestamp.now().isoformat()
        }
        
        logger.info("Generated pattern library insights")
        return insights

    def _get_most_successful_pattern_type(self, pattern_types: List[str], performances: List[float]) -> str:
        """Get the pattern type with highest average performance."""
        if not pattern_types or not performances:
            return "unknown"
        
        type_performance = {}
        for pt, perf in zip(pattern_types, performances):
            if pt not in type_performance:
                type_performance[pt] = []
            type_performance[pt].append(perf)
        
        best_type = max(type_performance.keys(), key=lambda x: np.mean(type_performance[x]))
        return best_type

    def _save_patterns(self):
        """Save patterns to disk."""
        pattern_path = os.path.join(self.output_dir, "patterns.pkl")
        try:
            with open(pattern_path, 'wb') as f:
                pickle.dump({"patterns": self.patterns}, f)
        except Exception as e:
            logger.error(f"Failed to save patterns: {e}")