import json
import pytest
from ams.core.sim_broker import SimBroker
from decimal import Decimal
from ams.core.order import Order, OrderDirection, OrderType

def test_internal_decimal_precision():
    broker = SimBroker(initial_cash=100000.0, slippage=0.001)
    
    # Internal representation should be Decimal
    assert isinstance(broker._cash, Decimal)
    
    # Order should handle precision properly and quantize
    broker.order_target_percent("AAPL", 0.5, 150.123)
    
    # Check that external exposes float
    assert isinstance(broker.cash, float)
    assert isinstance(broker.total_equity, float)
    
def test_external_api_returns_float():
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    broker.holdings = {"AAPL": 100}
    broker._last_prices = {"AAPL": Decimal("150.55")}
    broker.update_equity({"AAPL": 150.55})
    
    # Make sure we can serialize it
    try:
        data = json.dumps({"total_equity": broker.total_equity, "cash": broker.cash})
    except TypeError:
        pytest.fail("JSON serialization failed due to Decimal exposure")
    assert isinstance(broker.total_equity, float)

def test_scenario_1_suspended_stock_valuation():
    """
    Scenario 1: 停牌估值守恒 (集成验证)
    Given 持仓 100 张 A 债，昨日收盘价 100.55
    When 今日调用 update_equity 但 current_prices 缺少 A 债
    Then 对外暴露的 total_equity 统计出的 A 债部分应保持为 10055.00
    """
    broker = SimBroker(initial_cash=0.0, slippage=0.0)
    broker.holdings = {"A_BOND": 100}
    # yesterday price
    broker.update_equity({"A_BOND": 100.55})
    assert broker.total_equity == 10055.0
    
    # today price missing
    broker.update_equity({"B_BOND": 90.0}) # A_BOND is missing
    assert broker.total_equity == 10055.0 # Fallback to 100.55
    
def test_scenario_2_json_serialization():
    """
    Scenario 2: JSON 序列化兼容性
    Given 执行完一轮交易逻辑
    When 对 broker.total_equity 进行 json.dumps() 操作
    Then 系统应正常工作，不抛出 "Decimal is not JSON serializable" 异常。
    """
    broker = SimBroker(initial_cash=100000.0, slippage=0.001)
    broker.update_equity({"AAPL": 150.0})
    broker.order_target_percent("AAPL", 0.5, 150.0)
    
    try:
        data = json.dumps({"total_equity": broker.total_equity})
    except TypeError:
        pytest.fail("total_equity is not JSON serializable")

def test_broker_infinite_precision():
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    
    # Sequence of buys with decimals
    # Buy 1: 100 shares @ 103.456
    order1 = Order("TSLA", OrderDirection.BUY, 100, OrderType.MARKET, 0.0)
    broker.submit_order(order1)
    broker.match_orders({"TSLA": {"close": 103.456}})
    
    # Buy 2: 200 shares @ 105.123
    order2 = Order("TSLA", OrderDirection.BUY, 200, OrderType.MARKET, 0.0)
    broker.submit_order(order2)
    broker.match_orders({"TSLA": {"close": 105.123}})
    
    pos = broker.get_position("TSLA")
    
    # Manual calculation
    # (100 * 103.456 + 200 * 105.123) / 300 = 104.567333...
    manual_avg = (Decimal("100") * Decimal("103.456") + Decimal("200") * Decimal("105.123")) / Decimal("300")
    
    assert pos["avg_price"] == manual_avg
    assert isinstance(pos["avg_price"], Decimal)
    assert pos["quantity"] == 300

def test_broker_get_position_interface():
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    broker.order_target_percent("AAPL", 0.1, 150.0) # approx 10000 / 150 = 66 shares, rounded to 60 shares
    
    pos = broker.get_position("AAPL")
    assert "ticker" in pos
    assert "quantity" in pos
    assert "avg_price" in pos
    assert pos["ticker"] == "AAPL"
    assert isinstance(pos["avg_price"], Decimal)
    assert pos["avg_price"] == Decimal("150.0")
