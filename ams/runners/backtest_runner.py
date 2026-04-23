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
            # 1. Bar Input Ready
            data_slice = self.data_feed.get_data(None, date)
            if data_slice is None or data_slice.empty:
                continue
                
            # Create a dict of daily bar data for match_orders
            # Structure for match_orders: {ticker: {'high': ..., 'close': ..., ...}}
            daily_data = {}
            for _, row in data_slice.iterrows():
                ticker = row['ticker']
                daily_data[ticker] = {
                    'high': row.get('high_price', row.get('high', row.get('close_price', row.get('close', 0.0)))),
                    'close': row.get('close_price', row.get('close', 0.0)),
                    'low': row.get('low_price', row.get('low', row.get('close_price', row.get('close', 0.0)))),
                    'open': row.get('open_price', row.get('open', row.get('close_price', row.get('close', 0.0))))
                }

            # Convert date to string to ensure correct comparison for day-order lifecycle
            date_str = str(date.date()) if hasattr(date, 'date') else str(date)
            
            # 2. Match Orders
            self.broker.match_orders(daily_data, current_date=date_str)

            # 3. Expire Orders
            if hasattr(self.broker, 'expire_orders'):
                self.broker.expire_orders(current_date=date_str)
            
            # 4. Portfolio Snapshot
            # Extract current prices for equity update
            current_prices = {}
            price_col = 'close_price' if 'close_price' in data_slice.columns else 'price' if 'price' in data_slice.columns else 'close'
            if price_col in data_slice.columns and 'ticker' in data_slice.columns:
                for _, row in data_slice.iterrows():
                    current_prices[row['ticker']] = row[price_col]
            
            self.broker.update_equity(current_prices)
            
            # 5. Strategy Signal Evaluation
            class Context:
                pass
            context = Context()
            context.daily_return = previous_close
            context.holdings = list(self.broker.holdings.keys())
            context.broker = self.broker
            context.current_date = date
            context.current_prices = current_prices
            
            # Update previous_close for next day
            if price_col in data_slice.columns and 'ticker' in data_slice.columns:
                for _, row in data_slice.iterrows():
                    previous_close[row['ticker']] = row[price_col]
            
            # 6. Order Creation
            # The Strategy is now responsible for generating Orders!
            self.strategy.generate_target_portfolio(context, data_slice)
            
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
