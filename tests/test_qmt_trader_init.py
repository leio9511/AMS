import logging
import pytest
from windows_bridge.qmt_trader_sync import QMTTraderInit, AMSXtTraderCallback, XtQuantTrader

def test_trader_initialization_success():
    init = QMTTraderInit(path="dummy/path", session_id=123)
    trader = init.connect_and_mount()
    
    assert trader.started is True
    assert trader.connected is True
    assert isinstance(trader.callback, AMSXtTraderCallback)

def test_trader_callback_disconnect(caplog):
    callback = AMSXtTraderCallback()
    
    with caplog.at_level(logging.ERROR):
        callback.on_disconnected()
        
    assert "[-] 交易服务器连接断开" in caplog.text

def test_order_status_logging(caplog):
    callback = AMSXtTraderCallback()
    
    with caplog.at_level(logging.INFO):
        callback.on_order_stock_async_response("test_order_response")
        callback.on_trade("test_trade_event")
        
    assert "[委托回调] test_order_response" in caplog.text
    assert "[成交回调] test_trade_event" in caplog.text
