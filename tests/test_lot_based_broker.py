import json
import pytest
from ams.core.sim_broker import SimBroker

def test_integration_suspension_valuation_preserved():
    """
    Test Case 1: Given 100 bonds of A yesterday at 100.55, 
    if today's prices exclude A, broker.total_equity attributes exactly 10055.00 to bond A.
    """
    broker = SimBroker(initial_cash=0.0, slippage=0.0)
    broker.holdings = {"A_BOND": 100}
    
    # Yesterday's prices
    broker.update_equity({"A_BOND": 100.55})
    assert broker.total_equity == 10055.0
    
    # Today's prices (missing A_BOND)
    broker.update_equity({"B_BOND": 90.0})
    assert broker.total_equity == 10055.0

def test_integration_json_serialization_compatibility():
    """
    Test Case 2: After running a simulated day of trading, 
    json.dumps({"equity": broker.total_equity}) successfully parses without Decimal serialization errors.
    """
    broker = SimBroker(initial_cash=10000.0, slippage=0.0)
    
    # Simulate a day of trading
    broker.update_equity({"A_BOND": 100.0})
    broker.order_target_percent("A_BOND", 0.5, 100.0)
    
    # Broker should buy 50 shares of A_BOND (must be multiple of 10)
    assert broker.holdings["A_BOND"] == 50
    assert broker.cash == 5000.0
    
    # Validate JSON serialization
    try:
        data = json.dumps({"equity": broker.total_equity, "cash": broker.cash})
    except TypeError:
        pytest.fail("total_equity or cash is not JSON serializable")
        
    assert isinstance(broker.total_equity, float)
    assert isinstance(broker.cash, float)
