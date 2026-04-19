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
                 price = data.iloc[0]['price']
                 self.order_target_percent('AAPL', 0.1, price, context.broker)
                 return {'AAPL': 0.1}
            return {}

    strategy = MockStrategy()
    runner = BacktestRunner(feed, broker, strategy)
    
    runner.run('2024-01-01', '2024-01-02')
    
    assert len(strategy.call_dates) == 2
    assert strategy.call_dates[0] == pd.Timestamp('2024-01-01')
    assert strategy.call_dates[1] == pd.Timestamp('2024-01-02')
    
    # Check that there are active orders. Note: since the runner matches orders, 
    # the orders should be matched and filled because the price is present in data_slice.
    # Wait, the matching runs BEFORE `generate_target_portfolio`!
    # "标准事件流：broker.match_orders(daily_data) -> broker.update_equity() -> strategy.generate_target_portfolio(context)"
    # Thus, the orders placed by the strategy are left in `broker.active_orders` and will be matched on the NEXT day!
    # So on day 1 (150), order placed. On day 2, match_orders will see 'AAPL' price 155.
    # Since it's MARKET order, it will fill at 155. 
    # Target value = 0.1 * 100000 = 10000. Price used to calc shares is 150.
    # shares = floor(10000 / 150 / 10) * 10 = 60.
    # Order for 60 shares will be matched on day 2.
    assert broker.holdings['AAPL'] == 60

