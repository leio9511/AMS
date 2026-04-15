import pytest
import pandas as pd
from ams.core.sim_broker import SimBroker
from ams.core.history_datafeed import HistoryDataFeed
from ams.runners.backtest_runner import BacktestRunner
from ams.core.base import BaseStrategy

def test_sim_broker_deducts_funds_correctly():
    broker = SimBroker(initial_cash=100000.0, slippage=0.001)
    broker.order_target_percent('AAPL', 0.5, price=100.0)
    
    assert 'AAPL' in broker.holdings
    assert broker.holdings['AAPL'] == 500
    
    # 500 * 100 + 500 * 100 * 0.001 slippage = 50050 cost
    assert broker.cash == pytest.approx(49950.0)

def test_history_datafeed_returns_correct_slice():
    df = pd.DataFrame({
        'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
        'ticker': ['AAPL', 'AAPL', 'AAPL'],
        'price': [150, 155, 160]
    })
    feed = HistoryDataFeed(df)
    
    slice1 = feed.get_data(['AAPL'], '2024-01-02')
    assert len(slice1) == 1
    assert slice1.iloc[0]['price'] == 155

def test_backtest_runner_clock_ticks_correctly():
    df = pd.DataFrame({
        'date': ['2024-01-01', '2024-01-02'],
        'ticker': ['AAPL', 'AAPL'],
        'price': [150, 155]
    })
    feed = HistoryDataFeed(df)
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    
    class MockStrategy(BaseStrategy):
        def __init__(self):
            self.call_dates = []
        def on_bar(self, context, data):
            pass
        def generate_target_portfolio(self, context, data):
            if not data.empty:
                 self.call_dates.append(data.iloc[0]['date'])
                 return {'AAPL': 0.1}
            return {}

    strategy = MockStrategy()
    runner = BacktestRunner(feed, broker, strategy)
    
    runner.run('2024-01-01', '2024-01-02')
    
    assert len(strategy.call_dates) == 2
    assert strategy.call_dates[0] == pd.Timestamp('2024-01-01')
    assert strategy.call_dates[1] == pd.Timestamp('2024-01-02')
    # 10% of 100000 = 10000. 10000 / 150 = 66.66 -> floor to 60 lots.
    # So 60 shares.
    assert broker.holdings['AAPL'] == 60
