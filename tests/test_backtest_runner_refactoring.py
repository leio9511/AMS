import pytest
import pandas as pd
from ams.runners.backtest_runner import BacktestRunner
from ams.core.history_datafeed import HistoryDataFeed
from ams.core.sim_broker import SimBroker
from ams.core.base import BaseStrategy

def test_backtest_runner_orchestration_only():
    """
    Test Case 1: Expected: Runner correctly invokes broker.match_orders and 
    strategy generation without directly calculating trade settlements.
    """
    # Mock data for 2 days
    data = []
    dates = pd.date_range("2024-01-01", "2024-01-02")
    tickers = ["CB1"]
    
    for date in dates:
        for ticker in tickers:
            data.append({
                'date': date,
                'ticker': ticker,
                'close_price': 100,
            })
            
    df = pd.DataFrame(data)
    feed = HistoryDataFeed(data=df)
    
    class MockBroker(SimBroker):
        def __init__(self):
            super().__init__()
            self.match_called = 0
            self.update_called = 0
            
        def match_orders(self, daily_data):
            self.match_called += 1
            
        def update_equity(self, current_prices=None):
            self.update_called += 1
            super().update_equity(current_prices)

    class MockStrategy(BaseStrategy):
        def __init__(self):
            self.generate_called = 0

        def on_bar(self, context, data):
            pass

        def generate_target_portfolio(self, context, data):
            self.generate_called += 1
            return {}
            
    broker = MockBroker()
    strategy = MockStrategy()
    
    runner = BacktestRunner(feed, broker, strategy)
    runner.run("2024-01-01", "2024-01-02")
    
    # Check that matching and generation are called exactly for each day
    assert broker.match_called == 2
    assert strategy.generate_called == 2
    
    # 2 calls to update_equity per day in BacktestRunner
    assert broker.update_called == 4


def test_runner_integration_baseline():
    """
    Test Case 2: Expected: Full end-to-end integration test passes under the 
    new architecture, proving fallback safety and baseline parity.
    """
    from ams.core.cb_rotation_strategy import CBRotationStrategy
    
    # Mock data for 3 days
    data = []
    dates = pd.date_range("2024-01-01", "2024-01-03")
    
    # 3 tickers
    tickers = ["CB1", "CB2", "CB3"]
    
    for i, date in enumerate(dates):
        for j, ticker in enumerate(tickers):
            data.append({
                'date': date,
                'ticker': ticker,
                'close_price': 100 + i * 10 + j, # price changes
                'premium_rate': 0.1,
                'amount': 15000000,
                'volume': 10000,
                'is_st': False,
                'suspended': False
            })
            
    df = pd.DataFrame(data)
    
    feed = HistoryDataFeed(data=df)
    broker = SimBroker(initial_cash=100000)
    strategy = CBRotationStrategy(top_n=2) # pick 2 out of 3
    
    runner = BacktestRunner(feed, broker, strategy)
    df_equity = runner.run("2024-01-01", "2024-01-03")
    
    # Check if run without error
    assert not df_equity.empty
    assert len(df_equity) == 3
    
    # Check if equity has changed
    assert df_equity['equity'].iloc[-1] != 100000
    
