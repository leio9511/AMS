class StrategyFactory:
    _registry = {}

    @classmethod
    def register_strategy(cls, strategy_id: str):
        def decorator(strategy_class):
            cls._registry[strategy_id] = strategy_class
            return strategy_class
        return decorator

    @classmethod
    def create_strategy(cls, strategy_id: str, **kwargs):
        if strategy_id not in cls._registry:
            raise ValueError(f"ERROR: Strategy '{strategy_id}' not found in registry.")
        return cls._registry[strategy_id](**kwargs)

    @classmethod
    def clear_registry(cls):
        """For testing purposes."""
        cls._registry.clear()
