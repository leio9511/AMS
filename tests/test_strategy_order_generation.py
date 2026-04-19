import pytest
import pandas as pd
from datetime import datetime
from decimal import Decimal
from ams.core.cb_rotation_strategy import CBRotationStrategy
from ams.core.sim_broker import SimBroker
from ams.core.order import OrderType, Direction

class MockContext:
    def __init__(self, broker, current_prices, date_str):
        self.broker = broker
        self.current_prices = current_prices
        self.date = pd.to_datetime(date_str)
        self.holdings = list(broker.holdings.keys())
        self.daily_return = {}

def test_order_target_percent_conversion():
    broker = SimBroker(initial_cash=10000.0)
    strategy = CBRotationStrategy(top_n=1, weight_per_position=0.5)
    
    df = pd.DataFrame([
        {'ticker': 'CB1', 'close_price': 100, 'premium_rate': 0.1, 'amount': 15000000, 'volume': 1000, 'is_st': False, 'is_redeemed': False, 'suspended': False}
    ])
    
    context = MockContext(broker, {'CB1': 100.0}, '2025-01-03') # Friday
    target = strategy.generate_target_portfolio(context, df)
    
    # Check if an order was submitted to broker's active orders
    assert len(broker.active_orders) == 1
    order = broker.active_orders[0]
    
    assert order.ticker == 'CB1'
    assert order.direction == Direction.BUY
    assert order.order_type == OrderType.MARKET
    # 0.5 * 10000 = 5000 target value. Price is 100. Shares to buy = 50. Floor to multiple of 10 -> 50
    assert order.quantity == 50

def test_take_profit_limit_order_emission():
    broker = SimBroker(initial_cash=10000.0)
    strategy = CBRotationStrategy(top_n=1, weight_per_position=0.5, take_profit_threshold=0.1)
    
    df = pd.DataFrame([
        {'ticker': 'CB1', 'close_price': 100, 'premium_rate': 0.1, 'amount': 15000000, 'volume': 1000, 'is_st': False, 'is_redeemed': False, 'suspended': False}
    ])
    
    context = MockContext(broker, {'CB1': 100.0}, '2025-01-03') # Friday
    target = strategy.generate_target_portfolio(context, df)
    
    assert len(broker.active_orders) == 2
    buy_order = broker.active_orders[0]
    sell_order = broker.active_orders[1]
    
    assert buy_order.direction == Direction.BUY
    assert sell_order.direction == Direction.SELL
    assert sell_order.order_type == OrderType.LIMIT
    assert sell_order.limit_price == 110.0 # 100 * (1 + 0.1)

def test_weekly_rebalance_sleep():
    broker = SimBroker(initial_cash=10000.0)
    strategy = CBRotationStrategy(top_n=1, weight_per_position=0.5, rebalance_period='weekly', reinvest_on_risk_exit=False)
    
    df = pd.DataFrame([
        {'ticker': 'CB1', 'close_price': 100, 'premium_rate': 0.1, 'amount': 15000000, 'volume': 1000, 'is_st': False, 'is_redeemed': False, 'suspended': False}
    ])
    
    # Wednesday
    context = MockContext(broker, {'CB1': 100.0}, '2025-01-01') 
    
    # Assert no orders generated since it's Wednesday and we shouldn't reinvest
    target = strategy.generate_target_portfolio(context, df)
    assert len(broker.active_orders) == 0

    # But on Friday it should
    context = MockContext(broker, {'CB1': 100.0}, '2025-01-03')
    target = strategy.generate_target_portfolio(context, df)
    assert len(broker.active_orders) == 1

