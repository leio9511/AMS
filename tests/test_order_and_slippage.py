import pytest
from ams.core.order import Order, Direction, OrderType, OrderStatus
from ams.core.slippage import ExtremeRiskSlippageModel

def test_order_creation():
    order = Order(
        ticker="AAPL",
        direction=Direction.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=150.0
    )
    assert order.ticker == "AAPL"
    assert order.direction == Direction.BUY
    assert order.quantity == 100
    assert order.order_type == OrderType.LIMIT
    assert order.limit_price == 150.0
    assert order.status == OrderStatus.PENDING

def test_extreme_risk_slippage_model():
    order = Order(
        ticker="AAPL",
        direction=Direction.SELL,
        quantity=100,
        order_type=OrderType.MARKET
    )
    bar_data = {"close": 100.0, "high": 105.0, "low": 95.0, "open": 98.0}
    
    # 50% penalty
    slippage_model = ExtremeRiskSlippageModel(deduction_percentage=0.50)
    execution_price = slippage_model.calculate_execution_price(order, bar_data)
    
    assert execution_price == 50.0
