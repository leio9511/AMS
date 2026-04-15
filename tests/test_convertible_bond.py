import pytest
import pandas as pd
from ams.core.cb_rotation_strategy import CBRotationStrategy

def test_cb_rotation_filters_st_bonds():
    data = pd.DataFrame({
        'ticker': ['CB1', 'CB2', 'CB3'],
        'price': [100, 110, 105],
        'premium': [10, 15, 5],
        'is_st': [False, True, False]
    })
    strategy = CBRotationStrategy(top_n=2)
    portfolio = strategy.generate_target_portfolio(None, data)
    assert 'CB2' not in portfolio
    assert 'CB1' in portfolio
    assert 'CB3' in portfolio

def test_cb_rotation_applies_stop_loss():
    data = pd.DataFrame({
        'ticker': ['CB1', 'CB2'],
        'price': [100, 110],
        'premium': [10, 15],
        'is_st': [False, False],
        'daily_return': [-0.05, -0.09]
    })
    strategy = CBRotationStrategy(top_n=2)
    portfolio = strategy.generate_target_portfolio(None, data)
    assert 'CB2' not in portfolio
    assert 'CB1' in portfolio

def test_cb_rotation_calculates_double_low():
    data = pd.DataFrame({
        'ticker': ['CB1', 'CB2', 'CB3'],
        'price': [100, 120, 105],
        'premium': [10, 5, 20],
        'is_st': [False, False, False]
    })
    # Double lows: CB1=110, CB2=125, CB3=125
    strategy = CBRotationStrategy(top_n=1)
    portfolio = strategy.generate_target_portfolio(None, data)
    assert 'CB1' in portfolio
    assert 'CB2' not in portfolio
    assert 'CB3' not in portfolio
