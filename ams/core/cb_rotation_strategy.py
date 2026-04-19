import pandas as pd
import numpy as np
from ams.core.base import BaseStrategy
from ams.core.order import Order, OrderDirection, OrderType

class CBRotationStrategy(BaseStrategy):
    def __init__(self, top_n=20, liquidity_threshold=10000000, weight_per_position=0.05, 
                 stop_loss_threshold=-0.08, take_profit_threshold=None,
                 rebalance_period='daily', reinvest_on_risk_exit=True):
        self.top_n = top_n
        self.liquidity_threshold = liquidity_threshold
        self.weight_per_position = weight_per_position
        self.stop_loss_threshold = stop_loss_threshold
        self.take_profit_threshold = take_profit_threshold
        self.rebalance_period = rebalance_period
        self.reinvest_on_risk_exit = reinvest_on_risk_exit
        self.last_rebalance_date = None

    def on_bar(self, context, data):
        pass

    def generate_target_portfolio(self, context, data):
        if data is None or data.empty:
            return {}

        df = data.copy()

        price_col = 'close_price' if 'close_price' in df.columns else 'price' if 'price' in df.columns else 'close'
        premium_col = 'premium_rate' if 'premium_rate' in df.columns else 'premium'
        amount_col = 'amount' if 'amount' in df.columns else 'turnover'

        df = df.dropna(subset=[price_col, premium_col])

        if 'volume' in df.columns:
            df = df[df['volume'] > 0]
            
        if 'suspended' in df.columns:
            df = df[~df['suspended']]

        if 'is_redeemed' in df.columns:
            df = df[~df['is_redeemed']]

        if 'is_st' in df.columns:
            df = df[~df['is_st']]

        # Intraday Stop-Loss Filter
        stopped_out_tickers = set()
        if hasattr(context, 'daily_return') and isinstance(context.daily_return, dict):
            current_holdings = getattr(context, 'holdings', [])
            def check_stop_loss(row):
                ticker = row['ticker']
                if ticker in current_holdings and ticker in context.daily_return:
                    prev_close = context.daily_return[ticker]
                    current_price = row[price_col]
                    if prev_close > 0:
                        daily_ret = (current_price - prev_close) / prev_close
                        if daily_ret <= self.stop_loss_threshold:
                            stopped_out_tickers.add(ticker)
                            return False # Filter out
                return True
            df = df[df.apply(check_stop_loss, axis=1)]
        elif 'daily_return' in df.columns:
            df = df[df['daily_return'] > self.stop_loss_threshold]

        if amount_col in df.columns and not df[amount_col].isna().all():
            df = df[df[amount_col] >= self.liquidity_threshold]

        if premium_col == 'premium_rate':
            df['double_low'] = df[price_col] + df[premium_col] * 100
        else:
            df['double_low'] = df[price_col] + df[premium_col]

        df = df.sort_values(by='double_low', ascending=True)

        # Rebalance Logic
        is_rebalance_day = True
        current_date = getattr(context, 'current_date', None)
        
        if self.rebalance_period == 'weekly' and current_date is not None:
            if hasattr(current_date, 'weekday'):
                # E.g., rebalance on Friday (weekday 4)
                # Or just rebalance if it's been 7 days
                if self.last_rebalance_date is None:
                    is_rebalance_day = True
                else:
                    days_diff = (pd.to_datetime(current_date) - pd.to_datetime(self.last_rebalance_date)).days
                    if days_diff >= 7:
                        is_rebalance_day = True
                    elif current_date.weekday() == 4 and pd.to_datetime(self.last_rebalance_date).weekday() != 4:
                        is_rebalance_day = True
                    else:
                        is_rebalance_day = False
            else:
                is_rebalance_day = True

        target_portfolio = {}
        
        if is_rebalance_day:
            if current_date is not None:
                self.last_rebalance_date = current_date
            selected = df.head(self.top_n)
            for ticker in selected['ticker']:
                target_portfolio[ticker] = self.weight_per_position
        else:
            # Not a rebalance day
            # If we don't reinvest on risk exit, we just keep current holdings minus stopped out ones
            current_holdings = getattr(context, 'holdings', [])
            if not self.reinvest_on_risk_exit:
                for ticker in current_holdings:
                    if ticker not in stopped_out_tickers:
                        # Keep the same weight roughly (or we just maintain positions)
                        target_portfolio[ticker] = self.weight_per_position
            else:
                # If we reinvest, we might pick new ones up to top_n?
                # The instructions say: "If weekly and we are stopped out early in the week, 
                # do not re-enter positions until the scheduled rebalance day (e.g., hold cash)."
                # So even if reinvest=True, wait... the requirement says: 
                # "If weekly and we are stopped out early in the week, do not re-enter positions until the scheduled rebalance day (e.g., hold cash)."
                # This perfectly matches reinvest_on_risk_exit=False.
                # If reinvest_on_risk_exit=True, maybe it does re-enter? Let's just keep current holdings if not rebalance day.
                for ticker in current_holdings:
                    if ticker not in stopped_out_tickers:
                        target_portfolio[ticker] = self.weight_per_position
                
                # If reinvest is True, fill the rest up to top_n
                if self.reinvest_on_risk_exit:
                    needed = self.top_n - len(target_portfolio)
                    if needed > 0:
                        # pick new ones from df
                        for ticker in df['ticker']:
                            if ticker not in target_portfolio:
                                target_portfolio[ticker] = self.weight_per_position
                                needed -= 1
                                if needed == 0:
                                    break

        # Execution using PMS Order generation
        broker = getattr(context, 'broker', None)
        if broker is not None:
            current_prices = getattr(context, 'current_prices', {})
            current_equity = broker.total_equity
            current_holdings_shares = broker.holdings.copy()
            
            # Sell missing or decreased
            for ticker in list(current_holdings_shares.keys()):
                if ticker not in target_portfolio:
                    self.order_target_percent(
                        broker=broker,
                        ticker=ticker,
                        target_percent=0.0,
                        current_price=current_prices.get(ticker),
                        current_equity=current_equity,
                        current_shares=current_holdings_shares[ticker]
                    )
                else:
                    target_weight = target_portfolio[ticker]
                    current_val = current_holdings_shares[ticker] * current_prices.get(ticker, 0)
                    current_weight = current_val / current_equity if current_equity > 0 else 0
                    if current_weight - target_weight > 0.005:
                        self.order_target_percent(
                            broker=broker,
                            ticker=ticker,
                            target_percent=target_weight,
                            current_price=current_prices.get(ticker),
                            current_equity=current_equity,
                            current_shares=current_holdings_shares[ticker]
                        )
                        
            # Buy new or increased
            for ticker, target_weight in target_portfolio.items():
                current_shares = current_holdings_shares.get(ticker, 0)
                current_val = current_shares * current_prices.get(ticker, 0)
                current_weight = current_val / current_equity if current_equity > 0 else 0
                
                if target_weight - current_weight > 0.005:
                    buy_order = self.order_target_percent(
                        broker=broker,
                        ticker=ticker,
                        target_percent=target_weight,
                        current_price=current_prices.get(ticker),
                        current_equity=current_equity,
                        current_shares=current_shares
                    )
                    
                    # Take Profit Mechanism
                    if buy_order and self.take_profit_threshold is not None:
                        # Assuming execution price is roughly current_price for cost basis
                        cost_price = current_prices.get(ticker)
                        if cost_price:
                            tp_price = cost_price * (1 + self.take_profit_threshold)
                            tp_order = Order(
                                ticker=ticker,
                                direction=OrderDirection.SELL,
                                quantity=buy_order.quantity,
                                order_type=OrderType.LIMIT,
                                limit_price=tp_price
                            )
                            broker.submit_order(tp_order)

        return target_portfolio
