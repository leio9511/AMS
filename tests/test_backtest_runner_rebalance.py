import pytest
import pandas as pd
from ams.runners.backtest_runner import BacktestRunner

class MockDataFeed:
    def get_data(self, *args, **kwargs):
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
        
    def match_orders(self, daily_data):
        pass

class MockStrategy:
    def __init__(self, target_portfolio):
        self.target_portfolio = target_portfolio
        
    def generate_target_portfolio(self, context, data):
        # We simulate the rebalancing logic here since it was moved from Runner
        broker = context.broker
        current_holdings = list(broker.holdings.keys())
        total_equity = broker.total_equity
        current_prices = context.current_prices
        
        for ticker in current_holdings:
            if ticker not in self.target_portfolio:
                broker.order_target_percent(ticker, 0.0, price=current_prices.get(ticker))
            else:
                current_value = broker.holdings.get(ticker, 0) * current_prices.get(ticker, 0.0)
                current_weight = current_value / total_equity if total_equity > 0 else 0.0
                target_weight = self.target_portfolio[ticker]
                if current_weight - target_weight > 0.005:
                    broker.order_target_percent(ticker, target_weight, price=current_prices.get(ticker))
                    
        for ticker, target_weight in self.target_portfolio.items():
            if ticker not in current_holdings:
                broker.order_target_percent(ticker, target_weight, price=current_prices.get(ticker))
            else:
                current_value = broker.holdings.get(ticker, 0) * current_prices.get(ticker, 0.0)
                current_weight = current_value / total_equity if total_equity > 0 else 0.0
                if target_weight - current_weight > 0.005:
                    broker.order_target_percent(ticker, target_weight, price=current_prices.get(ticker))
                    
        return self.target_portfolio

def test_no_orders_when_portfolio_unchanged():
    feed = MockDataFeed()
    broker = MockBroker()
    strategy = MockStrategy({'CB1': 0.5, 'CB2': 0.5})
    
    runner = BacktestRunner(feed, broker, strategy)
    runner.run('2025-01-01', '2025-01-01')
    assert len(broker.orders) == 0

def test_orders_only_for_diff():
    feed = MockDataFeed()
    broker = MockBroker()
    strategy = MockStrategy({'CB1': 0.51, 'CB2': 0.49, 'CB3': 0.1})
    
    runner = BacktestRunner(feed, broker, strategy)
    runner.run('2025-01-01', '2025-01-01')
    assert len(broker.orders) == 3
    
    order_dict = dict(broker.orders)
    assert 'CB1' in order_dict and order_dict['CB1'] == 0.51
    assert 'CB2' in order_dict and order_dict['CB2'] == 0.49
    assert 'CB3' in order_dict and order_dict['CB3'] == 0.1

def test_skip_small_diffs():
    feed = MockDataFeed()
    broker = MockBroker()
    strategy = MockStrategy({'CB1': 0.504, 'CB2': 0.496})
    
    runner = BacktestRunner(feed, broker, strategy)
    runner.run('2025-01-01', '2025-01-01')
    assert len(broker.orders) == 0
