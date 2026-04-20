import pytest
import pandas as pd
import numpy as np
from ams.core.cb_rotation_strategy import CBRotationStrategy

def test_generate_target_portfolio_success():
    strategy = CBRotationStrategy()
    
    # Generate mock dataframe with 50 bonds
    data = []
    for i in range(1, 51):
        data.append({
            'ticker': f'CB{i}',
            'close_price': 100 + i, # 101 to 150
            'premium_rate': i / 100.0, # 0.01 to 0.50
            'volume': 10000,
            'amount': 15000000, # > 10M
            'is_st': False,
            'suspended': False
        })
    df = pd.DataFrame(data)
    
    # Expected: double low = close_price + premium_rate * 100
    # CB1: 101 + 1 = 102
    # CB2: 102 + 2 = 104
    # ...
    # So the top 20 will be CB1 to CB20
    
    target = strategy.generate_target_portfolio(None, df)
    
    assert len(target) == 20
    assert 'CB1' in target
    assert 'CB20' in target
    assert 'CB21' not in target
    assert target['CB1'] == 0.05
    assert target['CB20'] == 0.05

def test_liquidity_threshold_filtering():
    strategy = CBRotationStrategy()
    df = pd.DataFrame([
        {'ticker': 'CB1', 'close_price': 100, 'premium_rate': 0.1, 'amount': 5000000}, # Excluded (<10M)
        {'ticker': 'CB2', 'close_price': 105, 'premium_rate': 0.1, 'amount': 15000000}, # Included
        {'ticker': 'CB3', 'close_price': 110, 'premium_rate': 0.1, 'amount': 20000000}, # Included
    ])
    
    target = strategy.generate_target_portfolio(None, df)
    assert 'CB1' not in target
    assert 'CB2' in target
    assert 'CB3' in target

def test_missing_and_suspended_data_filtering():
    strategy = CBRotationStrategy()
    df = pd.DataFrame([
        {'ticker': 'CB1', 'close_price': 100, 'premium_rate': 0.1, 'amount': 15000000, 'volume': 0}, # Suspended (0 volume)
        {'ticker': 'CB2', 'close_price': np.nan, 'premium_rate': 0.1, 'amount': 15000000, 'volume': 1000}, # Missing price
        {'ticker': 'CB3', 'close_price': 110, 'premium_rate': np.nan, 'amount': 15000000, 'volume': 1000}, # Missing premium
        {'ticker': 'CB4', 'close_price': 120, 'premium_rate': 0.1, 'amount': 15000000, 'volume': 1000}, # Valid
    ])
    
    target = strategy.generate_target_portfolio(None, df)
    assert 'CB1' not in target
    assert 'CB2' not in target
    assert 'CB3' not in target
    assert 'CB4' in target

from ams.core.sim_broker import SimBroker
from ams.core.order import OrderType, OrderDirection

def test_take_profit_limit_order_generation():
    strategy = CBRotationStrategy(top_n=1, take_profit_threshold=0.1)
    broker = SimBroker(initial_cash=100000.0)
    
    # Initialize some holdings so that SSoT position has quantity for the TP order
    from decimal import Decimal
    broker.holdings['CB1'] = 20
    broker.avg_prices['CB1'] = Decimal('100.0')
    broker._cash = Decimal('98000.0')
    broker.update_equity({'CB1': 100.0})
    
    class Context:
        def __init__(self):
            self.broker = broker
            self.current_date = pd.Timestamp('2024-01-01')
            self.holdings = ['CB1']
            self.current_prices = {'CB1': 100.0}
            
    context = Context()
    
    df = pd.DataFrame([{
        'ticker': 'CB1', 'close_price': 100.0, 'premium_rate': 0.1,
        'volume': 10000, 'amount': 15000000, 'is_st': False, 'suspended': False
    }])
    
    strategy.generate_target_portfolio(context, df)
    
    # We expect 2 orders: 1 Market BUY (to reach target weight of 5%, ~50 shares, 50-20=30), 1 Limit SELL (for the 20 held shares)
    assert len(broker.order_book) == 2
    
    buy_order = broker.order_book[0]
    sell_order = broker.order_book[1]
    
    assert buy_order.direction == OrderDirection.BUY
    assert buy_order.order_type == OrderType.MARKET
    assert buy_order.ticker == 'CB1'
    assert buy_order.quantity == 30
    
    assert sell_order.direction == OrderDirection.SELL
    assert sell_order.order_type == OrderType.LIMIT
    import math
    assert math.isclose(sell_order.limit_price, 110.0) # 100 * 1.1
    assert sell_order.quantity == 20 # SSoT quantity

