import pytest
import pandas as pd
from decimal import Decimal

from ams.core.sim_broker import SimBroker
from ams.core.cb_rotation_strategy import CBRotationStrategy
from ams.runners.backtest_runner import BacktestRunner
from ams.core.order import OrderStatus, OrderDirection, OrderType

class DummyDataFeed:
    def __init__(self, df):
        self.df = df.copy()
        self.df['date'] = pd.to_datetime(self.df['date'])
        
    def get_data(self, tickers, date):
        return self.df[self.df['date'] == pd.to_datetime(date)]

def test_stop_loss_overrides_take_profit():
    df = pd.read_csv('/root/projects/AMS/tests/fixtures/fixture_stop_loss_immediate_effect.csv')
    data_feed = DummyDataFeed(df)
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    strategy = CBRotationStrategy(
        top_n=1, 
        weight_per_position=1.0, 
        stop_loss_threshold=-0.05, 
        rebalance_period='daily',
        take_profit_threshold=0.10,
        liquidity_threshold=0
    )
    runner = BacktestRunner(data_feed, broker, strategy)
    dates = pd.Series(pd.to_datetime(df['date'].unique())).sort_values()
    runner.run(dates.iloc[0], dates.iloc[-1])
    
    orders = broker.order_book
    canceled_tps = [o for o in orders if o.order_type == OrderType.LIMIT and o.status == OrderStatus.CANCELED]
    sl_orders = [o for o in orders if o.order_type == OrderType.MARKET and o.direction == OrderDirection.SELL and o.status == OrderStatus.FILLED]
    
    assert len(canceled_tps) >= 1
    assert len(sl_orders) >= 1

