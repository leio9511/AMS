import pandas as pd
import numpy as np
from ams.core.base import BaseStrategy

class CBRotationStrategy(BaseStrategy):
    def __init__(self, top_n=20, liquidity_threshold=10000000, weight_per_position=0.05, stop_loss_threshold=-0.08, rebalance_period='daily', reinvest_on_risk_exit=True, take_profit_threshold=None):
        self.top_n = top_n
        self.liquidity_threshold = liquidity_threshold
        self.weight_per_position = weight_per_position
        self.stop_loss_threshold = stop_loss_threshold
        self.rebalance_period = rebalance_period
        self.reinvest_on_risk_exit = reinvest_on_risk_exit
        self.take_profit_threshold = take_profit_threshold

    def on_bar(self, context, data):
        pass

    def generate_target_portfolio(self, context, data):
        if data is None or data.empty:
            return {}

        df = data.copy()

        # Try to resolve column names robustly to match tests and historical data
        price_col = 'close_price' if 'close_price' in df.columns else 'price' if 'price' in df.columns else 'close'
        premium_col = 'premium_rate' if 'premium_rate' in df.columns else 'premium'
        amount_col = 'amount' if 'amount' in df.columns else 'turnover'

        # Filter out NaN in critical columns
        df = df.dropna(subset=[price_col, premium_col])

        # Filter out bonds with no volume / suspended
        if 'volume' in df.columns:
            df = df[df['volume'] > 0]
            
        if 'suspended' in df.columns:
            df = df[~df['suspended']]

        # Filter 1: Forced Redemption
        if 'is_redeemed' in df.columns:
            df = df[~df['is_redeemed']]

        # Filter 2: ST Guard
        if 'is_st' in df.columns:
            df = df[~df['is_st']]

        # Filter 3: Intraday Stop-Loss
        # Calculate daily return if context has daily_return (previous close)
        if hasattr(context, 'daily_return') and isinstance(context.daily_return, dict):
            # context.daily_return contains previous_close
            current_holdings = getattr(context, 'holdings', [])
            
            def check_stop_loss(row):
                ticker = row['ticker']
                if ticker in current_holdings and ticker in context.daily_return:
                    prev_close = context.daily_return[ticker]
                    current_price = row[price_col]
                    if prev_close > 0:
                        daily_ret = (current_price - prev_close) / prev_close
                        if daily_ret <= self.stop_loss_threshold:
                            return False # Filter out
                return True # Keep
                
            df = df[df.apply(check_stop_loss, axis=1)]
        elif 'daily_return' in df.columns:
            # Fallback for older tests that provide daily_return directly in the dataframe
            df = df[df['daily_return'] > self.stop_loss_threshold]

        # Liquidity threshold (amount/turnover >= 10,000,000)
        # Note: In backtesting with some data sources, volume/amount might be missing.
        # If the column exists, we apply the filter.
        if amount_col in df.columns and not df[amount_col].isna().all():
            df = df[df[amount_col] >= self.liquidity_threshold]

        if df.empty:
            return {}

        # Double low calculation: close_price + premium_rate * 100
        if premium_col == 'premium_rate':
            df['double_low'] = df[price_col] + df[premium_col] * 100
        else:
            df['double_low'] = df[price_col] + df[premium_col]

        df = df.sort_values(by='double_low', ascending=True)

        # Select top candidates
        target_portfolio = {}
        selected = df.head(self.top_n)
        
        # If the number of selected bonds is equal to top_n or we're using dynamic weights, we assign weights.
        # Older tests expected a uniform distribution sum to 1.0 (weight = 1.0 / len(selected)) for small sets,
        # but the new PR requirement explicitly says "weight_per_position = 0.05".
        # We should use weight_per_position. Let's see if old tests expected 1.0 / len(selected).
        # Actually, the old tests just checked `assert 'CB1' in portfolio`. The value didn't matter.
        for ticker in selected['ticker']:
            target_portfolio[ticker] = self.weight_per_position

        if hasattr(context, 'broker') and hasattr(context, 'current_prices'):
            current_holdings = list(context.broker.holdings.keys())
            total_equity = context.broker.total_equity
            
            # Determine if we can buy today
            can_buy = True
            if self.rebalance_period == 'weekly':
                # Rebalance on Friday (4) by default
                if hasattr(context, 'date') and context.date.weekday() != 4:
                    if not self.reinvest_on_risk_exit:
                        can_buy = False
            
            # Sell missing
            for ticker in current_holdings:
                if ticker not in target_portfolio:
                    self.order_target_percent(ticker, 0.0, context.current_prices.get(ticker), context.broker)
                else:
                    current_value = context.broker.holdings.get(ticker, 0) * context.current_prices.get(ticker, 0.0)
                    current_weight = current_value / total_equity if total_equity > 0 else 0.0
                    target_weight = target_portfolio[ticker]
                    if current_weight - target_weight > 0.005:
                        self.order_target_percent(ticker, target_weight, context.current_prices.get(ticker), context.broker)
            
            # Buy new
            for ticker, target_weight in target_portfolio.items():
                if ticker not in current_holdings:
                    if can_buy:
                        self.order_target_percent(ticker, target_weight, context.current_prices.get(ticker), context.broker, take_profit_threshold=self.take_profit_threshold)
                else:
                    current_value = context.broker.holdings.get(ticker, 0) * context.current_prices.get(ticker, 0.0)
                    current_weight = current_value / total_equity if total_equity > 0 else 0.0
                    if target_weight - current_weight > 0.005 and can_buy:
                        self.order_target_percent(ticker, target_weight, context.current_prices.get(ticker), context.broker, take_profit_threshold=self.take_profit_threshold)

        return target_portfolio
