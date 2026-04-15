import pytest
from ams.core.sim_broker import SimBroker
from decimal import Decimal

def test_update_equity_with_suspension():
    broker = SimBroker(initial_cash=0.0, slippage=0.0)
    broker.holdings = {"A_BOND": 100}
    
    # Day 1: Update equity with current price
    broker.update_equity({"A_BOND": 100.55})
    assert broker.total_equity == 10055.0
    
    # Day 2: Price is missing (suspended), should use fallback
    broker.update_equity({"B_BOND": 90.0}) # A_BOND not in current_prices
    assert broker.total_equity == 10055.0

def test_update_equity_cold_start_missing_price():
    broker = SimBroker(initial_cash=0.0, slippage=0.0)
    broker.holdings = {"NEW_BOND": 100}
    
    # Day 1: Price is completely missing, no history either
    broker.update_equity({"OTHER_BOND": 90.0}) 
    assert broker.total_equity == 0.0
