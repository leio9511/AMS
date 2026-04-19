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
            
            # Create daily_data for match_orders
            daily_data = {}
            for _, row in data_slice.iterrows():
                ticker_data = {}
                for col in row.index:
                    ticker_data[col] = row[col]
                # Ensure 'close' is available for match_orders
                if 'close' not in ticker_data and 'close_price' in ticker_data:
                    ticker_data['close'] = ticker_data['close_price']
                elif 'close' not in ticker_data and 'price' in ticker_data:
                    ticker_data['close'] = ticker_data['price']
                daily_data[row['ticker']] = ticker_data
                
            self.broker.match_orders(daily_data)
            
            context.broker = self.broker
            context.current_prices = current_prices
            context.date = date
            
            # The strategy should now internally translate target allocations into Orders
            # and submit them to the broker. It can still return the target_portfolio.
            target_portfolio = self.strategy.generate_target_portfolio(context, data_slice)
            

            
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
