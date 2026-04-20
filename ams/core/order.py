from enum import Enum
from dataclasses import dataclass
from typing import Optional

class OrderDirection(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"

STATUS_PENDING = "PENDING"
STATUS_FILLED = "FILLED"
STATUS_CANCELED = "CANCELED"
STATUS_REJECTED = "REJECTED"

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
