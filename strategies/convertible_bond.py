from strategies.base_strategy import StrategyBase

class ConvertibleBondStrategy(StrategyBase):
    def __init__(self, engine, strategy_name="ConvertibleBondStrategy"):
        super().__init__(engine, strategy_name)
        self.threshold = -0.008

    def start(self):
        super().start()
        self.engine.register("eTick", self.on_tick)
        self.engine.register("eTimer", self.on_timer)

    def stop(self):
        super().stop()
        self.engine.unregister("eTick", self.on_tick)
        self.engine.unregister("eTimer", self.on_timer)

    def calculate_premium(self, price: float, conv_value: float) -> float:
        """Pure function: Calculate premium."""
        if conv_value <= 0:
            return 0.0
        return (price / conv_value) - 1.0

    def check_discount(self, premium: float) -> bool:
        """Pure function: check if discount threshold is met."""
        return premium <= self.threshold

    def on_tick(self, event):
        data = event.data
        code = data.get("code")
        price = data.get("price")
        conv_value = data.get("conv_value")
        premium = data.get("premium")

        if premium is None and price is not None and conv_value is not None:
            premium = self.calculate_premium(price, conv_value)

        if code and premium is not None:
            if self.check_discount(premium):
                print(f"SIGNAL: CB {code} discount is {premium*100:.2f}% (<= -0.8%)")

    def on_timer(self, event):
        pass
