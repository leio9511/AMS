import math
from ams.core.base import BaseBroker

class SimBroker(BaseBroker):
    def __init__(self, initial_cash=4000000.0, slippage=0.001):
        self.cash = float(initial_cash)
        self.initial_cash = float(initial_cash)
        self.slippage = slippage
        self.holdings = {} # ticker -> int (shares)
        self.total_equity = float(initial_cash)

    def update_equity(self, current_prices: dict):
        holdings_value = sum(
            self.holdings[t] * current_prices[t] 
            for t in self.holdings 
            if t in current_prices
        )
        self.total_equity = self.cash + holdings_value

    def order_target_percent(self, ticker, percent, price=None):
        if price is None or price <= 0:
            return

        target_value = self.total_equity * percent
        current_shares = self.holdings.get(ticker, 0)
        current_value = current_shares * price
        
        diff_value = target_value - current_value
        
        if diff_value > 0: # Buy
            target_shares_to_buy = math.floor(diff_value / price / 10) * 10
            
            # Check cash limits
            cost_per_share = price * (1 + self.slippage)
            max_shares_cash = math.floor(self.cash / cost_per_share / 10) * 10
            
            actual_bought_shares = min(target_shares_to_buy, max_shares_cash)
            
            if actual_bought_shares > 0:
                cost = actual_bought_shares * price * (1 + self.slippage)
                self.cash -= cost
                self.holdings[ticker] = current_shares + actual_bought_shares
                
        elif diff_value < 0: # Sell
            # Calculate shares to sell to reach target
            target_shares_to_sell = math.ceil(abs(diff_value) / price)
            actual_sold_shares = min(target_shares_to_sell, current_shares)
            
            if actual_sold_shares > 0:
                proceeds = actual_sold_shares * price * (1 - self.slippage)
                self.cash += proceeds
                self.holdings[ticker] = current_shares - actual_sold_shares
