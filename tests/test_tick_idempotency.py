import pytest
import threading
from windows_bridge.qmt_trader_sync import subscribe_quotes, XtQuantTrader, AMSXtTraderCallback
import windows_bridge.qmt_trader_sync as qts

class MockXtData:
    def __init__(self):
        self.subscriptions = {}
        self.callbacks = {}
        
    def subscribe_quote(self, stock_code, period, start_time, end_time, count, callback):
        self.subscriptions[stock_code] = True
        self.callbacks[stock_code] = callback
        return 1

@pytest.fixture(autouse=True)
def reset_xtdata():
    qts.xtdata = MockXtData()

def test_tick_callback_triggers_sell_on_profit():
    trader = XtQuantTrader("dummy", 1)
    trader.callback = AMSXtTraderCallback()
    
    holdings = {
        "113050.SH": {"cost_price": 100.0, "volume": 10}
    }
    
    subscribe_quotes(holdings, trader)
        
    callback = qts.xtdata.callbacks.get("113050.SH")
    assert callback is not None
    
    tick_data = {"lastPrice": 105.0}
    callback(tick_data)
    
    assert len(trader.orders) == 1
    assert trader.orders[0]["stock_code"] == "113050.SH"
    assert trader.orders[0]["order_type"] == 24 # sell
    assert trader.orders[0]["order_volume"] == 10
    assert "113050.SH" in trader.callback.pending_orders

def test_tick_callback_ignores_low_price():
    trader = XtQuantTrader("dummy", 1)
    trader.callback = AMSXtTraderCallback()
    
    holdings = {
        "113050.SH": {"cost_price": 100.0, "volume": 10}
    }
    
    subscribe_quotes(holdings, trader)
    
    callback = qts.xtdata.callbacks.get("113050.SH")
    assert callback is not None
    
    tick_data = {"lastPrice": 104.9}
    callback(tick_data)
    
    assert len(trader.orders) == 0
    assert "113050.SH" not in trader.callback.pending_orders

def test_high_frequency_tick_idempotency():
    trader = XtQuantTrader("dummy", 1)
    trader.callback = AMSXtTraderCallback()
    
    holdings = {
        "113050.SH": {"cost_price": 100.0, "volume": 10}
    }
    
    subscribe_quotes(holdings, trader)
    callback = qts.xtdata.callbacks.get("113050.SH")
    assert callback is not None
    
    def simulate_ticks():
        tick_data = {"lastPrice": 106.0}
        callback(tick_data)
        
    threads = []
    for _ in range(5):
        t = threading.Thread(target=simulate_ticks)
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    assert len(trader.orders) == 1
    assert "113050.SH" in trader.callback.pending_orders
