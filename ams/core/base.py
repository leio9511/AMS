import abc
import math
from decimal import Decimal
from ams.core.order import Order, OrderType, Direction

class BaseStrategy(abc.ABC):
    @abc.abstractmethod
    def on_bar(self, context, data):
        pass

    @abc.abstractmethod
    def generate_target_portfolio(self, context, data):
        pass

    def order_target_percent(self, ticker, target_pct, current_price, broker, take_profit_threshold=None):
        if current_price is None or current_price <= 0:
            return

        total_equity = broker.total_equity
        d_price = Decimal(str(current_price))
        d_percent = Decimal(str(target_pct))
        
        target_value = Decimal(str(total_equity)) * d_percent
        current_shares = broker.holdings.get(ticker, 0)
        current_value = Decimal(str(current_shares)) * d_price
        
        diff_value = target_value - current_value
        
        # calculate shares to buy/sell
        if diff_value > 0: # Buy
            target_shares_to_buy = math.floor(float(diff_value) / float(d_price) / 10) * 10
            
            # Check cash limits (approximate with slippage)
            cost_per_share = d_price * (Decimal('1') + broker.slippage)
            max_shares_cash = math.floor(float(broker.cash) / float(cost_per_share) / 10) * 10
            
            actual_bought_shares = min(target_shares_to_buy, max_shares_cash)
            if actual_bought_shares > 0:
                buy_order = Order(
                    ticker=ticker,
                    direction=Direction.BUY,
                    quantity=actual_bought_shares,
                    order_type=OrderType.MARKET
                )
                broker.submit_order(buy_order)
                if take_profit_threshold is not None:
                    limit_price = float(d_price * Decimal(str(1 + take_profit_threshold)))
                    sell_order = Order(
                        ticker=ticker,
                        direction=Direction.SELL,
                        quantity=actual_bought_shares,
                        order_type=OrderType.LIMIT,
                        limit_price=limit_price
                    )
                    broker.submit_order(sell_order)

        elif diff_value < 0: # Sell
            target_shares_to_sell = math.ceil(abs(float(diff_value)) / float(d_price))
            actual_sold_shares = min(target_shares_to_sell, current_shares)
            if actual_sold_shares > 0:
                sell_order = Order(
                    ticker=ticker,
                    direction=Direction.SELL,
                    quantity=actual_sold_shares,
                    order_type=OrderType.MARKET
                )
                broker.submit_order(sell_order)

class BaseDataFeed(abc.ABC):
    @abc.abstractmethod
    def get_data(self, tickers, date):
        pass

class BaseBroker(abc.ABC):
    @abc.abstractmethod
    def order_target_percent(self, ticker, percent):
        pass