def test_weekly_rebalance_sleep():
    strategy = CBRotationStrategy(top_n=1, rebalance_period='weekly', reinvest_on_risk_exit=False)
    broker = SimBroker(initial_cash=100000.0)
    
    class Context:
        def __init__(self):
            self.broker = broker
            self.current_date = pd.Timestamp('2024-01-05') # Friday
            self.holdings = []
            self.current_prices = {'CB1': 100.0, 'CB2': 100.0}
            self.daily_return = {}
            
    context = Context()
    
    df_friday = pd.DataFrame([{
        'ticker': 'CB1', 'close_price': 100.0, 'premium_rate': 0.1,
        'volume': 10000, 'amount': 15000000, 'is_st': False, 'suspended': False
    }])
    
    # Friday: Rebalance day, it should buy CB1
    strategy.generate_target_portfolio(context, df_friday)
    assert len(broker.order_book) == 1
    assert broker.order_book[0].direction == OrderDirection.BUY
    assert broker.order_book[0].ticker == 'CB1'
    
    # Simulate execution
    broker.order_book[0].status = 'FILLED' # Not real enum but won't trigger match_orders anyway
    broker.holdings['CB1'] = 50 # Mock holding
    broker._cash = 50000.0
    
    # Monday: CB1 hits stop loss
    broker.order_book.clear()
    context.current_date = pd.Timestamp('2024-01-08') # Monday
    context.holdings = ['CB1']
    context.daily_return = {'CB1': 100.0} # Prev close
    
    df_monday = pd.DataFrame([
        {'ticker': 'CB1', 'close_price': 90.0, 'premium_rate': 0.1, 'volume': 10000, 'amount': 15000000, 'is_st': False, 'suspended': False},
        {'ticker': 'CB2', 'close_price': 100.0, 'premium_rate': 0.1, 'volume': 10000, 'amount': 15000000, 'is_st': False, 'suspended': False}
    ])
    
    context.current_prices = {'CB1': 90.0, 'CB2': 100.0}
    
    # Monday generation
    strategy.generate_target_portfolio(context, df_monday)
    
    # It should emit a sell order for CB1 because it's stopped out!
    # And because it's weekly and reinvest_on_risk_exit=False, it should NOT buy CB2!
    assert len(broker.order_book) == 1
    assert broker.order_book[0].direction == OrderDirection.SELL
    assert broker.order_book[0].ticker == 'CB1'

from ams.core.cb_rotation_strategy import TP_MODE_POSITION, TP_MODE_INTRADAY, TP_MODE_BOTH

def test_strategy_uses_broker_ssot_cost():
    strategy = CBRotationStrategy(top_n=1, take_profit_threshold=0.1, tp_mode=TP_MODE_POSITION)
    broker = SimBroker(initial_cash=100000.0)
    
    # Mock get_position to return an avg_price of 90.0
    def mock_get_position(ticker):
        return {'avg_price': 90.0, 'quantity': 100}
    broker.get_position = mock_get_position
    
    class Context:
        def __init__(self):
            self.broker = broker
            self.current_date = pd.Timestamp('2024-01-01')
            self.holdings = ['CB1']
            self.current_prices = {'CB1': 100.0}
            
    context = Context()
    broker.holdings['CB1'] = 100
    broker._cash = 0
    broker.update_equity({'CB1': 100.0})
    strategy.weight_per_position = 1.0
    
    df = pd.DataFrame([{
        'ticker': 'CB1', 'close_price': 100.0, 'premium_rate': 0.1,
        'volume': 10000, 'amount': 15000000, 'is_st': False, 'suspended': False
    }])
    
    strategy.generate_target_portfolio(context, df)
    
    # We expect 1 Limit SELL order for TP because we already hold it
    # Note: no buy order since weight is already near target
    assert len(broker.order_book) == 1
    
    sell_order = broker.order_book[0]
    assert sell_order.direction == OrderDirection.SELL
    assert sell_order.order_type == OrderType.LIMIT
    import math
    assert math.isclose(sell_order.limit_price, 99.0) # 90.0 * 1.1 = 99.0

def test_dual_mode_tp_min_logic():
    strategy = CBRotationStrategy(top_n=1, take_profit_threshold=0.1, tp_mode=TP_MODE_BOTH)
    broker = SimBroker(initial_cash=100000.0)
    
    # avg_price = 110.0 (cost_tp = 121.0), intraday_price = 100.0 (intraday_tp = 110.0)
    # min should be 110.0
    def mock_get_position(ticker):
        return {'avg_price': 110.0, 'quantity': 100}
    broker.get_position = mock_get_position
    
    class Context:
        def __init__(self):
            self.broker = broker
            self.current_date = pd.Timestamp('2024-01-01')
            self.holdings = ['CB1']
            self.current_prices = {'CB1': 100.0}
            
    context = Context()
    broker.holdings['CB1'] = 100
    broker._cash = 0
    broker.update_equity({'CB1': 100.0})
    strategy.weight_per_position = 1.0
    
    df = pd.DataFrame([{
        'ticker': 'CB1', 'close_price': 100.0, 'premium_rate': 0.1,
        'volume': 10000, 'amount': 15000000, 'is_st': False, 'suspended': False
    }])
    
    strategy.generate_target_portfolio(context, df)
    
    assert len(broker.order_book) == 1
    sell_order = broker.order_book[0]
    import math
    assert math.isclose(sell_order.limit_price, 110.0) # min(121.0, 110.0)
