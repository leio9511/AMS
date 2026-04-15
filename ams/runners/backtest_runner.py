import os
import pandas as pd
import numpy as np

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
            
            # Need to sell things not in target portfolio
            if target_portfolio is not None:
                current_holdings = list(self.broker.holdings.keys())
                for ticker in current_holdings:
                    if ticker not in target_portfolio:
                        self.broker.order_target_percent(ticker, 0.0)
                
                for ticker, percent in target_portfolio.items():
                    self.broker.order_target_percent(ticker, percent)
            
            self.broker.update_equity()
            self.equity_curve.append({
                'date': date,
                'equity': self.broker.total_equity
            })
            
        return pd.DataFrame(self.equity_curve)
        
    def calculate_metrics(self, df_equity):
        if df_equity is None or df_equity.empty:
            return {'Total Return': 0.0, 'Max Drawdown': 0.0}
            
        initial_equity = df_equity['equity'].iloc[0]
        final_equity = df_equity['equity'].iloc[-1]
        
        total_return = (final_equity - initial_equity) / initial_equity
        
        # Max Drawdown
        df_equity['high_water_mark'] = df_equity['equity'].cummax()
        df_equity['drawdown'] = (df_equity['equity'] - df_equity['high_water_mark']) / df_equity['high_water_mark']
        max_drawdown = df_equity['drawdown'].min()
        
        return {
            'Total Return': total_return,
            'Max Drawdown': max_drawdown
        }

if __name__ == "__main__":
    from ams.core.history_datafeed import HistoryDataFeed
    from ams.core.sim_broker import SimBroker
    from ams.core.cb_rotation_strategy import CBRotationStrategy
    
    feed = HistoryDataFeed("data/cb_history_factors.csv")
    broker = SimBroker(initial_cash=100000.0)
    strategy = CBRotationStrategy()
    
    runner = BacktestRunner(feed, broker, strategy)
    
    # Run backtest for period mentioned in PRD
    df_equity = runner.run("2025-01-06", "2025-02-06")
    
    metrics = runner.calculate_metrics(df_equity)
    print(f"Total Return: {metrics['Total Return']:.4%}")
    print(f"Max Drawdown: {metrics['Max Drawdown']:.4%}")
