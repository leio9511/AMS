import abc
import math
from decimal import Decimal

class BaseStrategy(abc.ABC):
    @abc.abstractmethod
    def on_bar(self, context, data):
        pass

    @abc.abstractmethod
    def generate_target_portfolio(self, context, data):
        pass

    def order_target_percent(self, broker, ticker, target_percent, current_price, current_equity, current_shares):
        """
        Helper function to automatically calculate the required shares and generate an `Order` object
        to call `broker.submit_order(order)`. Returns the created order object or None.
        """
        if current_price is None or current_price <= 0:
            return None

        # Importing here to avoid circular imports if any
        from ams.core.order import Order, OrderDirection, OrderType

        d_price = Decimal(str(current_price))
        d_percent = Decimal(str(target_percent))
        d_equity = Decimal(str(current_equity))
        
        target_value = d_equity * d_percent
        current_value = Decimal(str(current_shares)) * d_price
        
        diff_value = target_value - current_value
        
        slippage = Decimal(str(getattr(broker, 'slippage', 0.0)))
        
        if diff_value > 0: # Buy
            f_price = float(d_price)
            f_diff = float(diff_value)
            # Lots of 10 shares
            target_shares_to_buy = math.floor(f_diff / f_price / 10) * 10
            
            # Check cash limits
            cost_per_share = d_price * (Decimal('1') + slippage)
            f_cost_per_share = float(cost_per_share)
            f_cash = broker.cash
            max_shares_cash = math.floor(f_cash / f_cost_per_share / 10) * 10
            
            actual_bought_shares = min(target_shares_to_buy, max_shares_cash)
            
            if actual_bought_shares > 0:
                order = Order(
                    ticker=ticker,
                    direction=OrderDirection.BUY,
                    quantity=actual_bought_shares,
                    order_type=OrderType.MARKET,
                    limit_price=float(d_price)
                )
                broker.submit_order(order)
                return order
                
        elif diff_value < 0: # Sell
            f_price = float(d_price)
            f_diff = float(diff_value)
            target_shares_to_sell = math.ceil(abs(f_diff) / f_price)
            actual_sold_shares = min(target_shares_to_sell, current_shares)
            
            if actual_sold_shares > 0:
                order = Order(
                    ticker=ticker,
                    direction=OrderDirection.SELL,
                    quantity=actual_sold_shares,
                    order_type=OrderType.MARKET,
                    limit_price=float(d_price)
                )
                broker.submit_order(order)
                return order
        
        return None

class BaseDataFeed(abc.ABC):
    @abc.abstractmethod
    def get_data(self, tickers, date):
        pass

class BaseBroker(abc.ABC):
    @abc.abstractmethod
    def order_target_percent(self, ticker, percent):
        pass

    @abc.abstractmethod
    def cancel_order(self, order_id):
        pass
