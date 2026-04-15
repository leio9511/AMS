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
        previous_close = {}
        for date in dates:
            data_slice = self.data_feed.get_data(None, date)
            if data_slice.empty:
                continue
            
            # Extract current prices
            current_prices = {}
            price_col = 'close_price' if 'close_price' in data_slice.columns else 'price' if 'price' in data_slice.columns else 'close'
            if price_col in data_slice.columns and 'ticker' in data_slice.columns:
                for _, row in data_slice.iterrows():
                    current_prices[row['ticker']] = row[price_col]
            
            self.broker.update_equity(current_prices)
            
            # Simple context object
            class Context:
                pass
            context = Context()
            
            # Enrich context with previous close as daily_return (as requested by PR-001)
            context.daily_return = previous_close
            context.holdings = list(self.broker.holdings.keys())
            
            # Update previous_close for next day
            price_col = 'close_price' if 'close_price' in data_slice.columns else 'price' if 'price' in data_slice.columns else 'close'
            if price_col in data_slice.columns and 'ticker' in data_slice.columns:
                for _, row in data_slice.iterrows():
                    previous_close[row['ticker']] = row[price_col]
            
            # Assuming strategy generate_target_portfolio returns dict {ticker: percent}
            target_portfolio = self.strategy.generate_target_portfolio(context, data_slice)
            
            if target_portfolio is not None:
                current_holdings = list(self.broker.holdings.keys())
                total_equity = self.broker.total_equity
                
                # Sell missing symbols or significantly decreased weights
                for ticker in current_holdings:
                    if ticker not in target_portfolio:
                        # order_target_percent expects a price now!
                        self.broker.order_target_percent(ticker, 0.0, price=current_prices.get(ticker))
                    else:
                        current_value = self.broker.holdings.get(ticker, 0) * current_prices.get(ticker, 0.0)
                        current_weight = current_value / total_equity if total_equity > 0 else 0.0
                        target_weight = target_portfolio[ticker]
                        if current_weight - target_weight > 0.005:
                            self.broker.order_target_percent(ticker, target_weight, price=current_prices.get(ticker))
                
                # Buy new symbols or significantly increased weights
                for ticker, target_weight in target_portfolio.items():
                    if ticker not in current_holdings:
                        self.broker.order_target_percent(ticker, target_weight, price=current_prices.get(ticker))
                    else:
                        current_value = self.broker.holdings.get(ticker, 0) * current_prices.get(ticker, 0.0)
                        current_weight = current_value / total_equity if total_equity > 0 else 0.0
                        if target_weight - current_weight > 0.005:
                            self.broker.order_target_percent(ticker, target_weight, price=current_prices.get(ticker))

            
            self.broker.update_equity(current_prices)
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
            'Max Drawdown': max_drawdown,
            'Final Equity': final_equity
        }

    def print_report(self, df_equity):
        metrics = self.calculate_metrics(df_equity)
        print(f"Total Return: {metrics['Total Return']:.4%}")
        print(f"Max Drawdown: {metrics['Max Drawdown']:.4%}")
        print(f"Final Equity: {metrics.get('Final Equity', 0.0):.2f}")

if __name__ == "__main__":
    from ams.core.history_datafeed import HistoryDataFeed
    from ams.core.sim_broker import SimBroker
    from ams.core.cb_rotation_strategy import CBRotationStrategy
    
    feed = HistoryDataFeed("data/cb_history_factors.csv")
    broker = SimBroker(initial_cash=4000000.0)
    strategy = CBRotationStrategy()
    
    runner = BacktestRunner(feed, broker, strategy)
    
    # Run backtest for period mentioned in PRD
    df_equity = runner.run("2025-01-06", "2025-02-06")
    
    metrics = runner.calculate_metrics(df_equity)
    final_equity = df_equity['equity'].iloc[-1] if not df_equity.empty else 4000000.0
    print(f"Total Return: {metrics['Total Return']:.4%}")
    print(f"Max Drawdown: {metrics['Max Drawdown']:.4%}")
    print(f"Final Equity: {final_equity:.2f}")
