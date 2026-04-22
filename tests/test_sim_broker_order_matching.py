import pytest
from ams.core.sim_broker import SimBroker
from ams.core.order import Order, OrderDirection, OrderType, OrderStatus
from ams.core.slippage import ExtremeRiskSlippageModel

def test_limit_order_matching_in_broker():
    broker = SimBroker(initial_cash=10000.0, slippage=0.0)
    # Mock holdings
    broker.holdings["AAPL"] = 100
    
    # Create Limit Sell order at 110.0
    order = Order(
        ticker="AAPL",
        direction=OrderDirection.SELL,
        quantity=50,
        order_type=OrderType.LIMIT,
        limit_price=110.0
    )
    broker.submit_order(order)
    
    assert len(broker.order_book) == 1
    assert broker.order_book[0].status == OrderStatus.PENDING
    
    # Provide bar data with high >= limit_price
    bar_data = {
        "AAPL": {
            "high": 112.0,
            "close": 105.0
        }
    }
    
    broker.match_orders(bar_data)
    
    assert order.status == OrderStatus.FILLED
    # Check execution at limit_price (110 * 50 = 5500)
    assert broker.cash == 10000.0 + 5500.0
    assert broker.holdings["AAPL"] == 50

def test_slippage_injection_in_broker():
    slippage_model = ExtremeRiskSlippageModel(penalty_rate=0.5)
    broker = SimBroker(initial_cash=10000.0, slippage_model=slippage_model)
    
    # Mock holdings
    broker.holdings["ST_BOMB"] = 100
    
    # Create Market Sell order
    order = Order(
        ticker="ST_BOMB",
        direction=OrderDirection.SELL,
        quantity=100,
        order_type=OrderType.MARKET,
        limit_price=0.0
    )
    broker.submit_order(order)
    
    # Provide bar data with close price 100.0
    bar_data = {
        "ST_BOMB": {
            "high": 105.0,
            "close": 100.0
        }
    }
    
    broker.match_orders(bar_data)
    
    assert order.status == OrderStatus.FILLED
    # Base price 100, penalty 0.5 -> execute at 50.0
    # Proceeds = 100 shares * 50.0 = 5000.0
    assert broker.cash == 10000.0 + 5000.0
    assert "ST_BOMB" not in broker.holdings


def test_automatic_order_expiry():
    broker = SimBroker(initial_cash=10000.0, slippage=0.0)
    broker.holdings["AAPL"] = 100
    
    order = Order(
        ticker="AAPL",
        direction=OrderDirection.SELL,
        quantity=50,
        order_type=OrderType.LIMIT,
        limit_price=110.0,
        effective_date="2023-01-01"
    )
    broker.submit_order(order)
    
    assert broker.order_book[0].status == OrderStatus.PENDING
    
    bar_data = {
        "AAPL": {
            "high": 109.0, # Does not hit 110.0
            "close": 105.0
        }
    }
    
    # Process on next day. Should not match, then should be canceled by _expire_old_orders.
    broker.match_orders(bar_data, current_date="2023-01-02")
    
    assert order.status == OrderStatus.CANCELED
    assert broker.cash == 10000.0
    assert broker.holdings["AAPL"] == 100
