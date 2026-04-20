import pytest
import random
from decimal import Decimal, ROUND_HALF_UP
from ams.core.sim_broker import SimBroker
from ams.core.order import Order, OrderDirection, OrderType, OrderStatus

def test_broker_precision_no_drift_100_trades():
    broker = SimBroker(initial_cash=10000000.0, slippage=0.0) # no slippage to test pure drift
    
    ticker = "000001.SZ"
    
    expected_cash = Decimal('10000000.00')
    expected_holdings_qty = Decimal('0')
    expected_avg_price = Decimal('0.00')
    
    # Track manually
    
    for i in range(120):
        # We will do random buys and sells with fractional prices
        is_buy = random.choice([True, False])
        
        # We only sell if we have holdings
        if expected_holdings_qty == 0:
            is_buy = True
            
        qty = random.randint(100, 1000)
        # Generate fractional price
        price = round(random.uniform(10.0, 150.0), 3) 
        
        if is_buy:
            cost = (Decimal(str(qty)) * Decimal(str(price))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if expected_cash >= cost:
                # Execute buy manually
                new_qty = expected_holdings_qty + Decimal(str(qty))
                new_avg = (expected_holdings_qty * expected_avg_price + Decimal(str(qty)) * Decimal(str(price))) / new_qty
                
                expected_cash -= cost
                expected_holdings_qty = new_qty
                expected_avg_price = new_avg
                
                # Execute via broker
                order = Order(
                    ticker=ticker,
                    direction=OrderDirection.BUY,
                    quantity=qty,
                    order_type=OrderType.MARKET,
                    limit_price=price # limit price ignored in MARKET
                )
                broker.submit_order(order)
                # match market order, the price needs to be in close
                broker.match_orders({ticker: {'close': price}})
        else:
            # Sell
            sell_qty = min(qty, int(expected_holdings_qty))
            if sell_qty > 0:
                proceeds = (Decimal(str(sell_qty)) * Decimal(str(price))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                
                expected_cash += proceeds
                expected_holdings_qty -= sell_qty
                if expected_holdings_qty == 0:
                    expected_avg_price = Decimal('0.00')
                    
                # Execute via broker
                order = Order(
                    ticker=ticker,
                    direction=OrderDirection.SELL,
                    quantity=sell_qty,
                    order_type=OrderType.MARKET,
                    limit_price=price
                )
                broker.submit_order(order)
                broker.match_orders({ticker: {'close': price}})
                
        # Update equity
        broker.update_equity({ticker: price})
        
        # Verify drift
        assert Decimal(str(broker.cash)) == expected_cash
        
        position = broker.get_position(ticker)
        assert position['quantity'] == int(expected_holdings_qty)
        
        # Decimal precision check on avg_price
        # since avg_price is internal it's a string or Decimal
        if expected_holdings_qty > 0:
            assert position['avg_price'] == expected_avg_price
            
        # Equity check
        holdings_value = (expected_holdings_qty * Decimal(str(price)))
        expected_equity = (expected_cash + holdings_value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        assert Decimal(str(broker.total_equity)) == expected_equity

