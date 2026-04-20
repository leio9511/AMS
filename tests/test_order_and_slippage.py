import pytest
from ams.core.order import (
    Order, OrderDirection, OrderType, OrderStatus,
    STATUS_PENDING, STATUS_FILLED, STATUS_CANCELED, STATUS_REJECTED
)
from ams.core.slippage import ExtremeRiskSlippageModel

def test_order_status_constants():
    assert STATUS_PENDING == "PENDING"
    assert STATUS_FILLED == "FILLED"
    assert STATUS_CANCELED == "CANCELED"
    assert STATUS_REJECTED == "REJECTED"

def test_order_initialization():
    order = Order(
        ticker="123456",
        direction=OrderDirection.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=110.0
    )
    assert order.status == OrderStatus.PENDING

def test_extreme_risk_slippage_model_sell():
    order = Order(
        ticker="123456",
        direction=OrderDirection.SELL,
        quantity=100,
        order_type=OrderType.MARKET,
        limit_price=0.0
    )
    slippage_model = ExtremeRiskSlippageModel(penalty_rate=0.5)
    result = slippage_model.calculate_slippage(order, base_price=100.0)
    assert result == 50.0
