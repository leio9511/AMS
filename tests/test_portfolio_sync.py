import json
import os
import pytest
from windows_bridge.qmt_trader_sync import sync_portfolio, XtQuantTrader

@pytest.fixture
def target_file(tmp_path):
    p = tmp_path / "target_positions.json"
    return str(p)

def test_sync_portfolio_perfect_match(target_file):
    trader = XtQuantTrader("dummy", 1)
    
    with open(target_file, 'w') as f:
        json.dump({"113050.SH": 100, "123004.SZ": 200}, f)
        
    current_positions = {"113050.SH": 100, "123004.SZ": 200}
    
    sync_portfolio(current_positions, trader, account=None, target_file=target_file)
    
    assert len(trader.orders) == 0

def test_sync_portfolio_missing_assets(target_file):
    trader = XtQuantTrader("dummy", 1)
    
    with open(target_file, 'w') as f:
        json.dump({"113050.SH": 100, "123004.SZ": 200}, f)
        
    current_positions = {"113050.SH": 100} # missing 123004.SZ
    
    sync_portfolio(current_positions, trader, account=None, target_file=target_file)
    
    assert len(trader.orders) == 1
    assert trader.orders[0]["stock_code"] == "123004.SZ"
    assert trader.orders[0]["order_volume"] == 200
    assert trader.orders[0]["order_type"] == 23 # buy

def test_sync_portfolio_excess_assets(target_file):
    trader = XtQuantTrader("dummy", 1)
    
    with open(target_file, 'w') as f:
        json.dump({"113050.SH": 100}, f)
        
    current_positions = {"113050.SH": 100, "123004.SZ": 200} # excess 123004.SZ
    
    sync_portfolio(current_positions, trader, account=None, target_file=target_file)
    
    assert len(trader.orders) == 1
    assert trader.orders[0]["stock_code"] == "123004.SZ"
    assert trader.orders[0]["order_volume"] == 200
    assert trader.orders[0]["order_type"] == 24 # sell
