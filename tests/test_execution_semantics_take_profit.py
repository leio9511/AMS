import pytest
import os
import pandas as pd
from decimal import Decimal
from ams.core.history_datafeed import HistoryDataFeed
from ams.core.sim_broker import SimBroker
from ams.core.cb_rotation_strategy import CBRotationStrategy
from ams.runners.backtest_runner import BacktestRunner
from ams.models.config import TakeProfitConfig, TakeProfitMode
from ams.core.order import OrderStatus

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "fixture_take_profit_lifecycle.csv")

def setup_runner(rebalance, tp_pos, capital=100000.0, top_n=1):
    tp_config = TakeProfitConfig(mode=TakeProfitMode.POSITION, pos_threshold=Decimal(str(tp_pos)), intra_threshold=Decimal(str(tp_pos)))
    strategy = CBRotationStrategy(top_n=top_n, weight_per_position=1.0, rebalance_period=rebalance, stop_loss_threshold=-0.1, tp_mode='position', tp_config=tp_config)
    broker = SimBroker(initial_cash=capital, slippage=0.0)
    data_feed = HistoryDataFeed(file_path=FIXTURE_PATH)
    return BacktestRunner(data_feed, broker, strategy)

def test_tp_limit_order_triggers_on_next_bar_high():
    runner = setup_runner(rebalance='daily', tp_pos=0.05) # Day 1 close=102, TP price = 102*1.05 = 107.1
    # Day 2 high is 110. It should trigger.
    runner.run('2026-03-02', '2026-03-03')
    
    assert 'BOND1' not in runner.broker.holdings
    found_filled = False
    for o in runner.broker.order_book:
        if o.direction.value == "SELL" and o.status == OrderStatus.FILLED:
            found_filled = True
            assert float(o.limit_price) == 107.1
            assert o.quantity == 980
    assert found_filled
    
    # Expected Cash: 100000 - 980*102.0 + 980*107.1 = 100000 + 980*5.1 = 100000 + 4998 = 104998
    assert runner.broker.cash == 104998.0
    assert runner.broker.total_equity == 104998.0

def test_tp_limit_order_expires_only_after_valid_match_window():
    runner = setup_runner(rebalance='daily', tp_pos=0.10) # TP = 102*1.10 = 112.2
    # Day 2 high is 110. It should NOT trigger.
    runner.run('2026-03-02', '2026-03-03')
    
    found_expired = False
    for o in runner.broker.order_book:
        if o.direction.value == "SELL" and o.status == OrderStatus.CANCELED:
            found_expired = True
    assert found_expired
    assert 'BOND1' in runner.broker.holdings

def test_weekly_rebalance_does_not_mask_midweek_take_profit():
    # In weekly mode, TP should trigger mid-week (Day 2).
    runner = setup_runner(rebalance='weekly', tp_pos=0.05)
    runner.run('2026-03-02', '2026-03-06')
    
    # Check for TP fill (should be on Day 2)
    tp_filled = any(o.ticker == 'BOND1' and o.direction.value == 'SELL' and o.status == OrderStatus.FILLED for o in runner.broker.order_book)
    assert tp_filled
    
    # Check for Friday rebalance re-buy (should be PENDING on Friday end)
    # Friday (2026-03-06) rebalance should see BOND1 is missing and re-buy it.
    rebuy_pending = any(o.ticker == 'BOND1' and o.direction.value == 'BUY' and o.status == OrderStatus.PENDING for o in runner.broker.order_book)
    assert rebuy_pending
    
    # Ensure no double sell (holdings should be 0 filled, but we might have a pending buy)
    assert runner.broker.holdings.get('BOND1', 0) == 0

def test_daily_tp_threshold_changes_affect_outcome():
    r1 = setup_runner(rebalance='daily', tp_pos=0.05)
    df1 = r1.run('2026-03-02', '2026-03-06')
    r1_equity = df1['equity'].iloc[-1]
    
    r2 = setup_runner(rebalance='daily', tp_pos=0.20)
    df2 = r2.run('2026-03-02', '2026-03-06')
    r2_equity = df2['equity'].iloc[-1]
    
    assert r1_equity != r2_equity

def test_weekly_tp_threshold_changes_affect_outcome():
    r1 = setup_runner(rebalance='weekly', tp_pos=0.05)
    df1 = r1.run('2026-03-02', '2026-03-06')
    r1_equity = df1['equity'].iloc[-1]
    
    r2 = setup_runner(rebalance='weekly', tp_pos=0.20)
    df2 = r2.run('2026-03-02', '2026-03-06')
    r2_equity = df2['equity'].iloc[-1]
    
    assert r1_equity != r2_equity
