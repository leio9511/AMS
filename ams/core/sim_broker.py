import math
from decimal import Decimal, ROUND_HALF_UP
from ams.core.base import BaseBroker
from ams.core.order import Order, OrderStatus, OrderType, Direction
from ams.core.slippage import BaseSlippageModel

class SimBroker(BaseBroker):
    def __init__(self, initial_cash=4000000.0, slippage=0.001, slippage_model: BaseSlippageModel = None):
        self._cash = Decimal(str(initial_cash)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self._initial_cash = float(initial_cash)
        self.slippage = Decimal(str(slippage))
        self.holdings = {} # ticker -> int (shares)
        self._total_equity = self._cash
        self._last_prices = {} # Fallback prices for suspended symbols
        self.slippage_model = slippage_model
        self.active_orders = []

    @property
    def cash(self):
        return float(self._cash)

    @cash.setter
    def cash(self, value):
        self._cash = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def total_equity(self):
        return float(self._total_equity)

    @property
    def initial_cash(self):
        return self._initial_cash

    def update_equity(self, current_prices: dict):
        # Update last prices
        for t, p in current_prices.items():
            self._last_prices[t] = Decimal(str(p))

        holdings_value = Decimal('0.00')
        for t, shares in self.holdings.items():
            if t in current_prices:
                price = Decimal(str(current_prices[t]))
            elif t in self._last_prices:
                price = self._last_prices[t]
            else:
                price = Decimal('0.00')
                
            holdings_value += (Decimal(str(shares)) * price)

        self._total_equity = (self._cash + holdings_value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def order_target_percent(self, ticker, percent, price=None):
        if price is None or price <= 0:
            return

        d_price = Decimal(str(price))
        d_percent = Decimal(str(percent))
        
        target_value = self._total_equity * d_percent
        current_shares = self.holdings.get(ticker, 0)
        current_value = Decimal(str(current_shares)) * d_price
        
        diff_value = target_value - current_value
        
        if diff_value > 0: # Buy
            f_price = float(d_price)
            f_diff = float(diff_value)
            target_shares_to_buy = math.floor(f_diff / f_price / 10) * 10
            
            # Check cash limits
            cost_per_share = d_price * (Decimal('1') + self.slippage)
            f_cost_per_share = float(cost_per_share)
            f_cash = float(self._cash)
            max_shares_cash = math.floor(f_cash / f_cost_per_share / 10) * 10
            
            actual_bought_shares = min(target_shares_to_buy, max_shares_cash)
            
            if actual_bought_shares > 0:
                cost = (Decimal(str(actual_bought_shares)) * d_price * (Decimal('1') + self.slippage)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                self._cash -= cost
                self.holdings[ticker] = current_shares + actual_bought_shares
                
        elif diff_value < 0: # Sell
            f_price = float(d_price)
            f_diff = float(diff_value)
            target_shares_to_sell = math.ceil(abs(f_diff) / f_price)
            actual_sold_shares = min(target_shares_to_sell, current_shares)
            
            if actual_sold_shares > 0:
                proceeds = (Decimal(str(actual_sold_shares)) * d_price * (Decimal('1') - self.slippage)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                self._cash += proceeds
                self.holdings[ticker] = current_shares - actual_sold_shares

    def submit_order(self, order: Order):
        self.active_orders.append(order)

    def match_orders(self, bar_data: dict):
        remaining_orders = []
        for order in self.active_orders:
            if order.status != OrderStatus.PENDING:
                continue
                
            ticker_data = bar_data.get(order.ticker)
            if not ticker_data:
                remaining_orders.append(order)
                continue

            matched = False
            execution_price = None
            
            if order.order_type == OrderType.LIMIT and order.direction == Direction.SELL:
                if 'high' in ticker_data and ticker_data['high'] >= order.limit_price:
                    execution_price = order.limit_price
                    matched = True
            elif order.order_type == OrderType.MARKET:
                if self.slippage_model:
                    execution_price = self.slippage_model.calculate_execution_price(order, ticker_data)
                else:
                    execution_price = ticker_data.get('close')
                matched = True

            if matched and execution_price is not None:
                if order.direction == Direction.SELL:
                    proceeds = (Decimal(str(order.quantity)) * Decimal(str(execution_price))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    self._cash += proceeds
                    current_shares = self.holdings.get(order.ticker, 0)
                    self.holdings[order.ticker] = max(0, current_shares - order.quantity)
                elif order.direction == Direction.BUY:
                    cost = (Decimal(str(order.quantity)) * Decimal(str(execution_price))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    self._cash -= cost
                    current_shares = self.holdings.get(order.ticker, 0)
                    self.holdings[order.ticker] = current_shares + order.quantity
                
                order.status = OrderStatus.FILLED
            else:
                remaining_orders.append(order)
                
        self.active_orders = remaining_orders
