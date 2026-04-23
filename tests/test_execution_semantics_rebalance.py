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

def test_rebalance_market_order_fills_on_next_bar_open():
    feed = DummyDataFeed("tests/fixtures/fixture_rebalance_next_bar.csv")
    broker = SimBroker(initial_cash=100000, slippage=0.0)
    strategy = CBRotationStrategy(top_n=1, weight_per_position=1.0, rebalance_period='daily', take_profit_threshold=None, stop_loss_threshold=-0.5)
    
    # Run Day 1
    dates = feed.df['date'].unique()
    date1 = dates[0]
    data_slice = feed.get_data(None, date1)
    
    daily_data = {}
    for _, row in data_slice.iterrows():
        ticker = row['ticker']
        daily_data[ticker] = {
            'open': row['open'], 'high': row['high'], 'low': row['low'], 'close': row['close']
        }
        
    date_str = str(pd.to_datetime(date1).date())
    broker.match_orders(daily_data, current_date=date_str)
    
    current_prices = {row['ticker']: row['close'] for _, row in data_slice.iterrows()}
    broker.update_equity(current_prices)
    
    class Context:
        pass
    context = Context()
    context.daily_return = {}
    context.holdings = list(broker.holdings.keys())
    context.broker = broker
    context.current_date = pd.to_datetime(date1)
    context.current_prices = current_prices
    
    strategy.generate_target_portfolio(context, data_slice)
    
    # Expectation 1: Generated on Day 1
    assert len(broker.order_book) == 1
    order = broker.order_book[0]
    assert order.ticker == 'T1'
    assert order.status == OrderStatus.PENDING
    assert order.order_type == OrderType.MARKET
    assert order.direction == OrderDirection.BUY
    
    assert broker.cash == 100000.0
    assert broker.holdings.get('T1', 0) == 0
    
    # Run Day 2
    date2 = dates[1]
    data_slice2 = feed.get_data(None, date2)
    daily_data2 = {}
    for _, row in data_slice2.iterrows():
        ticker = row['ticker']
        daily_data2[ticker] = {
            'open': row['open'], 'high': row['high'], 'low': row['low'], 'close': row['close']
        }
    
    date_str2 = str(pd.to_datetime(date2).date())
    broker.match_orders(daily_data2, current_date=date_str2)
    
    # Expectation 2: Fills on Day 2 open price (9.0)
    assert order.status == OrderStatus.FILLED
    
    # 100000 / 10.0 = 10000 shares
    # 10000 shares * 9.0 = 90000 cost
    # remaining cash = 10000.0
    assert broker.cash == 10000.0
    assert broker.holdings.get('T1', 0) == 10000

def test_rebalance_orders_cannot_fill_on_same_bar():
    feed = DummyDataFeed("tests/fixtures/fixture_rebalance_next_bar.csv")
    broker = SimBroker(initial_cash=100000, slippage=0.0)
    strategy = CBRotationStrategy(top_n=1, weight_per_position=1.0, rebalance_period='daily', take_profit_threshold=None, stop_loss_threshold=-0.5)
    
    dates = feed.df['date'].unique()
    date1 = dates[0]
    data_slice = feed.get_data(None, date1)
    
    daily_data = {}
    for _, row in data_slice.iterrows():
        ticker = row['ticker']
        daily_data[ticker] = {
            'open': row['open'], 'high': row['high'], 'low': row['low'], 'close': row['close']
        }
        
    date_str = str(pd.to_datetime(date1).date())
    broker.match_orders(daily_data, current_date=date_str)
    
    current_prices = {row['ticker']: row['close'] for _, row in data_slice.iterrows()}
    broker.update_equity(current_prices)
    
    class Context:
        pass
    context = Context()
    context.daily_return = {}
    context.holdings = list(broker.holdings.keys())
    context.broker = broker
    context.current_date = pd.to_datetime(date1)
    context.current_prices = current_prices
    
    strategy.generate_target_portfolio(context, data_slice)
    
    assert len(broker.order_book) == 1
    order = broker.order_book[0]
    assert order.status == OrderStatus.PENDING
    assert broker.holdings.get('T1', 0) == 0