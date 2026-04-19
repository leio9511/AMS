from abc import ABC, abstractmethod
from typing import Dict, Any
from .order import Order

class BaseSlippageModel(ABC):
    @abstractmethod
    def calculate_execution_price(self, order: Order, bar_data: Dict[str, Any]) -> float:
        """
        Calculate the execution price for the given order and bar data.
        
        :param order: The order to execute.
        :param bar_data: Dictionary containing bar data (e.g., 'close', 'high', 'low', 'open').
        :return: The calculated execution price.
        """
        pass

class ExtremeRiskSlippageModel(BaseSlippageModel):
    def __init__(self, deduction_percentage: float):
        """
        :param deduction_percentage: The percentage to deduct from the close price (e.g., 0.50 for 50%).
        """
        self.deduction_percentage = deduction_percentage

    def calculate_execution_price(self, order: Order, bar_data: Dict[str, Any]) -> float:
        """
        Calculate the execution price by applying the deduction percentage to the 'close' price.
        """
        close_price = bar_data.get('close')
        if close_price is None:
            raise ValueError("bar_data must contain 'close' price")
        
        return close_price * (1.0 - self.deduction_percentage)
