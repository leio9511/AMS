import pytest
from ams.core.sim_broker import SimBroker

def test_lot_based_buy_exact():
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    # price 125, target value 10000. percent = 10000 / 100000 = 0.1
    broker.order_target_percent("AAPL", 0.1, price=125.0)
    # 10000 / 125 = 80. Floor(80/10)*10 = 80
    assert broker.holdings["AAPL"] == 80
    assert broker.cash == 100000.0 - 80 * 125.0

def test_lot_based_buy_round_down():
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    # target value 10100. percent = 10100 / 100000 = 0.101
    broker.order_target_percent("AAPL", 0.101, price=125.0)
    # 10100 / 125 = 80.8. Floor(80.8/10)*10 = 80
    assert broker.holdings["AAPL"] == 80
    assert broker.cash == 100000.0 - 80 * 125.0

def test_mtm_equity_update():
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    broker.holdings["AAPL"] = 80
    broker.cash = 90000.0
    
    current_prices = {"AAPL": 130.0}
    broker.update_equity(current_prices)
    
    # equity = 90000.0 + 80 * 130.0 = 100400.0
    assert broker.total_equity == 100400.0

def test_invalid_price_protection():
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    broker.order_target_percent("AAPL", 0.1, price=0.0)
    assert "AAPL" not in broker.holdings or broker.holdings["AAPL"] == 0
    assert broker.cash == 100000.0
    
    broker.order_target_percent("AAPL", 0.1, price=-5.0)
    assert "AAPL" not in broker.holdings or broker.holdings["AAPL"] == 0
    assert broker.cash == 100000.0

import logging
from ams.core.order import Order, OrderType, OrderDirection, OrderStatus

def test_expire_old_orders_logging(caplog):
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    order = Order(
        ticker="AAPL",
        order_type=OrderType.LIMIT,
        direction=OrderDirection.BUY,
        quantity=10,
        limit_price=150.0,
        effective_date="2023-01-01"
    )
    # Using dynamic id if missing
    order_id = getattr(order, 'id', id(order))
    broker.submit_order(order)
    
    with caplog.at_level(logging.INFO):
        broker.expire_orders("2023-01-02")
        
    assert order.status == OrderStatus.CANCELED
    assert "PENDING -> CANCELED" in caplog.text
    assert str(order_id) in caplog.text
    assert "2023-01-01" in caplog.text

