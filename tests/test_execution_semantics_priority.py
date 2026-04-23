import pytest
import os
import pandas as pd
from decimal import Decimal
from ams.core.history_datafeed import HistoryDataFeed
from ams.core.sim_broker import SimBroker
from ams.core.cb_rotation_strategy import CBRotationStrategy
from ams.runners.backtest_runner import BacktestRunner
from ams.models.config import TakeProfitConfig, TakeProfitMode
from ams.core.order import OrderStatus, OrderType

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "fixture_priority_conflicts.csv")

def setup_runner(rebalance='daily', tp_pos=0.05, sl=-0.05):
    tp_config = TakeProfitConfig(mode=TakeProfitMode.POSITION, pos_threshold=Decimal(str(tp_pos)), intra_threshold=Decimal(str(tp_pos)))
    strategy = CBRotationStrategy(top_n=2, weight_per_position=0.5, rebalance_period=rebalance, stop_loss_threshold=sl, tp_mode='position', tp_config=tp_config)
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    data_feed = HistoryDataFeed(file_path=FIXTURE_PATH)
    return BacktestRunner(data_feed, broker, strategy)

def test_tp_and_stop_loss_same_bar_priority():
    runner = setup_runner(sl=-0.08)
    # Day 1: Buys BOND1 and BOND2.
    # Day 2: BOND2 drops 10% (daily_return = -0.10). BOND1 goes up 8%.
    runner.run('2026-03-02', '2026-03-03')
    
    # On Day 2 end, BOND2 should trigger STOP_LOSS.
    # We expect a MARKET SELL order for BOND2, and NO LIMIT SELL for BOND2.
    sl_orders = 0
    tp_orders = 0
    for o in runner.broker.order_book:
        if o.ticker == 'BOND2' and o.direction.value == 'SELL' and o.effective_date == '2026-03-03':
            if o.order_type == OrderType.MARKET:
                sl_orders += 1
            if o.order_type == OrderType.LIMIT:
                tp_orders += 1
    
    assert sl_orders == 1, "Expected 1 MARKET SELL order for BOND2 due to STOP_LOSS"
    assert tp_orders == 0, "Expected NO LIMIT SELL order for BOND2"

def test_tp_and_rebalance_do_not_double_sell_position():
    # Day 1: Buys BOND1 and BOND2 (50% each).
    # Day 2: Rebalance triggered.
    # Let's say BOND1 goes up heavily, so its weight becomes > 50% + 0.5%.
    # This generates a REBALANCE sell intent.
    # BUT it's in target_portfolio, so it generates a TAKE_PROFIT intent!
    runner = setup_runner(rebalance='daily', tp_pos=0.01)
    runner.run('2026-03-02', '2026-03-03')
    
    # On Day 2 end, BOND1 should have BOTH Rebalance Sell AND Take-Profit intent.
    # Arbitration must choose TP (LIMIT) over Rebalance (MARKET).
    # Wait, let's verify only 1 sell order exists for BOND1 on Day 2.
    sell_orders = 0
    limit_sells = 0
    market_sells = 0
    for o in runner.broker.order_book:
        if o.ticker == 'BOND1' and o.direction.value == 'SELL' and o.effective_date == '2026-03-03':
            sell_orders += 1
            if o.order_type == OrderType.LIMIT:
                limit_sells += 1
            if o.order_type == OrderType.MARKET:
                market_sells += 1
                
    assert sell_orders == 1, "Expected EXACTLY 1 sell order for BOND1 to prevent double sell"
    assert limit_sells == 1, "Expected TP (LIMIT) to take priority over REBALANCE (MARKET)"
    assert market_sells == 0, "Expected REBALANCE (MARKET) to be ignored"

