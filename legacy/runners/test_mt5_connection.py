# runners/test_mt5_connection.py
import sys
import os
import yaml
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("❌ MetaTrader5 not installed. Install with: pip install MetaTrader5")
    sys.exit(1)

def test_mt5_login():
    print("📡 Testing MT5 Connection...")
    
    # Load config dynamically
    config_path = "config/base_config.yaml"
    if not os.path.exists(config_path):
        print(f"❌ Config not found: {config_path}")
        return False

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    mt5_config = config.get("system", {}).get("mt5", {})
    server = mt5_config.get("server")
    login = mt5_config.get("login")
    password = mt5_config.get("password")
    timeout = mt5_config.get("timeout", 30000)

    if not all([server, login, password]):
        print("❌ MT5 config missing in base_config.yaml")
        return False

    # Initialize MT5
    if not mt5.initialize():
        print(f"❌ MT5 failed to initialize. Error: {mt5.last_error()}")
        return False

    # Login
    authorized = mt5.login(
        login=int(login),
        password=str(password),
        server=str(server),
        timeout=timeout
    )

    if authorized:
        account_info = mt5.account_info()
        print(f"✅ MT5 Login SUCCESS")
        print(f"   Account: {account_info.login}")
        print(f"   Server: {account_info.server}")
        print(f"   Balance: ${account_info.balance:,.2f}")
        mt5.shutdown()
        return True
    else:
        print(f"❌ MT5 Login FAILED. Error: {mt5.last_error()}")
        mt5.shutdown()
        return False

if __name__ == "__main__":
    success = test_mt5_connection()
    if success:
        print("\n🎯 MT5 connection verified. You may proceed to data collection.")
    else:
        print("\n⚠️  Fix MT5 credentials or network before continuing.")