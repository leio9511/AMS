import math
from decimal import Decimal, ROUND_HALF_UP
from ams.core.base import BaseBroker

class SimBroker(BaseBroker):
    def __init__(self, initial_cash=4000000.0, slippage=0.001):
        self._cash = Decimal(str(initial_cash)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self._initial_cash = float(initial_cash)
        self.slippage = Decimal(str(slippage))
        self.holdings = {} # ticker -> int (shares)
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
