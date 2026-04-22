import pytest
import pandas as pd
from decimal import Decimal
from ams.core.history_datafeed import HistoryDataFeed
from ams.core.sim_broker import SimBroker
from ams.runners.backtest_runner import BacktestRunner
from ams.core.cb_rotation_strategy import CBRotationStrategy
from ams.models.config import TakeProfitConfig, TakeProfitMode
from ams.core.order import Order, OrderDirection, OrderType, OrderStatus
import main_runner
from unittest.mock import patch

def test_tp_limit_order_triggers_on_next_bar_high():
    # Scenario: TP LIMIT SELL submitted on Day 1 is FILLED on Day 2 if Day 2 High >= Limit Price
    data_path = "/root/projects/AMS/tests/fixtures/fixture_tp_trigger.csv"
    data_feed = HistoryDataFeed(file_path=data_path)
    
    broker = SimBroker(initial_cash=100000.0, slippage=0.0) 
    
    # Pre-populate with position on Day 1 by submitting a BUY order before the run
    # This BUY order will match on Day 1 (2026-01-01)
    broker.submit_order(Order(
        ticker="TEST01",
        direction=OrderDirection.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        limit_price=100.0
    ))
    
    tp_config = TakeProfitConfig(mode=TakeProfitMode.POSITION, pos_threshold=Decimal('0.05'))
    strategy = CBRotationStrategy(
        top_n=1, 
        tp_mode='position', 
        tp_config=tp_config,
        rebalance_period='daily',
        liquidity_threshold=0
    )
    
    runner = BacktestRunner(data_feed, broker, strategy)
    
    # Run from Day 1 to Day 2
    runner.run("2026-01-01", "2026-01-02")
    
    # Day 1 (2026-01-01): 
    # 1. match_orders matches the pre-submitted BUY order at 100.0. avg_price = 100.0.
    # 2. generate_target_portfolio sees position, creates TP order at 105.0, effective_date='2026-01-01'.
    
    # Day 2 (2026-01-02):
    # 1. match_orders sees TP order. Day 2 High is 110.0 >= 105.0. Matches! status -> FILLED.
    # 2. _expire_old_orders runs, but order is already FILLED.
    
    found_tp_order = False
    for order in broker.order_book:
        if order.direction == OrderDirection.SELL and getattr(order, 'limit_price', None) == 105.0:
            found_tp_order = True
            assert order.status == OrderStatus.FILLED, f"TP order should be FILLED, but got {order.status}"
    
    assert found_tp_order, "TP order for 105.0 should have been created on Day 1"
    assert "TEST01" not in broker.holdings, "TEST01 should have been sold by TP"

def test_tp_limit_order_expires_only_after_valid_match_window():
    # Scenario: TP LIMIT SELL submitted on Day 1 remains PENDING during Day 2 matching if price is not hit, 
    # and is CANCELED only AFTER Day 2 matching window closes
    data_path = "/root/projects/AMS/tests/fixtures/fixture_tp_no_trigger.csv"
    data_feed = HistoryDataFeed(file_path=data_path)
    
    broker = SimBroker(initial_cash=100000.0, slippage=0.0)
    
    # Pre-populate with position on Day 1
    broker.submit_order(Order(
        ticker="TEST01",
        direction=OrderDirection.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        limit_price=100.0
    ))
    
    tp_config = TakeProfitConfig(mode=TakeProfitMode.POSITION, pos_threshold=Decimal('0.05'))
    strategy = CBRotationStrategy(
        top_n=1,
        tp_mode='position',
        tp_config=tp_config,
        rebalance_period='daily',
        liquidity_threshold=0
    )
    
    runner = BacktestRunner(data_feed, broker, strategy)
    
    runner.run("2026-01-01", "2026-01-02")
    
    # Day 1: BUY filled. TP created for 105.0, effective_date='2026-01-01'.
    # Day 2: match_orders. High 104.0 < 105.0. No match.
    # Day 2: _expire_old_orders runs. Day 1 < Day 2. TP order CANCELED.
    
    found_tp_order_day1 = False
    for order in broker.order_book:
        if order.direction == OrderDirection.SELL and getattr(order, 'limit_price', None) == 105.0:
            if order.effective_date == "2026-01-01":
                found_tp_order_day1 = True
                assert order.status == OrderStatus.CANCELED, f"Day 1 TP order should be CANCELED after Day 2 matching, but got {order.status}"
            
    assert found_tp_order_day1, "TP order for 105.0 should have been created on Day 1"
    assert "TEST01" in broker.holdings, "TEST01 should still be held as TP didn't trigger"

def test_tp_mode_both_validation():
    # Scenario: main_runner.py exits with error if tp-mode=both but tp-pos or tp-intra is missing
    test_args = ["main_runner.py", "--strategy", "cb_rotation", "--start-date", "2026-01-01", 
                 "--end-date", "2026-01-02", "--capital", "4000000", "--top-n", "20", 
                 "--rebalance", "daily", "--tp-mode", "both", "--sl", "-0.08"]
    
    with patch("sys.argv", test_args):
        with pytest.raises(ValueError) as exc:
            main_runner.main()
        assert "ERROR: --tp-mode 'both' requires both --tp-pos and --tp-intra to be set." in str(exc.value)
