import logging

try:
    from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
except ImportError:
    class XtQuantTrader:
        def __init__(self, path, session_id):
            self.path = path
            self.session_id = session_id
            self.started = False
            self.connected = False
            self.callback = None
            
        def start(self):
            self.started = True
            
        def connect(self):
            self.connected = True
            
        def register_callback(self, callback):
            self.callback = callback

    class XtQuantTraderCallback:
        def on_disconnected(self): pass
        def on_order_stock_async_response(self, response): pass
        def on_trade(self, trade): pass

class AMSXtTraderCallback(XtQuantTraderCallback):
    def __init__(self):
        super().__init__()
        self.pending_orders = set()

    def on_disconnected(self):
        logging.error("[-] 交易服务器连接断开")

    def on_order_stock_async_response(self, response):
        logging.info(f"[委托回调] {response}")

    def on_trade(self, trade):
        logging.info(f"[成交回调] {trade}")

class QMTTraderInit:
    def __init__(self, path, session_id):
        self.trader = XtQuantTrader(path, session_id)
        self.callback = AMSXtTraderCallback()
        
    def connect_and_mount(self):
        self.trader.start()
        self.trader.connect()
        self.trader.register_callback(self.callback)
        return self.trader

