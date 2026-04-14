import logging
import json
import os
import threading

try:
    from xtquant.xttrader import XtQuantTrader as _XtQuantTrader, XtQuantTraderCallback as _XtQuantTraderCallback
    XtQuantTrader = _XtQuantTrader
    XtQuantTraderCallback = _XtQuantTraderCallback
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
                "order_type": order_type,
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

class _FallbackXtData:
    def __init__(self):
        self.subscriptions = {}
        self.callbacks = {}
        
    def subscribe_quote(self, stock_code, period, start_time, end_time, count, callback):
        self.subscriptions[stock_code] = True
        self.callbacks[stock_code] = callback
        return 1

fallback_xtdata = _FallbackXtData()

try:
    from xtquant import xtdata as _real_xtdata
    if hasattr(_real_xtdata, 'subscribe_quote'):
        xtdata = _real_xtdata
    else:
        xtdata = fallback_xtdata
except ImportError:
    xtdata = fallback_xtdata

class AMSXtTraderCallback(XtQuantTraderCallback):
    def __init__(self):
        super().__init__()
        self.pending_orders = set()
        self._lock = threading.Lock()

    def acquire_order_lock(self, code):
        with self._lock:
            if code in self.pending_orders:
                return False
            self.pending_orders.add(code)
            return True

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
            trader.order_stock_async(account, code, 23, diff, 5, 0, "sync", "buy")
        elif diff < 0:
            trader.order_stock_async(account, code, 24, abs(diff), 5, 0, "sync", "sell")

def subscribe_quotes(holdings, trader, account=None):
    callback_tracker = trader.callback if hasattr(trader, 'callback') else None

    for stock_code, info in holdings.items():
        cost_price = info.get('cost_price', 0)
        volume = info.get('volume', 0)
        
        target_profit_price = cost_price * 1.05
        
        def on_tick_callback(data, code=stock_code, target=target_profit_price, vol=volume):
            tick_price = data.get('lastPrice', 0)
            if tick_price >= target:
                if callback_tracker and hasattr(callback_tracker, 'acquire_order_lock'):
                    if not callback_tracker.acquire_order_lock(code):
                        return
                        
                trader.order_stock_async(account, code, 24, vol, 5, 0, "profit_take", "sell")
                
        xtdata.subscribe_quote(stock_code, 'tick', '', '', 0, on_tick_callback)
