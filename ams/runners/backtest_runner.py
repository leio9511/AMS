import pandas as pd

class BacktestRunner:
    def __init__(self, data_feed, broker, strategy):
        self.data_feed = data_feed
        self.broker = broker
        self.strategy = strategy
        self.equity_curve = []

    def run(self, start_date, end_date):
        dates = pd.date_range(start_date, end_date)
        for date in dates:
            data_slice = self.data_feed.get_data(None, date)
            if data_slice.empty:
                continue
            
            # Simple context object
            class Context:
                pass
            context = Context()
            
            # Assuming strategy generate_target_portfolio returns dict {ticker: percent}
            target_portfolio = self.strategy.generate_target_portfolio(context, data_slice)
            if target_portfolio:
                 for ticker, percent in target_portfolio.items():
                     self.broker.order_target_percent(ticker, percent)
            
            self.broker.update_equity()
            self.equity_curve.append({
                'date': date,
                'equity': self.broker.total_equity
            })
        return pd.DataFrame(self.equity_curve)
