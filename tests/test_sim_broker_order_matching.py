import pytest
from ams.core.sim_broker import SimBroker
from ams.core.order import Order, OrderType, Direction, OrderStatus
from ams.core.slippage import ExtremeRiskSlippageModel

def test_sim_broker_limit_order_matching():
    broker = SimBroker(initial_cash=100000.0)
    broker.holdings['A'] = 100
    
    order = Order(
        ticker='A',
        direction=Direction.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=110.0
    )
    
    broker.submit_order(order)
    assert len(broker.active_orders) == 1
    
    bar_data = {'A': {'high': 112.0, 'close': 105.0}}
    broker.match_orders(bar_data)
    
    assert order.status == OrderStatus.FILLED
    assert len(broker.active_orders) == 0
    # Expected cash: 100000.0 + 100 * 110.0 = 111000.0
    assert broker.cash == 111000.0
    assert broker.holdings['A'] == 0

def test_sim_broker_slippage_injection():
    slippage_model = ExtremeRiskSlippageModel(deduction_percentage=0.50)
    broker = SimBroker(initial_cash=100000.0, slippage_model=slippage_model)
    broker.holdings['B'] = 100
    
    order = Order(
        ticker='B',
        direction=Direction.SELL,
        quantity=100,
        order_type=OrderType.MARKET
    )
    
    broker.submit_order(order)
    
    bar_data = {'B': {'high': 10.0, 'close': 10.0}}
    broker.match_orders(bar_data)
    
    assert order.status == OrderStatus.FILLED
    # Penalty is 50%, so execution_price = 10.0 * 0.50 = 5.0
    # Cash added: 100 * 5.0 = 500.0
    assert broker.cash == 100500.0
    assert broker.holdings['B'] == 0
