import pytest
from ams.core.sim_broker import SimBroker

def test_sim_broker_buy_insufficient_cash_partial_fill():
    broker = SimBroker(initial_cash=10000.0, slippage=0.01)
    # Target value 15000 is 1.5 * equity
    broker.order_target_percent("AAPL", 1.5)
    
    # Expected: cash becomes 0.0, holdings increases by 10000 / 1.01 = 9900.99
    assert broker.cash == 0.0
    assert abs(broker.holdings["AAPL"] - 9900.99) < 0.01
    
def test_sim_broker_buy_sufficient_cash():
    broker = SimBroker(initial_cash=10000.0, slippage=0.01)
    # Target value 5000 is 0.5 * equity
    broker.order_target_percent("AAPL", 0.5)
    
    # Expected: normal buy, cost < cash
    assert broker.cash == 10000.0 - 5050.0
    assert broker.holdings["AAPL"] == 5000.0

def test_sim_broker_sell():
    broker = SimBroker(initial_cash=10000.0, slippage=0.01)
    # First, get some holdings
    broker.order_target_percent("AAPL", 0.5)
    # Cash is 4950.0, holdings AAPL is 5000.0, equity is 9950.0
    
    # Now sell some. Target 0.25 of equity (9950 * 0.25 = 2487.5)
    # diff = 2487.5 - 5000.0 = -2512.5
    # proceeds = 2512.5 * 0.99 = 2487.375
    broker.order_target_percent("AAPL", 0.25)
    
    assert abs(broker.holdings["AAPL"] - 2487.5) < 0.01
    assert abs(broker.cash - (4950.0 + 2487.375)) < 0.01
