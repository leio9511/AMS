from abc import ABC, abstractmethod
from ams.core.order import Order, OrderDirection

class BaseSlippageModel(ABC):
    @abstractmethod
    def calculate_slippage(self, order: Order, base_price: float) -> float:
        pass

class ExtremeRiskSlippageModel(BaseSlippageModel):
    def __init__(self, penalty_rate: float = 0.5):
        self.penalty_rate = penalty_rate

    def calculate_slippage(self, order: Order, base_price: float) -> float:
        if order.direction == OrderDirection.SELL:
            return base_price * (1 - self.penalty_rate)
        elif order.direction == OrderDirection.BUY:
            return base_price * (1 + self.penalty_rate)
        return base_price
