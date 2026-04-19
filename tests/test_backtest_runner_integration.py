import pytest
import pandas as pd
import numpy as np

from ams.runners.backtest_runner import BacktestRunner
from ams.core.history_datafeed import HistoryDataFeed
from ams.core.sim_broker import SimBroker
from ams.core.cb_rotation_strategy import CBRotationStrategy

def test_backtest_runner_short_period():
    # Mock data for 3 days
    data = []
    dates = pd.date_range("2024-01-01", "2024-01-03")
    
    # 3 tickers
    tickers = ["CB1", "CB2", "CB3"]
    
    for date in dates:
        for ticker in tickers:
            data.append({
                'date': date,
                'ticker': ticker,
                'close_price': 100,
                'premium_rate': 0.1,
                'amount': 15000000,
                'volume': 10000,
                'is_st': False,
                'suspended': False
            })
            
    df = pd.DataFrame(data)
    
    feed = HistoryDataFeed(data=df)
    broker = SimBroker()
    strategy = CBRotationStrategy(top_n=2) # pick 2 out of 3
    
    runner = BacktestRunner(feed, broker, strategy)
    df_equity = runner.run("2024-01-01", "2024-01-03")
    
    # Check if run without error
    assert not df_equity.empty
    assert len(df_equity) == 3
    
    # Check if broker updated holdings
    assert len(broker.holdings) > 0

def test_backtest_metrics_calculation():
    # Mock equity curve
    df_equity = pd.DataFrame({
        'date': pd.date_range("2024-01-01", "2024-01-05"),
        'equity': [100000, 110000, 90000, 105000, 120000]
    })
    
    runner = BacktestRunner(None, None, None)
    metrics = runner.calculate_metrics(df_equity)
    
    assert 'Total Return' in metrics
    assert 'Max Drawdown' in metrics
    assert 'Final Equity' in metrics
    
    # Total return: (120000 - 100000) / 100000 = 0.2
    assert metrics['Total Return'] == pytest.approx(0.2)
    
    # Max drawdown: from 110000 to 90000 -> (90000 - 110000) / 110000 = -0.1818...
    assert metrics['Max Drawdown'] == pytest.approx(-0.1818, abs=0.0001)

def test_initial_cash_default():
    broker = SimBroker()
    runner = BacktestRunner(None, broker, None)
    assert broker.initial_cash == 4000000.0

def test_daily_equity_sync():
    # Mock data
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
            self.call_count = 0
            self.passed_prices = []
            
        def update_equity(self, current_prices=None):
            self.call_count += 1
            if current_prices:
                self.passed_prices.append(current_prices)
            super().update_equity(current_prices or {})
            
    broker = MockBroker()
    
    class MockStrategy:
        def generate_target_portfolio(self, context, data):
            return {"CB1": 0.1}
            
    strategy = MockStrategy()
    runner = BacktestRunner(feed, broker, strategy)
    runner.run("2024-01-01", "2024-01-02")
    
    # Should be called during run loop with current_prices dict
    assert broker.call_count >= 2
    assert len(broker.passed_prices) > 0
    assert "CB1" in broker.passed_prices[0]
    
def test_final_report_format(capsys):
    df_equity = pd.DataFrame({
        'date': pd.date_range("2024-01-01", "2024-01-02"),
        'equity': [4000000.0, 4100000.0]
    })
    runner = BacktestRunner(None, None, None)
    runner.print_report(df_equity)
    captured = capsys.readouterr()
    output = captured.out
    
    assert "Total Return: 2.5000%" in output
    assert "Max Drawdown: 0.0000%" in output
    assert "Final Equity: 4100000.00" in output


def test_runner_event_flow_delegation():
    # Mock data
    data = []
    dates = pd.date_range("2024-01-01", "2024-01-02")
    tickers = ["CB1"]
    
    for date in dates:
        for ticker in tickers:
            data.append({
                'date': date,
                'ticker': ticker,
                'close_price': 100,
                'high_price': 105,
                'low_price': 95,
                'open_price': 98
            })
            
    df = pd.DataFrame(data)
    feed = HistoryDataFeed(data=df)
    
    class MockBroker(SimBroker):
        def __init__(self):
            super().__init__()
            self.match_orders_called = False
            self.update_equity_called = False
            
        def match_orders(self, daily_data):
            self.match_orders_called = True
            # Verify data format passed to match_orders
            assert "CB1" in daily_data
            assert 'high' in daily_data["CB1"]
            assert 'close' in daily_data["CB1"]
            super().match_orders(daily_data)
            
        def update_equity(self, current_prices=None):
            self.update_equity_called = True
            super().update_equity(current_prices)
            
    broker = MockBroker()
    
    class MockStrategy:
        def __init__(self):
            self.generate_target_portfolio_called = False
            
        def generate_target_portfolio(self, context, data_slice):
            self.generate_target_portfolio_called = True
            
    strategy = MockStrategy()
    runner = BacktestRunner(feed, broker, strategy)
    
    # Check that runner doesn't have its own match logic
    assert not hasattr(runner, 'match_order')
    
    runner.run("2024-01-01", "2024-01-02")
    
    assert broker.match_orders_called, "Runner should call broker.match_orders"
    assert broker.update_equity_called, "Runner should call broker.update_equity"
    assert strategy.generate_target_portfolio_called, "Runner should call strategy.generate_target_portfolio"
