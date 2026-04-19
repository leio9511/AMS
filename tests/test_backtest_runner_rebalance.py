import pytest
import pandas as pd
from ams.runners.backtest_runner import BacktestRunner

class MockDataFeed:
    def get_data(self, *args, **kwargs):
        # We just need to return a non-empty dataframe so runner doesn't skip
        return pd.DataFrame({
            'ticker': ['CB1', 'CB2'],
            'close_price': [100.0, 100.0]
        })

class MockBroker:
    def __init__(self):
        self.holdings = {'CB1': 500, 'CB2': 500}
        self.total_equity = 100000.0
        self.orders = []
        
    def order_target_percent(self, ticker, percent, price=None):
        self.orders.append((ticker, percent))

    def update_equity(self, current_prices=None):
        pass

class MockStrategy:
    def __init__(self, target_portfolio):
        self.target_portfolio = target_portfolio
        
    def generate_target_portfolio(self, context, data):
        return self.target_portfolio

def test_no_orders_when_portfolio_unchanged():
    feed = MockDataFeed()
    broker = MockBroker()
    # Weights exactly match current holdings (50% each)
    strategy = MockStrategy({'CB1': 0.5, 'CB2': 0.5})
    
    runner = BacktestRunner(feed, broker, strategy)
    runner.run('2025-01-01', '2025-01-01')
    
    # Should not emit any orders because difference is < 0.005
    assert len(broker.orders) == 0

def test_orders_only_for_diff():
    feed = MockDataFeed()
    broker = MockBroker()
    # CB1 increases from 50% to 51% (>0.005)
    # CB2 decreases from 50% to 49% (>0.005)
    # CB3 is new (0 to 10%)
    # Total target = 1.1 (just for test diff logic)
    strategy = MockStrategy({'CB1': 0.51, 'CB2': 0.49, 'CB3': 0.1})
    
    runner = BacktestRunner(feed, broker, strategy)
    runner.run('2025-01-01', '2025-01-01')
    
    # Expect 3 orders
    assert len(broker.orders) == 3
    
    # Check the emitted orders
    order_dict = dict(broker.orders)
    assert 'CB1' in order_dict and order_dict['CB1'] == 0.51
    assert 'CB2' in order_dict and order_dict['CB2'] == 0.49
    assert 'CB3' in order_dict and order_dict['CB3'] == 0.1

def test_skip_small_diffs():
    feed = MockDataFeed()
    broker = MockBroker()
    # CB1 increases from 0.5 to 0.504 (diff < 0.005) -> skip
    # CB2 decreases from 0.5 to 0.496 (diff < 0.005) -> skip
    strategy = MockStrategy({'CB1': 0.504, 'CB2': 0.496})
    
    runner = BacktestRunner(feed, broker, strategy)
    runner.run('2025-01-01', '2025-01-01')
    
    assert len(broker.orders) == 0
