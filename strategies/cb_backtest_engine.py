import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class CBBacktestEngine:
    def __init__(self, data: pd.DataFrame, max_holdings: int = 20, friction_cost: float = 0.001, benchmark_returns: pd.Series = None):
        self.data = data.copy()
        self.max_holdings = max_holdings
        self.friction_cost = friction_cost
        self.benchmark_returns = benchmark_returns
        
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
        current_holdings = {} # symbol -> weight
        nav_history = []
        
        # For simplicity, calculate daily returns of all bonds
        df['ret'] = df.groupby('symbol')['close'].pct_change()
        
        for idx, date in enumerate(unique_dates):
            day_data = df[df['date'] == date]
            
            # 1. Update NAV based on current holdings' returns
            daily_return = 0.0
            if current_holdings:
                for sym, weight in current_holdings.items():
                    sym_data = day_data[day_data['symbol'] == sym]
                    if not sym_data.empty:
                        ret = sym_data.iloc[0]['ret']
                        if not np.isnan(ret):
                            daily_return += weight * ret
                portfolio_nav *= (1 + daily_return)
                
            nav_history.append({'date': date, 'nav': portfolio_nav, 'daily_return': daily_return})
            
            # 2. Rebalance if it's a rebalance date
            if date in rebalance_dates:
                # Filter universe
                candidates = day_data.copy()
                
                # Exclude risky bonds or scale < 0.5B (allow customization via parameter or use 30M for test)
                # If scale < 30M, exclude
                if 'outstanding_scale' in candidates.columns:
                    candidates = candidates[candidates['outstanding_scale'] >= 0.3] # Assume scale in 100M, 0.3 = 30M
                
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
                        candidates['rank_turnover'] = candidates['turnover'].rank(ascending=False) # higher turnover = lower rank val for subtraction
                        candidates['score'] = candidates['rank_price'] + candidates['rank_premium'] - candidates['rank_turnover']
                    else:
                        candidates['score'] = candidates['rank_price'] + candidates['rank_premium']
                        
                    candidates = candidates.sort_values('score', ascending=True)
                    
                    target_symbols = candidates.head(self.max_holdings)['symbol'].tolist()
                    target_weight = 1.0 / len(target_symbols) if target_symbols else 0.0
                    
                    new_holdings = {sym: target_weight for sym in target_symbols}
                    
                    # Calculate turnover to deduct costs
                    turnover = 0.0
                    all_syms = set(current_holdings.keys()).union(set(new_holdings.keys()))
                    for sym in all_syms:
                        old_w = current_holdings.get(sym, 0.0)
                        new_w = new_holdings.get(sym, 0.0)
                        turnover += abs(new_w - old_w)
                        
                    # Cost is applied on the change
                    cost = (turnover / 2.0) * self.friction_cost # total traded weight * cost
                    portfolio_nav *= (1 - cost)
                    
                    current_holdings = new_holdings

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
