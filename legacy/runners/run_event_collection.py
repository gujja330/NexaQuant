# runners/run_event_collection.py
import os
import sys
import yaml
from pathlib import Path
from datetime import datetime  # 🔹 ADDED MISSING IMPORT

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# AI-Driven Imports (Per new_rules.md)
from data_engine.event_injector import EventInjector
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("🌍 Starting Economic Event Collection")
    print("✅ Loading configuration...")
    
    config_path = "config/base_config.yaml"
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"❌ Config file not found: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    event_injector = EventInjector(config)
    
    if not event_injector.enabled:
        print("⚠️ Event injection disabled in config. Skipping collection.")
        return
    
    print(f"📊 Event collection parameters:")
    print(f"   Sources: {event_injector.sources}")
    print(f"   Minimum impact: {event_injector.min_impact}")
    print(f"   Update frequency: {config.get('event_injection', {}).get('update_frequency_hours', 6)} hours")
    
    try:
        events_df = event_injector.collect_economic_events(days_ahead=7)
        
        # 🔹 SAFETY CHECK: Handle empty DataFrame
        if events_df.empty or 'impact' not in events_df.columns:
            print("⚠️ No valid events collected (missing 'impact' column)")
            summary = {
                "collection_time": datetime.now().isoformat(),
                "total_events": 0,
                "high_impact_events": 0,
                "medium_impact_events": 0,
                "low_impact_events": 0,
                "sources_used": event_injector.sources,
                "status": "NO_VALID_EVENTS"
            }
        else:
            print(f"✅ Successfully collected {len(events_df)} economic events")
            print(f"   High impact: {(events_df['impact'] == 'high').sum()}")
            print(f"   Medium impact: {(events_df['impact'] == 'medium').sum()}")
            print(f"   Low impact: {(events_df['impact'] == 'low').sum()}")
            
            summary = {
                "collection_time": str(events_df['timestamp'].max()) if not events_df.empty else datetime.now().isoformat(),
                "total_events": len(events_df),
                "high_impact_events": int((events_df['impact'] == 'high').sum()),
                "medium_impact_events": int((events_df['impact'] == 'medium').sum()),
                "low_impact_events": int((events_df['impact'] == 'low').sum()),
                "sources_used": event_injector.sources,
                "status": "SUCCESS"
            }
        
        # Save summary
        output_dir = "./runners/output/event_collection/"
        os.makedirs(output_dir, exist_ok=True)
        
        import json
        summary_path = os.path.join(output_dir, f"event_collection_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"📄 Event collection summary saved: {summary_path}")
        
    except Exception as e:
        logger.error(f"❌ Event collection failed: {e}")
        error_log_path = os.path.join("logs", "config_errors.log")
        os.makedirs(os.path.dirname(error_log_path), exist_ok=True)
        with open(error_log_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [run_event_collection] [Critical] Event collection failed: {str(e)} [Unresolved]\n")
        raise

    print("📂 Event data stored in: ./data_engine/events/")

if __name__ == "__main__":
    print("🎯 Economic Event Collection Starting...")
    print("🔒 Zero-investment event collection from free sources")
    print("📊 Events will be injected into synthetic data for realism")
    main()
    print("✅ Event collection completed successfully")