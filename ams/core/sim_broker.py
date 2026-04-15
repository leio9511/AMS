from ams.core.base import BaseBroker

class SimBroker(BaseBroker):
    def __init__(self, initial_cash=100000.0, slippage=0.001):
        self.cash = initial_cash
        self.initial_cash = initial_cash
        self.slippage = slippage
        self.holdings = {} # ticker -> value
        self.total_equity = initial_cash

    def update_equity(self):
        self.total_equity = self.cash + sum(self.holdings.values())

    def order_target_percent(self, ticker, percent):
        self.update_equity()
        target_value = self.total_equity * percent
        current_value = self.holdings.get(ticker, 0.0)
        
        diff = target_value - current_value
        
        if diff > 0: # Buy
            cost = diff * (1 + self.slippage)
            self.cash -= cost
            self.holdings[ticker] = target_value
        elif diff < 0: # Sell
            proceeds = abs(diff) * (1 - self.slippage)
            self.cash += proceeds
            self.holdings[ticker] = target_value
        
        self.update_equity()
