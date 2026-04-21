import pytest
from decimal import Decimal
from ams.models.config import TakeProfitMode, TakeProfitConfig, TakeProfitPolicy

def test_takeprofitconfig_validation_success():
    config_pos = TakeProfitConfig(mode=TakeProfitMode.POSITION, pos_threshold=Decimal('0.1'))
    assert config_pos.mode == TakeProfitMode.POSITION
    
    config_intra = TakeProfitConfig(mode=TakeProfitMode.INTRADAY, intra_threshold=Decimal('0.2'))
    assert config_intra.mode == TakeProfitMode.INTRADAY
    
    config_both = TakeProfitConfig(mode=TakeProfitMode.BOTH, pos_threshold=Decimal('0.1'), intra_threshold=Decimal('0.2'))
    assert config_both.mode == TakeProfitMode.BOTH

def test_takeprofitconfig_validation_failure_position():
    with pytest.raises(ValueError, match=r"\[VALIDATION_ERROR\]"):
        TakeProfitConfig(mode=TakeProfitMode.POSITION, pos_threshold=Decimal('0'))
    with pytest.raises(ValueError, match=r"\[VALIDATION_ERROR\]"):
        TakeProfitConfig(mode=TakeProfitMode.POSITION, pos_threshold=Decimal('-0.1'))
    with pytest.raises(ValueError, match=r"\[VALIDATION_ERROR\]"):
        TakeProfitConfig(mode=TakeProfitMode.POSITION, pos_threshold=None)

def test_takeprofitconfig_validation_failure_intraday():
    with pytest.raises(ValueError, match=r"\[VALIDATION_ERROR\]"):
        TakeProfitConfig(mode=TakeProfitMode.INTRADAY, intra_threshold=Decimal('0'))
    with pytest.raises(ValueError, match=r"\[VALIDATION_ERROR\]"):
        TakeProfitConfig(mode=TakeProfitMode.INTRADAY, intra_threshold=Decimal('-0.1'))
    with pytest.raises(ValueError, match=r"\[VALIDATION_ERROR\]"):
        TakeProfitConfig(mode=TakeProfitMode.INTRADAY, intra_threshold=None)

def test_takeprofitconfig_validation_failure_both():
    with pytest.raises(ValueError, match=r"\[VALIDATION_ERROR\]"):
        TakeProfitConfig(mode=TakeProfitMode.BOTH, pos_threshold=Decimal('0.1'), intra_threshold=Decimal('0'))
    with pytest.raises(ValueError, match=r"\[VALIDATION_ERROR\]"):
        TakeProfitConfig(mode=TakeProfitMode.BOTH, pos_threshold=Decimal('0'), intra_threshold=Decimal('0.1'))
    with pytest.raises(ValueError, match=r"\[VALIDATION_ERROR\]"):
        TakeProfitConfig(mode=TakeProfitMode.BOTH, pos_threshold=None, intra_threshold=Decimal('0.1'))

def test_takeprofitpolicy_calculate_position():
    config = TakeProfitConfig(mode=TakeProfitMode.POSITION, pos_threshold=Decimal('0.20'))
    avg_cost = Decimal('100')
    prev_close = Decimal('110')
    tp_price = TakeProfitPolicy.calculate_tp_price(config, avg_cost, prev_close)
    assert tp_price == Decimal('120.00')

def test_takeprofitpolicy_calculate_intraday():
    config = TakeProfitConfig(mode=TakeProfitMode.INTRADAY, intra_threshold=Decimal('0.08'))
    avg_cost = Decimal('100')
    prev_close = Decimal('110')
    tp_price = TakeProfitPolicy.calculate_tp_price(config, avg_cost, prev_close)
    assert tp_price == Decimal('118.80')

def test_takeprofitpolicy_calculate_both():
    config = TakeProfitConfig(mode=TakeProfitMode.BOTH, pos_threshold=Decimal('0.20'), intra_threshold=Decimal('0.08'))
    avg_cost = Decimal('100')
    prev_close = Decimal('110')
    tp_price = TakeProfitPolicy.calculate_tp_price(config, avg_cost, prev_close)
    assert tp_price == Decimal('118.80')
