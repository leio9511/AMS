import pytest
import pandas as pd
from decimal import Decimal
from ams.core.sim_broker import SimBroker
from ams.core.cb_rotation_strategy import CBRotationStrategy
from ams.runners.backtest_runner import BacktestRunner
from ams.core.order import OrderStatus, OrderType, OrderDirection
from ams.core.base import BaseDataFeed

class DummyDataFeed(BaseDataFeed):
    def __init__(self, data_path):
        self.df = pd.read_csv(data_path)
        self.df['date'] = pd.to_datetime(self.df['date'])

    def get_data(self, tickers, date):
        return self.df[self.df['date'] == pd.to_datetime(date)]

def test_stop_loss_fills_on_next_bar_open():
    feed = DummyDataFeed("tests/fixtures/fixture_stop_loss_immediate_effect.csv")
    broker = SimBroker(initial_cash=100000, slippage=0.0)
    strategy = CBRotationStrategy(top_n=1, weight_per_position=1.0, rebalance_period='daily', 
                                  stop_loss_threshold=-0.05, take_profit_threshold=None)
    runner = BacktestRunner(feed, broker, strategy)
    dates = feed.df['date'].unique()
    
    runner.run(dates[0], pd.to_datetime('2024-01-04'))
    
    assert broker.holdings.get('T1', 0) == 0
    assert broker.cash == 80000.0
    assert broker.total_equity == 80000.0
    
    # Explicitly verify the correct order status transitions
    sell_orders = [o for o in broker.order_book if o.direction == OrderDirection.SELL and o.order_type == OrderType.MARKET]
    assert len(sell_orders) == 1
    assert sell_orders[0].status == OrderStatus.FILLED

def test_weekly_rebalance_should_not_mask_stop_loss():
    feed = DummyDataFeed("tests/fixtures/fixture_stop_loss_immediate_effect.csv")
    broker = SimBroker(initial_cash=100000, slippage=0.0)
    strategy = CBRotationStrategy(top_n=1, weight_per_position=1.0, rebalance_period='weekly', 
                                  stop_loss_threshold=-0.05, take_profit_threshold=None)
    runner = BacktestRunner(feed, broker, strategy)
    dates = feed.df['date'].unique()
    
    runner.run(dates[0], dates[-1])
    
    assert broker.holdings.get('T1', 0) == 0
    assert broker.cash == 80000.0
    assert broker.total_equity == 80000.0
    
    # Explicitly verify the correct order status transitions
    sell_orders = [o for o in broker.order_book if o.direction == OrderDirection.SELL and o.order_type == OrderType.MARKET]
    assert len(sell_orders) == 1
    assert sell_orders[0].status == OrderStatus.FILLED

def test_daily_stop_loss_threshold_changes_affect_outcome():
    feed = DummyDataFeed("tests/fixtures/fixture_stop_loss_thresholds.csv")
    
    broker1 = SimBroker(initial_cash=100000, slippage=0.0)
    strategy1 = CBRotationStrategy(top_n=1, weight_per_position=1.0, rebalance_period='daily', 
                                  stop_loss_threshold=-0.01, take_profit_threshold=None)
    runner1 = BacktestRunner(feed, broker1, strategy1)
    
    broker2 = SimBroker(initial_cash=100000, slippage=0.0)
    strategy2 = CBRotationStrategy(top_n=1, weight_per_position=1.0, rebalance_period='daily', 
                                  stop_loss_threshold=-0.10, take_profit_threshold=None)
    runner2 = BacktestRunner(feed, broker2, strategy2)
    
    dates = feed.df['date'].unique()
    
    runner1.run(dates[0], dates[-1])
    runner2.run(dates[0], dates[-1])
    
    # Tight SL triggers earlier, avoids worse drop.
    assert broker1.cash == 92000.0
    assert broker1.total_equity == 92000.0
    
    # Wide SL triggers later, causing larger drawdown.
    assert broker2.cash == 200.0
    assert broker2.total_equity == 81800.0
