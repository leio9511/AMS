from enum import Enum
from dataclasses import dataclass
from typing import Optional

class OrderDirection(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"

class OrderStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"

@dataclass
class Order:
    ticker: str
    direction: OrderDirection
    quantity: int
    order_type: OrderType
    limit_price: float
    status: OrderStatus = OrderStatus.PENDING
    effective_date: Optional[str] = None
