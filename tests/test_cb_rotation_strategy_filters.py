import pytest
import pandas as pd
from ams.core.cb_rotation_strategy import CBRotationStrategy

class MockContext:
    def __init__(self, holdings=None, daily_return=None):
        self.holdings = holdings or []
        self.daily_return = daily_return or {}

def get_base_data():
    return pd.DataFrame({
        'ticker': ['CB1', 'CB2', 'CB3', 'CB4'],
        'close_price': [100.0, 110.0, 90.0, 105.0],
        'premium_rate': [0.1, 0.2, 0.15, 0.05],
        'amount': [20000000, 20000000, 20000000, 20000000],
        'is_redeemed': [False, False, False, False],
        'is_st': [False, False, False, False]
    })

def test_filter_forced_redemption():
    data = get_base_data()
    # CB2 is redeemed
    data.loc[data['ticker'] == 'CB2', 'is_redeemed'] = True
    
    strategy = CBRotationStrategy()
    context = MockContext()
    portfolio = strategy.generate_target_portfolio(context, data)
    
    # CB2 should not be in the portfolio
    assert 'CB2' not in portfolio
    assert 'CB1' in portfolio
    assert 'CB3' in portfolio
    assert 'CB4' in portfolio

def test_filter_st_stocks():
    data = get_base_data()
    # CB3 is ST
    data.loc[data['ticker'] == 'CB3', 'is_st'] = True
    
    strategy = CBRotationStrategy()
    context = MockContext()
    portfolio = strategy.generate_target_portfolio(context, data)
    
    # CB3 should not be in the portfolio
    assert 'CB3' not in portfolio
    assert 'CB1' in portfolio
    assert 'CB2' in portfolio
    assert 'CB4' in portfolio

def test_intraday_stop_loss():
    data = get_base_data()
    # Let's say CB4 had a previous close of 120.0 and dropped to 105.0 (-12.5% return)
    # CB1 had previous close of 101.0 -> 100.0 (>-8%)
    context = MockContext(
        holdings=['CB1', 'CB4'],
        daily_return={'CB1': 101.0, 'CB4': 120.0}
    )
    
    strategy = CBRotationStrategy()
    portfolio = strategy.generate_target_portfolio(context, data)
    
    # CB4 should be filtered out (stop loss)
    assert 'CB4' not in portfolio
    # CB1 should remain (no stop loss triggered)
    assert 'CB1' in portfolio
    # CB2 and CB3 should remain (not in holdings, so not subject to intraday stop loss here, though they wouldn't hit it anyway)
    assert 'CB2' in portfolio
    assert 'CB3' in portfolio
