from ams.models.config import TakeProfitConfig, TakeProfitMode, TakeProfitPolicy
from decimal import Decimal
import pandas as pd
import numpy as np
from ams.core.base import BaseStrategy
from ams.core.order import Order, OrderDirection, OrderType, OrderStatus


TP_MODE_POSITION = "position"
TP_MODE_INTRADAY = "intraday"
TP_MODE_BOTH = "both"

class CBRotationStrategy(BaseStrategy):

    def __init__(self, top_n=20, liquidity_threshold=10000000, weight_per_position=0.05, 
                 stop_loss_threshold=-0.08, take_profit_threshold=None,
                 rebalance_period='daily', reinvest_on_risk_exit=True,
                 tp_mode=TP_MODE_POSITION, tp_config=None):
        self.top_n = top_n
        self.liquidity_threshold = liquidity_threshold
        self.weight_per_position = weight_per_position
        self.stop_loss_threshold = stop_loss_threshold
        self.rebalance_period = rebalance_period
        self.take_profit_threshold = take_profit_threshold
        self.reinvest_on_risk_exit = reinvest_on_risk_exit
        self.tp_mode = TakeProfitMode(tp_mode) if isinstance(tp_mode, str) else tp_mode
        self.last_rebalance_date = None
        self.liquidated_this_cycle = set()
        self.last_bar_holdings = set()
        
        # Priority: tp_config > take_profit_threshold
        if tp_config is not None:
            self.tp_config = tp_config
        elif self.take_profit_threshold is not None:
            thresh = Decimal(str(self.take_profit_threshold))
            self.tp_config = TakeProfitConfig(mode=self.tp_mode, pos_threshold=thresh, intra_threshold=thresh)
        else:
            self.tp_config = None

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

        stopped_out_tickers = set()
        current_holdings = list(getattr(context, 'holdings', []))
        broker = getattr(context, 'broker', None)
        
        if broker is not None and hasattr(broker, 'order_book'):
            for o in broker.order_book:
                if o.status == OrderStatus.PENDING and o.direction == OrderDirection.BUY:
                    if o.ticker not in current_holdings:
                        current_holdings.append(o.ticker)

        current_date = getattr(context, 'current_date', None)
        current_date_str = str(current_date.date()) if hasattr(current_date, 'date') else str(current_date) if current_date else None
        current_prices = getattr(context, 'current_prices', {})
        
        sell_intents = {}

        # 1. Stop-Loss Evaluation (Decoupled from candidate filtering)
        if hasattr(context, 'daily_return') and isinstance(context.daily_return, dict):
            for ticker in current_holdings:
                if ticker in context.daily_return:
                    prev_close = context.daily_return[ticker]
                    current_price = current_prices.get(ticker)
                    if current_price is None and not df.empty and 'ticker' in df.columns:
                        match = df[df['ticker'] == ticker]
                        if not match.empty:
                            current_price = match.iloc[0][price_col]
                    
                    if current_price is not None and prev_close > 0:
                        daily_ret = (current_price - prev_close) / prev_close
                        if daily_ret <= self.stop_loss_threshold:
                            stopped_out_tickers.add(ticker)
                            self.liquidated_this_cycle.add(ticker)
                            if broker is not None:
                                position = broker.get_position(ticker)
                                ssot_qty = int(position.get('quantity', 0))
                                if ssot_qty > 0:
                                    sell_intents.setdefault(ticker, {})['STOP_LOSS'] = {
                                        'order_type': OrderType.MARKET,
                                        'price': float(current_price),
                                        'quantity': ssot_qty
                                    }

        # Filter out stopped-out tickers from df candidates
        if stopped_out_tickers and not df.empty and 'ticker' in df.columns:
            df = df[~df['ticker'].isin(stopped_out_tickers)]
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
        
        if self.rebalance_period == 'weekly' and current_date is not None:
            if hasattr(current_date, 'weekday'):
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

        if is_rebalance_day:
            self.liquidated_this_cycle.clear()

        target_portfolio = {}
        
        for ticker in self.last_bar_holdings:
            if ticker not in current_holdings:
                self.liquidated_this_cycle.add(ticker)

        if is_rebalance_day:
            if current_date is not None:
                self.last_rebalance_date = current_date
            selected = df.head(self.top_n)
            for ticker in selected['ticker']:
                target_portfolio[ticker] = self.weight_per_position
        else:
            for ticker in current_holdings:
                if ticker not in stopped_out_tickers:
                    target_portfolio[ticker] = self.weight_per_position
            
            if self.reinvest_on_risk_exit:
                needed = self.top_n - len(target_portfolio)
                if needed > 0:
                    for ticker in df['ticker']:
                        if ticker not in target_portfolio and ticker not in self.liquidated_this_cycle:
                            target_portfolio[ticker] = self.weight_per_position
                            needed -= 1
                            if needed == 0:
                                break

        # Execution using PMS Order generation
        if broker is not None:
            current_equity = broker.total_equity
            
            pending_buys = {}
            pending_sells = {}
            if hasattr(broker, 'order_book'):
                for o in broker.order_book:
                    if o.status == OrderStatus.PENDING:
                        if o.direction == OrderDirection.BUY:
                            pending_buys[o.ticker] = pending_buys.get(o.ticker, 0) + o.quantity
                        elif o.direction == OrderDirection.SELL:
                            pending_sells[o.ticker] = pending_sells.get(o.ticker, 0) + o.quantity

            def get_shares_for_sell(t):
                return max(0, broker.holdings.get(t, 0) - pending_sells.get(t, 0))

            def get_shares_for_buy(t):
                return broker.holdings.get(t, 0) + pending_buys.get(t, 0)

            effective_holdings_tickers = list(broker.holdings.keys())
            for t in pending_buys:
                if t not in effective_holdings_tickers:
                    effective_holdings_tickers.append(t)

            # 2. Rebalance Sell Intents
            for ticker in effective_holdings_tickers:
                eff_shares_sell = get_shares_for_sell(ticker)
                if ticker not in target_portfolio:
                    if eff_shares_sell > 0:
                        sell_intents.setdefault(ticker, {})['REBALANCE'] = {
                            'target_percent': 0.0,
                            'current_price': current_prices.get(ticker),
                            'current_equity': current_equity,
                            'current_shares': eff_shares_sell
                        }
                else:
                    target_weight = target_portfolio[ticker]
                    current_val = eff_shares_sell * current_prices.get(ticker, 0)
                    current_weight = current_val / current_equity if current_equity > 0 else 0
                    if current_weight - target_weight > 0.005:
                        sell_intents.setdefault(ticker, {})['REBALANCE'] = {
                            'target_percent': target_weight,
                            'current_price': current_prices.get(ticker),
                            'current_equity': current_equity,
                            'current_shares': eff_shares_sell
                        }

            # Buy new or increased (before TP intent evaluation)
            for ticker, target_weight in target_portfolio.items():
                eff_shares_buy = get_shares_for_buy(ticker)
                current_val = eff_shares_buy * current_prices.get(ticker, 0)
                current_weight = current_val / current_equity if current_equity > 0 else 0
                
                if target_weight - current_weight > 0.005:
                    order = self.order_target_percent(
                        broker=broker,
                        ticker=ticker,
                        target_percent=target_weight,
                        current_price=current_prices.get(ticker),
                        current_equity=current_equity,
                        current_shares=eff_shares_buy
                    )
                    if order:
                        order.effective_date = current_date_str

            # 3. Take Profit Sell Intents
            if hasattr(self, 'tp_config') and self.tp_config is not None:
                for ticker in target_portfolio:
                    if any(o.ticker == ticker and o.order_type == OrderType.LIMIT for o in (broker.order_book if hasattr(broker, 'order_book') else []) if o.status == OrderStatus.PENDING and o.direction == OrderDirection.SELL):
                        continue

                    current_price = current_prices.get(ticker)
                    if not current_price:
                        continue
                        
                    current_price_dec = Decimal(str(current_price))
                    
                    avg_price = None
                    position = broker.get_position(ticker) if hasattr(broker, 'get_position') else {}
                    if position and position.get('avg_price') is not None:
                        avg_price = position['avg_price']
                        if isinstance(avg_price, (int, float, str)):
                            avg_price = Decimal(str(avg_price))
                                
                    avg_cost_dec = avg_price if avg_price is not None else current_price_dec
                    
                    tp_price = TakeProfitPolicy.calculate_tp_price(
                        config=self.tp_config,
                        avg_cost=avg_cost_dec,
                        prev_close=current_price_dec
                    )
                    
                    if tp_price is not None:
                        ssot_qty = int(position.get('quantity', 0)) if position else 0
                        if ssot_qty > 0:
                            sell_intents.setdefault(ticker, {})['TAKE_PROFIT'] = {
                                'order_type': OrderType.LIMIT,
                                'price': float(tp_price),
                                'quantity': ssot_qty
                            }

            # Execution Arbitration Phase
            # Priority: STOP_LOSS > TAKE_PROFIT > REBALANCE
            for ticker, intents in sell_intents.items():
                if 'STOP_LOSS' in intents:
                    intent = intents['STOP_LOSS']
                    if hasattr(broker, 'order_book'):
                        for o in broker.order_book:
                            if o.ticker == ticker and o.status == OrderStatus.PENDING and o.direction == OrderDirection.SELL and o.order_type == OrderType.LIMIT:
                                broker.cancel_order(o.order_id)
                    sl_order = Order(
                        ticker=ticker,
                        direction=OrderDirection.SELL,
                        quantity=intent['quantity'],
                        order_type=intent['order_type'],
                        limit_price=intent['price'],
                        effective_date=current_date_str
                    )
                    broker.submit_order(sl_order)
                elif 'TAKE_PROFIT' in intents:
                    intent = intents['TAKE_PROFIT']
                    tp_order = Order(
                        ticker=ticker,
                        direction=OrderDirection.SELL,
                        quantity=intent['quantity'],
                        order_type=intent['order_type'],
                        limit_price=intent['price'],
                        effective_date=current_date_str
                    )
                    broker.submit_order(tp_order)
                elif 'REBALANCE' in intents:
                    intent = intents['REBALANCE']
                    if hasattr(broker, 'order_book'):
                        for o in broker.order_book:
                            if o.ticker == ticker and o.status == OrderStatus.PENDING and o.direction == OrderDirection.SELL and o.order_type == OrderType.LIMIT:
                                broker.cancel_order(o.order_id)
                    order = self.order_target_percent(
                        broker=broker,
                        ticker=ticker,
                        target_percent=intent['target_percent'],
                        current_price=intent['current_price'],
                        current_equity=intent['current_equity'],
                        current_shares=intent['current_shares']
                    )
                    if order:
                        order.effective_date = current_date_str



        self.last_bar_holdings = set(target_portfolio.keys())
        return target_portfolio
