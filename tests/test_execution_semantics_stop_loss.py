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

def test_stop_loss_fills_on_next_bar_open():
    """
    Test Case 1: test_stop_loss_fills_on_next_bar_open
    Expected: A stop-loss triggered on Day N is filled on Day N+1 at Day N+1's open price.
    """
    df = pd.read_csv('/root/projects/AMS/tests/fixtures/fixture_stop_loss_immediate_effect.csv')
    data_feed = DummyDataFeed(df)
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    strategy = CBRotationStrategy(
        top_n=1, 
        weight_per_position=1.0, 
        stop_loss_threshold=-0.05, 
        rebalance_period='daily',
        take_profit_threshold=None,
        liquidity_threshold=0
    )
    runner = BacktestRunner(data_feed, broker, strategy)
    dates = pd.Series(pd.to_datetime(df['date'].unique())).sort_values()
    df_equity = runner.run(dates.iloc[0], dates.iloc[-1])
    
    # Day 1: Signal Buy
    # Day 2 Open: Fill Buy at 100. Cash = 0, Holdings = 1000. Day 2 Close: 100. No Signal.
    # Day 3 Open: 94. Close: 94. Daily Return = (94-100)/100 = -0.06 < -0.05. Signal Stop Loss!
    # Day 4 Open: 90. Fill Sell at 90. Cash = 90000. Day 4 Close: 90. Rebalance Buy -> Signal Buy.
    # Day 5 Open: 85. Fill Buy at 85 (target 90000 / 85 => 1050 shares, max cash = 90000, actual buy = 1050). Cash = 90000 - 85*1050 = 750.
    
    sell_orders = [o for o in broker.order_book if o.direction == OrderDirection.SELL]
    assert len(sell_orders) >= 1
    
    # First sell order is the stop loss
    sl_order = sell_orders[0]
    assert sl_order.order_type == OrderType.MARKET
    assert sl_order.status == OrderStatus.FILLED
    
    # Verify exact cash on Day 4 after sell.
    # We can check the equity curve.
    assert df_equity.iloc[3]['equity'] == 90000.0 # Day 4 equity
    assert df_equity.iloc[4]['equity'] == 90000.0 # Day 5 equity (cash 750 + 1050*85 = 90000)

def test_weekly_rebalance_should_not_mask_stop_loss():
    """
    Test Case 2: test_weekly_rebalance_should_not_mask_stop_loss
    Expected: In weekly mode, a mid-week stop-loss trigger immediately exits the position on the next bar without waiting for the rebalance day. The weekend rebalance must proceed with the updated holdings.
    """
    df = pd.read_csv('/root/projects/AMS/tests/fixtures/fixture_stop_loss_immediate_effect.csv')
    data_feed = DummyDataFeed(df)
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    strategy = CBRotationStrategy(
        top_n=1, 
        weight_per_position=1.0, 
        stop_loss_threshold=-0.05, 
        rebalance_period='weekly',
        take_profit_threshold=None,
        liquidity_threshold=0
    )
    runner = BacktestRunner(data_feed, broker, strategy)
    dates = pd.Series(pd.to_datetime(df['date'].unique())).sort_values()
    df_equity = runner.run(dates.iloc[0], dates.iloc[-1])
    
    # Day 1 (Monday): Rebalance Buy.
    # Day 2 (Tuesday) Open: Fill Buy at 100.
    # Day 3 (Wednesday) Close: 94. Signal Stop Loss.
    # Day 4 (Thursday) Open: 90. Fill Sell at 90. Cash = 90000. Day 4 Close: 90. Mid-week, no rebalance buy!
    # Day 5 (Friday) Open: 85. Day 5 Close: 85. Rebalance Buy! (Friday is rebalance day).
    
    # The stop loss should have been filled on Thursday!
    sell_orders = [o for o in broker.order_book if o.direction == OrderDirection.SELL and o.status == OrderStatus.FILLED]
    assert len(sell_orders) == 1
    
    # Check that Thursday equity is exactly cash 90000
    assert df_equity.iloc[3]['equity'] == 90000.0

def test_daily_stop_loss_threshold_changes_affect_outcome():
    """
    Test Case 3: test_daily_stop_loss_threshold_changes_affect_outcome
    Expected: A tight stop-loss like -1% and a wide stop-loss like -5% must yield different trade paths and results on the same deterministic fixture.
    """
    df = pd.read_csv('/root/projects/AMS/tests/fixtures/fixture_stop_loss_thresholds.csv')
    
    # Run tight SL (-0.01)
    tight_feed = DummyDataFeed(df)
    tight_broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    tight_strategy = CBRotationStrategy(
        top_n=1, weight_per_position=1.0, stop_loss_threshold=-0.01, 
        rebalance_period='daily', take_profit_threshold=None, liquidity_threshold=0
    )
    tight_runner = BacktestRunner(tight_feed, tight_broker, tight_strategy)
    tight_eq_curve = tight_runner.run(pd.to_datetime(df['date'].min()), pd.to_datetime(df['date'].max()))
    
    # Run wide SL (-0.05)
    wide_feed = DummyDataFeed(df)
    wide_broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    wide_strategy = CBRotationStrategy(
        top_n=1, weight_per_position=1.0, stop_loss_threshold=-0.05, 
        rebalance_period='daily', take_profit_threshold=None, liquidity_threshold=0
    )
    wide_runner = BacktestRunner(wide_feed, wide_broker, wide_strategy)
    wide_eq_curve = wide_runner.run(pd.to_datetime(df['date'].min()), pd.to_datetime(df['date'].max()))
    
    # For Tight SL (-0.01): Day 3 close is 98 (-0.02). Triggers SL. Sells at Day 4 Open (94).
    # For Wide SL (-0.05): Day 3 close is 98 (-0.02, no trigger). Day 4 close is 94 (-0.0408, no trigger). Day 5 close is 90 (-0.0425). No trigger!
    
    tight_final = tight_eq_curve.iloc[-1]['equity']
    wide_final = wide_eq_curve.iloc[-1]['equity']
    
    assert tight_final != wide_final
    # Exact assertions:
    # Tight: Sell at 94 (Day 4 open). Rebuys at Day 4 close (94).
    # Wide: Never triggers SL. Holds until end.
    # Let's just assert they are different as requested.

