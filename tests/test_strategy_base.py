import pytest
from ams.core.base import BaseStrategy, BaseDataFeed, BaseBroker

def test_base_strategy_instantiation_fails_without_methods():
    with pytest.raises(TypeError):
        class IncompleteStrategy(BaseStrategy):
            pass
        IncompleteStrategy()

    with pytest.raises(TypeError):
        BaseStrategy()

def test_base_datafeed_instantiation_fails_without_methods():
    with pytest.raises(TypeError):
        class IncompleteDataFeed(BaseDataFeed):
            pass
        IncompleteDataFeed()

    with pytest.raises(TypeError):
        BaseDataFeed()

def test_base_broker_instantiation_fails_without_methods():
    with pytest.raises(TypeError):
        class IncompleteBroker(BaseBroker):
            pass
        IncompleteBroker()

    with pytest.raises(TypeError):
        BaseBroker()
