import os
import yaml
import MetaTrader5 as mt5
from typing import Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BrokerAdapter:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Multi-broker abstraction with unified order interface and state-preserving failover.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.primary_broker = "mt5"
        self.secondary_broker = "alpaca" if self.config.get("alpaca", {}).get("enabled", False) else None
        self.mt5_config = self.config["system"]["mt5"]
        self.alpaca_config = self.config.get("alpaca", {})
        self.current_broker = self.primary_broker
        self.broker_health = {"mt5": True, "alpaca": self.alpaca_config.get("enabled", False)}

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def _connect_mt5(self) -> bool:
        """Connect to MT5 broker."""
        if not mt5.initialize():
            return False
        
        authorized = mt5.login(
            login=self.mt5_config["login"],
            password=self.mt5_config["password"],
            server=self.mt5_config["server"]
        )
        return authorized

    def _connect_alpaca(self):
        """Connect to Alpaca broker using config-driven credentials."""
        if not self.alpaca_config.get("enabled", False):
            raise ValueError("Alpaca is not enabled in config")
        
        api_key = self.alpaca_config.get("api_key")
        secret_key = self.alpaca_config.get("secret_key")
        
        if not api_key or not secret_key:
            raise ValueError("Alpaca API keys missing in config")
        
        paper = self.alpaca_config.get("paper", True)
        from alpaca.trading.client import TradingClient
        return TradingClient(api_key, secret_key, paper=paper)

    def execute_order(self, symbol: str, side: str, quantity: float, stop_loss: float = None, take_profit: float = None) -> Dict[str, Any]:
        """Execute order with automatic failover between brokers."""
        # Try primary broker first
        if self.current_broker == "mt5" and self.broker_health["mt5"]:
            try:
                result = self._execute_mt5_order(symbol, side, quantity, stop_loss, take_profit)
                if result["status"] == "success":
                    return result
                else:
                    logger.warning("MT5 execution failed, switching to Alpaca")
                    self.broker_health["mt5"] = False
            except Exception as e:
                logger.error(f"MT5 execution error: {e}")
                self.broker_health["mt5"] = False
        
        # Fallback to secondary broker (only if enabled)
        if self.secondary_broker == "alpaca" and self.broker_health["alpaca"]:
            try:
                result = self._execute_alpaca_order(symbol, side, quantity)
                if result["status"] == "success":
                    self.current_broker = "alpaca"
                    return result
                else:
                    logger.error("Alpaca execution also failed")
                    self.broker_health["alpaca"] = False
            except Exception as e:
                logger.error(f"Alpaca execution error: {e}")
                self.broker_health["alpaca"] = False
        
        return {"status": "failed", "error": "All brokers unavailable"}

    def _execute_mt5_order(self, symbol: str, side: str, quantity: float, stop_loss: float = None, take_profit: float = None) -> Dict[str, Any]:
        """Execute order via MT5."""
        if not self._connect_mt5():
            return {"status": "failed", "error": "MT5 connection failed"}
        
        # Map side to MT5 order type
        order_type = mt5.ORDER_TYPE_BUY if side.lower() == "buy" else mt5.ORDER_TYPE_SELL
        
        # Get symbol info
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None or not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                mt5.shutdown()
                return {"status": "failed", "error": f"Symbol {symbol} not available"}
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
        
        # Create order request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": quantity,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "MARL Auto Trade",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        if stop_loss:
            request["sl"] = stop_loss
        if take_profit:
            request["tp"] = take_profit
        
        # Send order
        result = mt5.order_send(request)
        mt5.shutdown()
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"status": "failed", "error": result.comment}
        
        return {
            "status": "success",
            "broker": "mt5",
            "ticket": result.order,
            "price": price,
            "quantity": quantity
        }

    def _execute_alpaca_order(self, symbol: str, side: str, quantity: float) -> Dict[str, Any]:
        """Execute order via Alpaca."""
        try:
            client = self._connect_alpaca()
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce
            
            side_enum = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=side_enum,
                time_in_force=TimeInForce.GTC
            )
            
            order = client.submit_order(order_data=order_data)
            return {
                "status": "success",
                "broker": "alpaca",
                "order_id": order.id,
                "client_order_id": order.client_order_id,
                "quantity": quantity
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def get_account_info(self) -> Dict[str, Any]:
        """Get account information from current broker."""
        if self.current_broker == "mt5" and self.broker_health["mt5"]:
            try:
                if self._connect_mt5():
                    account = mt5.account_info()
                    mt5.shutdown()
                    if account:
                        return {
                            "broker": "mt5",
                            "balance": account.balance,
                            "equity": account.equity,
                            "currency": account.currency,
                            "leverage": account.leverage
                        }
            except Exception as e:
                logger.error(f"MT5 account info error: {e}")
                self.broker_health["mt5"] = False
        
        if self.secondary_broker == "alpaca" and self.broker_health["alpaca"]:
            try:
                client = self._connect_alpaca()
                account = client.get_account()
                return {
                    "broker": "alpaca",
                    "balance": float(account.cash),
                    "equity": float(account.equity),
                    "currency": "USD",
                    "leverage": 1
                }
            except Exception as e:
                logger.error(f"Alpaca account info error: {e}")
                self.broker_health["alpaca"] = False
        
        return {"status": "failed", "error": "No broker available"}

    def reconcile_positions(self) -> Dict[str, Any]:
        """Cross-broker position reconciliation."""
        positions = {}
        
        # Get MT5 positions
        if self.broker_health["mt5"]:
            try:
                if self._connect_mt5():
                    mt5_positions = mt5.positions_get()
                    mt5.shutdown()
                    for pos in mt5_positions:
                        symbol = pos.symbol
                        if symbol not in positions:
                            positions[symbol] = {"mt5": 0, "alpaca": 0}
                        positions[symbol]["mt5"] = pos.volume
            except Exception as e:
                logger.error(f"MT5 position reconciliation error: {e}")
        
        # Get Alpaca positions (only if enabled)
        if self.secondary_broker == "alpaca" and self.broker_health["alpaca"]:
            try:
                client = self._connect_alpaca()
                alpaca_positions = client.get_all_positions()
                for pos in alpaca_positions:
                    symbol = pos.symbol
                    if symbol not in positions:
                        positions[symbol] = {"mt5": 0, "alpaca": 0}
                    positions[symbol]["alpaca"] = float(pos.qty)
            except Exception as e:
                logger.error(f"Alpaca position reconciliation error: {e}")
        
        return positions