import pytest
import pandas as pd
import numpy as np
from ams.core.cb_rotation_strategy import CBRotationStrategy

def test_generate_target_portfolio_success():
    strategy = CBRotationStrategy()
    
    # Generate mock dataframe with 50 bonds
    data = []
    for i in range(1, 51):
        data.append({
            'ticker': f'CB{i}',
            'close_price': 100 + i, # 101 to 150
            'premium_rate': i / 100.0, # 0.01 to 0.50
            'volume': 10000,
            'amount': 15000000, # > 10M
            'is_st': False,
            'suspended': False
        })
    df = pd.DataFrame(data)
    
    # Expected: double low = close_price + premium_rate * 100
    # CB1: 101 + 1 = 102
    # CB2: 102 + 2 = 104
    # ...
    # So the top 20 will be CB1 to CB20
    
    target = strategy.generate_target_portfolio(None, df)
    
    assert len(target) == 20
    assert 'CB1' in target
    assert 'CB20' in target
    assert 'CB21' not in target
    assert target['CB1'] == 0.05
    assert target['CB20'] == 0.05

def test_liquidity_threshold_filtering():
    strategy = CBRotationStrategy()
    df = pd.DataFrame([
        {'ticker': 'CB1', 'close_price': 100, 'premium_rate': 0.1, 'amount': 5000000}, # Excluded (<10M)
        {'ticker': 'CB2', 'close_price': 105, 'premium_rate': 0.1, 'amount': 15000000}, # Included
        {'ticker': 'CB3', 'close_price': 110, 'premium_rate': 0.1, 'amount': 20000000}, # Included
    ])
    
    target = strategy.generate_target_portfolio(None, df)
    assert 'CB1' not in target
    assert 'CB2' in target
    assert 'CB3' in target

def test_missing_and_suspended_data_filtering():
    strategy = CBRotationStrategy()
    df = pd.DataFrame([
        {'ticker': 'CB1', 'close_price': 100, 'premium_rate': 0.1, 'amount': 15000000, 'volume': 0}, # Suspended (0 volume)
        {'ticker': 'CB2', 'close_price': np.nan, 'premium_rate': 0.1, 'amount': 15000000, 'volume': 1000}, # Missing price
        {'ticker': 'CB3', 'close_price': 110, 'premium_rate': np.nan, 'amount': 15000000, 'volume': 1000}, # Missing premium
        {'ticker': 'CB4', 'close_price': 120, 'premium_rate': 0.1, 'amount': 15000000, 'volume': 1000}, # Valid
    ])
    
    target = strategy.generate_target_portfolio(None, df)
    assert 'CB1' not in target
    assert 'CB2' not in target
    assert 'CB3' not in target
    assert 'CB4' in target
