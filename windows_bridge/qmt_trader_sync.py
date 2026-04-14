import logging
import json
import os

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
            self.orders = []
            
        def start(self):
            self.started = True
            
        def connect(self):
            self.connected = True
            
        def register_callback(self, callback):
            self.callback = callback
            
        def order_stock_async(self, account, stock_code, order_type, order_volume, price_type, price, strategy_name, order_remark):
            self.orders.append({
                "account": account,
                "stock_code": stock_code,
                "order_type": order_type, # 23=buy, 24=sell
                "order_volume": order_volume,
                "price_type": price_type,
                "price": price,
                "strategy_name": strategy_name,
                "order_remark": order_remark
            })
            return 1

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

def sync_portfolio(current_positions, trader, account=None, target_file="target_positions.json"):
    if not os.path.exists(target_file):
        targets = {}
    else:
        with open(target_file, 'r') as f:
            targets = json.load(f)
            
    all_codes = set(targets.keys()).union(set(current_positions.keys()))
    
    for code in sorted(all_codes):
        target_vol = targets.get(code, 0)
        curr_vol = current_positions.get(code, 0)
        
        diff = target_vol - curr_vol
        if diff > 0:
            # buy (type 23)
            trader.order_stock_async(account, code, 23, diff, 5, 0, "sync", "buy")
        elif diff < 0:
            # sell (type 24)
            trader.order_stock_async(account, code, 24, abs(diff), 5, 0, "sync", "sell")

