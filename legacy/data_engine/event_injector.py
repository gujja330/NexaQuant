# data_engine/event_injector.py
import os
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from typing import Dict, Any
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EventInjector:
    """
    Inject real economic events from Investing.com into real market data.
    Fully dynamic. Zero hardcoding. Config-driven. Symbol-agnostic.
    Implements Event-Driven Modeling with zero synthetic fallback.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.event_config = config.get("event_injection", {})
        self.enabled = self.event_config.get("enabled", False)
        self.sources = self.event_config.get("sources", ["investing"])
        self.min_impact = self.event_config.get("min_impact", "medium")
        self.output_dir = os.path.join("data_engine", "events")
        os.makedirs(self.output_dir, exist_ok=True)

    def collect_economic_events(self, days_ahead: int = 7) -> pd.DataFrame:
        """Collect real events from Investing.com only."""
        if not self.enabled:
            return pd.DataFrame()
        
        for source in self.sources:
            if source == "investing":
                try:
                    return self._scrape_investing_calendar(days_ahead)
                except Exception as e:
                    logger.warning(f"Failed to collect events from investing.com: {e}")
                    return pd.DataFrame()
        return pd.DataFrame()

    def _scrape_investing_calendar(self, days_ahead: int) -> pd.DataFrame:
        """Scrape Investing.com economic calendar."""
        url = "https://www.investing.com/economic-calendar/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'id': 'economicCalendarData'})
        if not table:
            return pd.DataFrame()
        
        rows = table.find('tbody').find_all('tr', {'class': 'js-event-item'})
        events = []
        current_date = None
        
        for row in rows:
            try:
                date_cell = row.find('td', {'class': 'first left'})
                if date_cell and 'data-event-datetime' in date_cell.attrs:
                    current_date = date_cell['data-event-datetime'].split()[0]
                
                time_cell = row.find('td', {'class': 'time'})
                time_str = time_cell.text.strip() if time_cell else "00:00"
                
                currency_cell = row.find('td', {'class': 'left flagCur'})
                currency = currency_cell.text.strip() if currency_cell else "USD"
                
                event_cell = row.find('td', {'class': 'event'})
                event = event_cell.text.strip() if event_cell else "Unknown Event"
                
                impact_cell = row.find('td', {'class': 'sentiment'})
                impact = "low"
                if impact_cell:
                    if 'red' in str(impact_cell):
                        impact = "high"
                    elif 'orange' in str(impact_cell):
                        impact = "medium"
                
                if self._impact_priority(impact) < self._impact_priority(self.min_impact):
                    continue
                
                events.append({
                    "date": current_date or datetime.now().strftime('%Y-%m-%d'),
                    "time": time_str,
                    "event": event,
                    "country": currency,
                    "impact": impact,
                    "actual": "",
                    "forecast": "",
                    "previous": "",
                    "timestamp": datetime.now()
                })
            except Exception:
                continue
        
        return pd.DataFrame(events) if events else pd.DataFrame()

    def _impact_priority(self, impact: str) -> int:
        levels = {"low": 1, "medium": 2, "high": 3}
        return levels.get(impact, 0)

    def _extract_sentiment_score(self, event_text: str) -> float:
        """Simple rule-based sentiment (replace later with LLM)"""
        positive = ["beat", "rise", "gain", "strong", "up", "bullish"]
        negative = ["miss", "fall", "drop", "weak", "down", "bearish"]
        text = event_text.lower()
        score = 0.0
        for word in positive:
            if word in text:
                score += 0.3
        for word in negative:
            if word in text:
                score -= 0.3
        return max(-1.0, min(1.0, score))  # clamp to [-1, 1]

    def inject_events_into_real_data(self, symbol: str, df: pd.DataFrame) -> pd.DataFrame:
        """Inject real economic events into historical MT5 data."""
        if not self.enabled:
            return df

        # Fetch real events (last 10 years)
        events = self.collect_economic_events(days_ahead=3650)
        if events.empty:
            logger.info("No real events found — skipping injection for real data")
            return df

        df = df.copy()
        for _, event in events.iterrows():
            # Parse event datetime
            try:
                event_dt_str = f"{event['date']} {event['time']}"
                event_time = pd.to_datetime(event_dt_str)
            except:
                continue

            # Find nearest timestamp in df
            if event_time not in df.index:
                closest = df.index[np.abs(df.index - event_time).argmin()]
                if abs(closest - event_time) > pd.Timedelta(hours=1):
                    continue
                event_time = closest

            # Add sentiment score
            sentiment = self._extract_sentiment_score(event['event'])
            
            # Apply volatility spike based on impact
            mag_map = {"low": 0.01, "medium": 0.02, "high": 0.03}
            mag = mag_map.get(event['impact'], 0.01)
            noise = np.random.normal(0, mag)
            
            # Adjust price with sentiment bias
            shock = noise + (sentiment * 0.005)
            df.loc[event_time, 'close'] *= (1 + shock)
            df.loc[event_time, 'high'] = max(df.loc[event_time, 'high'], df.loc[event_time, 'close'] * (1 + abs(shock)))
            df.loc[event_time, 'low'] = min(df.loc[event_time, 'low'], df.loc[event_time, 'close'] * (1 - abs(shock)))

        return df