# intelligence/nlp_event_processor.py
import numpy as np
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class NLPEventProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.event_sentiment_map = {
            "NFP": {"positive": ["beat", "increase", "strong"], "negative": ["miss", "decrease", "weak"]},
            "CPI": {"positive": ["higher", "increase"], "negative": ["lower", "decrease"]},
            "FOMC": {"positive": ["hawkish", "rate hike"], "negative": ["dovish", "rate cut"]}
        }

    def process_event(self, event_type: str, headline: str) -> float:
        headline_lower = headline.lower()
        mapping = self.event_sentiment_map.get(event_type, {})
        pos_words = mapping.get("positive", [])
        neg_words = mapping.get("negative", [])

        pos_score = sum(1 for word in pos_words if word in headline_lower)
        neg_score = sum(1 for word in neg_words if word in headline_lower)

        if pos_score > neg_score:
            return 0.8
        elif neg_score > pos_score:
            return -0.8
        return 0.0

    def add_event_features(self, df: "pd.DataFrame", events: List[Dict]) -> "pd.DataFrame":
        if not events:
            df['event_sentiment'] = 0.0
            df['event_impact'] = 0.0
            return df

        df = df.copy()
        df['event_sentiment'] = 0.0
        df['event_impact'] = 0.0

        for event in events:
            if 'timestamp' not in event or 'type' not in event:
                continue
            try:
                event_time = pd.to_datetime(event['timestamp'])
                mask = (df.index >= event_time) & (df.index < event_time + pd.Timedelta(hours=1))
                if mask.any():
                    sentiment = self.process_event(event['type'], event.get('headline', ''))
                    impact = event.get('impact', 0.5)
                    df.loc[mask, 'event_sentiment'] = sentiment
                    df.loc[mask, 'event_impact'] = impact
            except Exception as e:
                logger.warning(f"Failed to process event: {e}")
        return df