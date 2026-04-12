from strategies.base_strategy import StrategyBase

class CrystalFlyStrategy(StrategyBase):
    def __init__(self, engine, strategy_name="CrystalFlyStrategy"):
        super().__init__(engine, strategy_name)

    def start(self):
        super().start()
        self.engine.register("eTick", self.on_tick)
        self.engine.register("eTimer", self.on_timer)

    def stop(self):
        super().stop()
        self.engine.unregister("eTick", self.on_tick)
        self.engine.unregister("eTimer", self.on_timer)

    def check_fundamentals(self, pe: float, threshold: float = 30.0) -> bool:
        """Pure function: Fundamental screening formula."""
        if pe is None:
            return False
        return pe < threshold

    def on_tick(self, event):
        data = event.data
        code = data.get("code")
        pe = data.get("pe")
        
        if code and pe is not None:
            if self.check_fundamentals(pe):
                print(f"SIGNAL: {code} passed fundamental screening (PE: {pe})")

    def on_timer(self, event):
        pass
