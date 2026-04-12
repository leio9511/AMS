from engine.event_engine import EventEngine

class StrategyBase:
    def __init__(self, engine: EventEngine, strategy_name: str = "Base"):
        self.engine = engine
        self.strategy_name = strategy_name
        self.active = False

    def start(self):
        """Called to explicitly begin event subscription and processing."""
        self.active = True

    def stop(self):
        """Called to explicitly end event subscription and processing."""
        self.active = False
