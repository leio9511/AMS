import pytest
import pandas as pd
from ams.runners.backtest_runner import BacktestRunner
from ams.core.base import BaseStrategy

class MockDataFeed:
    def get_data(self, *args, **kwargs):
        # We just need to return a non-empty dataframe so runner doesn't skip
        return pd.DataFrame({
            'ticker': ['CB1', 'CB2', 'CB3'],
            'close_price': [100.0, 100.0, 100.0]
        })

class MockBroker:
    def __init__(self):
        self.holdings = {'CB1': 500, 'CB2': 500}
        self.total_equity = 100000.0
        self.orders = []
        self.cash = 100000.0
        self.slippage = 0.0
        
    def submit_order(self, order):
        self.orders.append(order)

    def update_equity(self, current_prices=None):
        pass

    def match_orders(self, daily_data):
        pass

class MockStrategy(BaseStrategy):
    def __init__(self, target_portfolio):
        self.target_portfolio = target_portfolio
        
    def on_bar(self, context, data):
        pass

    def generate_target_portfolio(self, context, data):
        broker = context.broker
        current_prices = getattr(context, 'current_prices', {})
        current_equity = broker.total_equity
        current_holdings_shares = broker.holdings.copy()
        
        # Sell missing or decreased
        for ticker in list(current_holdings_shares.keys()):
            if ticker not in self.target_portfolio:
                self.order_target_percent(
                    broker=broker, ticker=ticker, target_percent=0.0,
                    current_price=current_prices.get(ticker), current_equity=current_equity,
                    current_shares=current_holdings_shares[ticker]
                )
            else:
                target_weight = self.target_portfolio[ticker]
                current_val = current_holdings_shares[ticker] * current_prices.get(ticker, 0)
                current_weight = current_val / current_equity if current_equity > 0 else 0
                if current_weight - target_weight > 0.005:
                    self.order_target_percent(
                        broker=broker, ticker=ticker, target_percent=target_weight,
                        current_price=current_prices.get(ticker), current_equity=current_equity,
                        current_shares=current_holdings_shares[ticker]
                    )
                    
        # Buy new or increased
        for ticker, target_weight in self.target_portfolio.items():
            current_shares = current_holdings_shares.get(ticker, 0)
            current_val = current_shares * current_prices.get(ticker, 0)
            current_weight = current_val / current_equity if current_equity > 0 else 0
            
            if target_weight - current_weight > 0.005:
                self.order_target_percent(
                    broker=broker, ticker=ticker, target_percent=target_weight,
                    current_price=current_prices.get(ticker), current_equity=current_equity,
                    current_shares=current_shares
                )
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
    
    order_tickers = {o.ticker for o in broker.orders}
    assert 'CB1' in order_tickers
    assert 'CB2' in order_tickers
    assert 'CB3' in order_tickers

def test_skip_small_diffs():
    feed = MockDataFeed()
    broker = MockBroker()
    # CB1 increases from 0.5 to 0.504 (diff < 0.005) -> skip
    # CB2 decreases from 0.5 to 0.496 (diff < 0.005) -> skip
    strategy = MockStrategy({'CB1': 0.504, 'CB2': 0.496})
    
    runner = BacktestRunner(feed, broker, strategy)
    runner.run('2025-01-01', '2025-01-01')
    
    assert len(broker.orders) == 0
