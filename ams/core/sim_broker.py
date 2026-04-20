import math
from decimal import Decimal, ROUND_HALF_UP
from ams.core.base import BaseBroker
from ams.core.order import Order, OrderDirection, OrderType, OrderStatus
from ams.core.slippage import BaseSlippageModel

class SimBroker(BaseBroker):
    def __init__(self, initial_cash=4000000.0, slippage=0.001, slippage_model: BaseSlippageModel = None):
        self._cash = Decimal(str(initial_cash)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self._initial_cash = float(initial_cash)
        self.slippage = Decimal(str(slippage))
        self.slippage_model = slippage_model
        self.order_book = [] # list of Order objects
        self.holdings = {} # ticker -> int (shares)
        self.avg_prices = {} # ticker -> Decimal (average price)
        self._total_equity = self._cash
        self._last_prices = {} # Fallback prices for suspended symbols

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

    def get_position(self, ticker: str) -> dict:
        qty = self.holdings.get(ticker, 0)
        avg = self.avg_prices.get(ticker, Decimal('0.00'))
        return {
            "ticker": ticker,
            "quantity": qty,
            "avg_price": avg
        }

    def submit_order(self, order: Order):
        self.order_book.append(order)

    def _expire_old_orders(self, current_date: str):
        if not current_date:
            return
        for order in self.order_book:
            if order.status == OrderStatus.PENDING and order.effective_date:
                if order.effective_date < current_date:
                    order.status = OrderStatus.CANCELED

    def match_orders(self, bar_data: dict, current_date: str = None):
        self._expire_old_orders(current_date)
        
        for order in self.order_book:
            if order.status != OrderStatus.PENDING:
                continue
                
            ticker = order.ticker
            if ticker not in bar_data:
                continue
                
            ticker_data = bar_data[ticker]
            
            if order.order_type == OrderType.LIMIT and order.direction == OrderDirection.SELL:
                high_price = ticker_data.get('high', 0.0)
                if high_price >= order.limit_price:
                    execute_price = order.limit_price
                    current_shares = self.holdings.get(ticker, 0)
                    
                    if current_shares >= order.quantity:
                        proceeds = (Decimal(str(order.quantity)) * Decimal(str(execute_price))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                        self._cash += proceeds
                        self.holdings[ticker] -= order.quantity
                        if self.holdings[ticker] == 0:
                            del self.holdings[ticker]
                            self.avg_prices.pop(ticker, None)
                        order.status = OrderStatus.FILLED
                    else:
                        order.status = OrderStatus.REJECTED
                        
            elif order.order_type == OrderType.MARKET:
                base_price = ticker_data.get('close', 0.0)
                if self.slippage_model:
                    execute_price = self.slippage_model.calculate_slippage(order, base_price)
                else:
                    if order.direction == OrderDirection.SELL:
                        execute_price = base_price * (1 - float(self.slippage))
                    else:
                        execute_price = base_price * (1 + float(self.slippage))
                        
                if order.direction == OrderDirection.SELL:
                    current_shares = self.holdings.get(ticker, 0)
                    if current_shares >= order.quantity:
                        proceeds = (Decimal(str(order.quantity)) * Decimal(str(execute_price))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                        self._cash += proceeds
                        self.holdings[ticker] -= order.quantity
                        if self.holdings[ticker] == 0:
                            del self.holdings[ticker]
                            self.avg_prices.pop(ticker, None)
                        order.status = OrderStatus.FILLED
                    else:
                        order.status = OrderStatus.REJECTED
                elif order.direction == OrderDirection.BUY:
                    cost = (Decimal(str(order.quantity)) * Decimal(str(execute_price))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    if self._cash >= cost:
                        self._cash -= cost
                        
                        old_qty = Decimal(str(self.holdings.get(ticker, 0)))
                        old_avg = self.avg_prices.get(ticker, Decimal('0.00'))
                        buy_qty = Decimal(str(order.quantity))
                        buy_price = Decimal(str(execute_price))
                        
                        new_avg_price = (old_qty * old_avg + buy_qty * buy_price) / (old_qty + buy_qty)
                        self.avg_prices[ticker] = new_avg_price
                        
                        self.holdings[ticker] = self.holdings.get(ticker, 0) + order.quantity
                        order.status = OrderStatus.FILLED
                    else:
                        order.status = OrderStatus.REJECTED

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
                
                old_qty = Decimal(str(current_shares))
                old_avg = self.avg_prices.get(ticker, Decimal('0.00'))
                buy_qty = Decimal(str(actual_bought_shares))
                buy_price = d_price * (Decimal('1') + self.slippage)
                
                new_avg_price = (old_qty * old_avg + buy_qty * buy_price) / (old_qty + buy_qty)
                self.avg_prices[ticker] = new_avg_price
                
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
                if self.holdings[ticker] == 0:
                    del self.holdings[ticker]
                    self.avg_prices.pop(ticker, None)
