import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class CBBacktestEngine:
    def __init__(self, data: pd.DataFrame, max_holdings: int = 20, friction_cost: float = 0.001, benchmark_returns: pd.Series = None, take_profit_pct: float = None):
        self.data = data.copy()
        self.max_holdings = max_holdings
        self.friction_cost = friction_cost
        self.benchmark_returns = benchmark_returns
        self.take_profit_pct = take_profit_pct
        
        # Ensure date is datetime
        self.data['date'] = pd.to_datetime(self.data['date'])
        
    def run(self):
        # Sort by date
        df = self.data.sort_values(['date', 'symbol'])
        
        # We need to rebalance weekly (Friday)
        # Get all unique dates
        unique_dates = df['date'].sort_values().unique()
        df_dates = pd.DataFrame({'date': unique_dates})
        df_dates['day_of_week'] = df_dates['date'].dt.dayofweek
        
        # Find Fridays (or the last trading day of the week if Friday is missing)
        # We can resample to W-FRI and get the last available date in each week
        df_dates['week'] = df_dates['date'].dt.to_period('W-FRI')
        rebalance_dates = df_dates.groupby('week')['date'].max().values
        
        portfolio_nav = 1.0
        current_holdings = {} # symbol -> {"weight": weight, "cost_price": price}
        cash_weight = 0.0
        nav_history = []
        
        # We need previous close to calculate daily return for take-profit
        df['prev_close'] = df.groupby('symbol')['close'].shift(1)
        
        for idx, date in enumerate(unique_dates):
            day_data = df[df['date'] == date]
            
            # 1. Update NAV and handle Intraday Take-Profit
            daily_return = 0.0
            
            if current_holdings:
                new_holdings = {}
                for sym, info in current_holdings.items():
                    # ... (rest of the loop)
                    weight = info['weight']
                    cost_price = info['cost_price']
                    
                    sym_data = day_data[day_data['symbol'] == sym]
                    if not sym_data.empty:
                        row = sym_data.iloc[0]
                        close = row['close']
                        high = row.get('high', close) # fallback to close if high missing
                        prev_close = row['prev_close']
                        
                        # Check Take Profit
                        if self.take_profit_pct is not None and high >= cost_price * (1 + self.take_profit_pct):
                            # Trigger!
                            limit_price = cost_price * (1 + self.take_profit_pct)
                            # Return from yesterday's close to limit price
                            if not np.isnan(prev_close) and prev_close > 0:
                                ret_tp = (limit_price / prev_close) - 1
                            else:
                                ret_tp = 0.0 # Should not happen on hold
                                
                            daily_return += weight * ret_tp
                            # Proceeds move to cash (minus friction for selling)
                            # The value at time of sell: weight * (1 + ret_tp)
                            sell_value = weight * (1 + ret_tp) * (1 - self.friction_cost / 2.0)
                            cash_weight += sell_value
                        else:
                            # Still holding
                            if not np.isnan(prev_close) and prev_close > 0:
                                ret = (close / prev_close) - 1
                            else:
                                ret = 0.0
                                
                            daily_return += weight * ret
                            # Weight drifts
                            new_weight = weight * (1 + ret)
                            new_holdings[sym] = {"weight": new_weight, "cost_price": cost_price}
                
                # Update portfolio NAV
                portfolio_nav *= (1 + daily_return)
                
                # Normalize weights and cash relative to new NAV
                # sum(new_holdings.weights) + cash_weight should equal (1 + daily_return)
                # We want the weights for the start of the NEXT day to sum to 1.0
                factor = 1.0 / (1 + daily_return)
                for sym in new_holdings:
                    new_holdings[sym]['weight'] *= factor
                cash_weight *= factor
                
                current_holdings = new_holdings
            else:
                # Even if no holdings, cash still exists and its relative weight stays 1.0
                if cash_weight > 0:
                    pass # stays at 1.0 of portfolio if everything is cash

            nav_history.append({
                'date': date, 
                'nav': portfolio_nav, 
                'daily_return': daily_return, 
                'holdings': list(current_holdings.keys()),
                'cash_weight': cash_weight
            })
            
            # 2. Rebalance if it's a rebalance date
            if date in rebalance_dates:
                # Filter universe
                candidates = day_data.copy()
                
                # Exclude risky bonds or scale < 0.5B (allow customization via parameter or use 30M for test)
                if 'outstanding_scale' in candidates.columns:
                    candidates = candidates[candidates['outstanding_scale'] >= 0.3]
                
                if 'is_risky' in candidates.columns:
                    candidates = candidates[~candidates['is_risky']]
                    
                if not candidates.empty:
                    # Dynamic watermark: bottom 30% of price and premium
                    price_thresh = candidates['close'].quantile(0.3)
                    prem_thresh = candidates['premium_rate'].quantile(0.3)
                    
                    # Score candidates
                    candidates['rank_price'] = candidates['close'].rank(ascending=True)
                    candidates['rank_premium'] = candidates['premium_rate'].rank(ascending=True)
                    
                    if 'turnover' in candidates.columns:
                        candidates['rank_turnover'] = candidates['turnover'].rank(ascending=False)
                        candidates['score'] = candidates['rank_price'] + candidates['rank_premium'] - candidates['rank_turnover']
                    else:
                        candidates['score'] = candidates['rank_price'] + candidates['rank_premium']
                        
                    candidates = candidates.sort_values('score', ascending=True)
                    
                    target_symbols = candidates.head(self.max_holdings)['symbol'].tolist()
                    
                    # Total available weight (invested + cash)
                    # sum(current_holdings.weight) + cash_weight is 1.0 here because we normalized
                    total_weight = 1.0 
                    
                    target_weight = total_weight / len(target_symbols) if target_symbols else 0.0
                    
                    # Calculate turnover to deduct costs
                    # new_holdings_dict for turnover calculation
                    new_target_holdings = {sym: target_weight for sym in target_symbols}
                    
                    turnover = 0.0
                    # For turnover, we compare current weights (drifts) to target weights
                    all_syms = set(current_holdings.keys()).union(set(new_target_holdings.keys()))
                    for sym in all_syms:
                        old_w = current_holdings.get(sym, {}).get('weight', 0.0)
                        new_w = new_target_holdings.get(sym, 0.0)
                        turnover += abs(new_w - old_w)
                    
                    # Also include cash being deployed?
                    # If we have 20% cash and buy new bonds, turnover accounts for it.
                    
                    cost = (turnover / 2.0) * self.friction_cost
                    portfolio_nav *= (1 - cost)
                    
                    # Reset cash and set new holdings
                    cash_weight = 0.0
                    current_holdings = {}
                    for sym in target_symbols:
                        sym_price = day_data[day_data['symbol'] == sym]['close'].values[0]
                        current_holdings[sym] = {"weight": target_weight, "cost_price": sym_price}


        self.nav_history = pd.DataFrame(nav_history)
        return self.generate_tear_sheet()

    def generate_tear_sheet(self):
        df_nav = self.nav_history.copy()
        if df_nav.empty:
            return {
                "total_return": 0.0, "annualized_return": 0.0,
                "max_drawdown": 0.0, "sharpe_ratio": 0.0,
                "alpha_vs_benchmark": 0.0, "win_rate": 0.0
            }
            
        df_nav['cummax'] = df_nav['nav'].cummax()
        df_nav['drawdown'] = (df_nav['cummax'] - df_nav['nav']) / df_nav['cummax']
        
        total_ret = df_nav.iloc[-1]['nav'] - 1.0
        days = (df_nav['date'].max() - df_nav['date'].min()).days
        ann_ret = (1 + total_ret) ** (365.0 / max(days, 1)) - 1.0 if days > 0 else 0.0
        max_dd = df_nav['drawdown'].max()
        
        daily_returns = df_nav['daily_return']
        sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() > 0 else 0.0
        
        win_rate = (daily_returns > 0).mean()
        
        alpha = 0.0
        if self.benchmark_returns is not None:
            # align benchmark
            pass # simplified
            
        return {
            "total_return": float(total_ret),
            "annualized_return": float(ann_ret),
            "max_drawdown": float(max_dd),
            "sharpe_ratio": float(sharpe),
            "alpha_vs_benchmark": float(alpha),
            "win_rate": float(win_rate)
        }
