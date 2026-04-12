from strategies.base_strategy import StrategyBase

class ETFArbStrategy(StrategyBase):
    def __init__(self, engine, strategy_name="ETFArbStrategy"):
        super().__init__(engine, strategy_name)

    def start(self):
        super().start()
        self.engine.register("eTick", self.on_tick)
        self.engine.register("eTimer", self.on_timer)

    def stop(self):
        super().stop()
        self.engine.unregister("eTick", self.on_tick)
        self.engine.unregister("eTimer", self.on_timer)

    def calculate_premium(self, price: float, iopv: float) -> float:
        """Pure function to calculate premium percentage."""
        if iopv <= 0:
            return 0.0
        return (price / iopv) - 1.0

    def on_tick(self, event):
        data = event.data
        code = data.get("code")
        price = data.get("lastPrice") # QMT full_tick uses lastPrice
        iopv = data.get("iopv") 
        
        if price is not None and iopv is not None:
            premium = self.calculate_premium(price, iopv)
            if premium > 0.02:
                print(f"!!! SIGNAL: {code} premium is {premium*100:.2f}% (> 2%)")

    def on_timer(self, event):
        pass
