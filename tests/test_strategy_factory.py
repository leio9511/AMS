import pytest
from ams.core.factory import StrategyFactory

class MockStrategy:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

def test_strategy_registration():
    StrategyFactory.clear_registry()
    
    @StrategyFactory.register_strategy('mock')
    class MyMockStrategy(MockStrategy):
        pass

    assert 'mock' in StrategyFactory._registry
    assert StrategyFactory._registry['mock'] == MyMockStrategy

def test_create_strategy_success():
    StrategyFactory.clear_registry()
    
    @StrategyFactory.register_strategy('mock')
    class MyMockStrategy(MockStrategy):
        pass

    strategy = StrategyFactory.create_strategy('mock', param1="value1")
    assert isinstance(strategy, MyMockStrategy)
    assert strategy.kwargs == {"param1": "value1"}

def test_create_strategy_not_found_error():
    StrategyFactory.clear_registry()
    
    with pytest.raises(ValueError, match="^ERROR: Strategy 'nonexistent' not found in registry.$"):
        StrategyFactory.create_strategy('nonexistent')
