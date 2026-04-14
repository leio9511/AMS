import pytest
import pandas as pd
import numpy as np
from strategies.cb_backtest_engine import CBBacktestEngine

def generate_mock_data():
    dates = pd.date_range(start='2023-01-02', periods=15, freq='B') # Starts on Monday
    data = []
    
    for i, date in enumerate(dates):
        # 5 bonds
        for j in range(1, 6):
            symbol = f"11000{j}"
            close = 100.0 + j + i
            premium_rate = 10.0 + j
            turnover = 1000.0 + j * 100
            
            # Bond 1 is risky on week 2
            is_risky = False
            if j == 1 and i >= 5:
                is_risky = True
                
            # Bond 2 has small scale
            scale = 0.2 if j == 2 else 1.0 # 0.2 < 0.3 thresh
            
            data.append({
                'date': date,
                'symbol': symbol,
                'close': close,
                'premium_rate': premium_rate,
                'turnover': turnover,
                'outstanding_scale': scale,
                'is_risky': is_risky
            })
            
    return pd.DataFrame(data)

def test_risk_filtering():
    df = generate_mock_data()
    # Rebalance happens on Fridays (i=4 is Friday, 2023-01-06, i=9 is 2023-01-13)
    # Bond 2 should be excluded because scale < 0.3
    # Bond 1 should be excluded on the second rebalance because is_risky = True starting i=5
    
    engine = CBBacktestEngine(df, max_holdings=5, friction_cost=0.0)
    engine.run()
    
    nav_df = engine.nav_history
    
    all_holdings_ever = set()
    for h_list in nav_df['holdings']:
        all_holdings_ever.update(h_list)
        
    # Bond 2 should NEVER be in holdings
    assert '110002' not in all_holdings_ever, "Bond 2 should be filtered out due to small scale"
    
    # Bond 1 should be in the holdings in week 1
    holdings_week1 = nav_df[nav_df['date'] == '2023-01-09']['holdings'].values[0]
    assert '110001' in holdings_week1, "Bond 1 should be present in week 1"
    
    # Bond 1 should NOT be in the holdings in week 3 (after second rebalance on 2023-01-13)
    holdings_week3 = nav_df[nav_df['date'] == '2023-01-16']['holdings'].values[0]
    assert '110001' not in holdings_week3, "Bond 1 should be filtered out in week 3 due to is_risky"


def test_weekly_rotation_costs():
    df = generate_mock_data()
    engine = CBBacktestEngine(df, max_holdings=2, friction_cost=0.01) # 1% cost
    ts = engine.run()
    
    assert ts['total_return'] is not None
    assert ts['annualized_return'] is not None
    # If costs are deducted, total return will reflect it.
    
    engine_no_cost = CBBacktestEngine(df, max_holdings=2, friction_cost=0.0)
    ts_no_cost = engine_no_cost.run()
    
    assert ts_no_cost['total_return'] > ts['total_return'] # Costs should reduce return

def test_tear_sheet_keys():
    df = generate_mock_data()
    engine = CBBacktestEngine(df)
    ts = engine.run()
    
    expected_keys = {
        "total_return", "annualized_return", "max_drawdown", 
        "sharpe_ratio", "alpha_vs_benchmark", "win_rate"
    }
    
    assert set(ts.keys()) == expected_keys
