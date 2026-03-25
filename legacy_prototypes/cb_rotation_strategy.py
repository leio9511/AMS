"""
可转债双低轮动策略 (miniQMT 模拟盘)
核心因子: 双低值 = 价格 + 溢价率 * 100
"""

import time
import pandas as pd

# Mock xtquant for environment where it is missing
try:
    from xtquant import xtdata
    from xtquant.xttrader import XtQuanttrader, XtQuanttraderCallback
    from xtquant.xttype import StockAccount
    HAS_XTQUANT = True
except ImportError:
    print("WARNING: xtquant not found. Using Mock mode for strategy skeleton.")
    HAS_XTQUANT = False

class CBRotationStrategy:
    def __init__(self, account_id='12345678', session_id=123456):
        self.account_id = account_id
        self.session_id = session_id
        self.acc = None # Account object
        self.xt_trader = None
        self.target_count = 20
        self.market = 'SH' # or 'SZ'

    def connect(self):
        """连接 miniQMT 客户端"""
        if not HAS_XTQUANT:
            print("[Mock] Connected to miniQMT.")
            return True
        # Real connection logic would go here
        return True

    def get_cb_pool(self):
        """获取全市场可转债代码列表"""
        if not HAS_XTQUANT:
            return ["110001.SH", "123001.SZ"] # Mock data
        # 使用 xtdata.get_stock_list_in_sector('全转债')
        return []

    def fetch_data(self, code_list):
        """获取转债实时价格、转股价、正股价格等因子"""
        if not HAS_XTQUANT:
            # Mock factor data
            return pd.DataFrame({
                'code': code_list,
                'price': [110.5, 120.0],
                'premium_rate': [0.05, 0.15] # 溢价率
            })
        # 实盘使用 xtdata.get_full_tick 获取最新报价
        return pd.DataFrame()

    def calculate_double_low(self, df):
        """计算双低因子: 价格 + 溢价率 * 100"""
        df['double_low'] = df['price'] + df['premium_rate'] * 100
        return df.sort_values('double_low')

    def select_top_bonds(self, df):
        """选出双低值最低的前 N 名"""
        return df.head(self.target_count)

    def execute_trade(self, target_list):
        """对比当前持仓与目标列表，进行调仓"""
        print(f"Target bonds to hold: {target_list}")
        if not HAS_XTQUANT:
            print("[Mock] Order placed for rotation.")
            return
        # 实盘使用 xt_trader.order_stock 下单

    def run(self):
        """策略执行主逻辑"""
        print("Starting CB Rotation Strategy...")
        if not self.connect():
            return
        
        pool = self.get_cb_pool()
        data = self.fetch_data(pool)
        df_sorted = self.calculate_double_low(data)
        top_20 = self.select_top_bonds(df_sorted)
        
        self.execute_trade(top_20['code'].tolist())
        print("Strategy cycle completed.")

if __name__ == "__main__":
    strategy = CBRotationStrategy()
    strategy.run()
