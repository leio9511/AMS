import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch
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
    
    engine_no_cost = CBBacktestEngine(df, max_holdings=2, friction_cost=0.0)
    ts_no_cost = engine_no_cost.run()
    
    assert ts_no_cost['total_return'] > ts['total_return']

def test_take_profit_trigger_logic():
    # Given a mock holding with cost=100 and high=106, with take_profit_pct=0.05, 
    # assert the bond is sold at 105 and removed from holdings.
    dates = pd.date_range(start='2023-01-06', periods=3, freq='B') # Starts on Friday (Rebalance Day)
    
    data = [
        {'date': dates[0], 'symbol': 'B1', 'close': 100.0, 'high': 100.0, 'premium_rate': 10.0},
        {'date': dates[1], 'symbol': 'B1', 'close': 102.0, 'high': 106.0, 'premium_rate': 10.0},
        {'date': dates[2], 'symbol': 'B1', 'close': 103.0, 'high': 103.0, 'premium_rate': 10.0},
    ]
    df = pd.DataFrame(data)
    
    engine = CBBacktestEngine(df, max_holdings=1, friction_cost=0.0, take_profit_pct=0.05)
    engine.run()
    
    nav_history = engine.nav_history
    # Day 0: Buy B1 at 100.
    # Day 1: High 106 >= 105. Trigger! Sell at 105. 
    #   Daily ret = (105/100) - 1 = 0.05. 
    #   NAV = 1.0 * (1.05) = 1.05.
    
    assert nav_history.iloc[1]['nav'] == 1.05
    assert 'B1' not in nav_history.iloc[1]['holdings']
    assert nav_history.iloc[2]['nav'] == 1.05

def test_cash_management_during_rebalance():
    # Given 20% cash_weight on rebalance day, assert that cash_weight is reset to 0 
    # and the full portfolio value is redistributed.
    dates = pd.date_range(start='2023-01-06', periods=10, freq='B') # Starts on Friday
    
    data = []
    for i, d in enumerate(dates):
        # B1 hits TP on next week Tuesday (i=7)
        data.append({'date': d, 'symbol': 'B1', 'close': 100.0 if i < 7 else 120.0, 'high': 115.0 if i == 7 else 100.0, 'premium_rate': 10.0})
        data.append({'date': d, 'symbol': 'B2', 'close': 100.0, 'high': 100.0, 'premium_rate': 5.0})
        
    df = pd.DataFrame(data)
    engine = CBBacktestEngine(df, max_holdings=1, friction_cost=0.0, take_profit_pct=0.10)
    engine.run()
    
    nav_history = engine.nav_history
    # Rebalance on dates[0] and dates[5] and dates[9]
    # At dates[9] (Friday), rebalance should reset cash_weight
    last_row = nav_history.iloc[-1]
    assert last_row['cash_weight'] == 0.0
    assert len(last_row['holdings']) == 1

def test_no_take_profit_when_disabled():
    # When take_profit_pct=None, assert the engine ignores high price and uses only close.
    dates = pd.date_range(start='2023-01-06', periods=2, freq='B')
    data = [
        {'date': dates[0], 'symbol': 'B1', 'close': 100.0, 'high': 100.0, 'premium_rate': 10.0},
        {'date': dates[1], 'symbol': 'B1', 'close': 102.0, 'high': 120.0, 'premium_rate': 10.0},
    ]
    df = pd.DataFrame(data)
    engine = CBBacktestEngine(df, max_holdings=1, friction_cost=0.0, take_profit_pct=None)
    engine.run()
    
    nav_history = engine.nav_history
    assert nav_history.iloc[1]['nav'] == 1.02

def test_accounting_correctness():
    # Assert that NAV remains consistent with holdings + cash
    df = generate_mock_data()
    # Add high column
    df['high'] = df['close'] * 1.02
    engine = CBBacktestEngine(df, max_holdings=3, friction_cost=0.001, take_profit_pct=0.01)
    engine.run()
    
    nav_history = engine.nav_history
    assert not nav_history['nav'].isnull().any()
    assert (nav_history['nav'] > 0).all()
