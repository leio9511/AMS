from enum import Enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

class TakeProfitMode(Enum):
    POSITION = "position"
    INTRADAY = "intraday"
    BOTH = "both"

@dataclass(frozen=True)
class TakeProfitConfig:
    mode: TakeProfitMode
    pos_threshold: Optional[Decimal] = None
    intra_threshold: Optional[Decimal] = None

    def __post_init__(self):
        if self.mode in [TakeProfitMode.POSITION, TakeProfitMode.BOTH]:
            if self.pos_threshold is None or self.pos_threshold <= 0:
                raise ValueError(f"[VALIDATION_ERROR] TakeProfitConfig: POSITION threshold must be positive.")
        if self.mode in [TakeProfitMode.INTRADAY, TakeProfitMode.BOTH]:
            if self.intra_threshold is None or self.intra_threshold <= 0:
                raise ValueError(f"[VALIDATION_ERROR] TakeProfitConfig: INTRADAY threshold must be positive.")

class TakeProfitPolicy:
    @staticmethod
    def calculate_tp_price(config: TakeProfitConfig, avg_cost: Decimal, prev_close: Decimal) -> Decimal:
        if config.mode == TakeProfitMode.POSITION:
            return avg_cost * (Decimal('1') + config.pos_threshold)
        elif config.mode == TakeProfitMode.INTRADAY:
            return prev_close * (Decimal('1') + config.intra_threshold)
        elif config.mode == TakeProfitMode.BOTH:
            pos_price = avg_cost * (Decimal('1') + config.pos_threshold)
            intra_price = prev_close * (Decimal('1') + config.intra_threshold)
            return min(pos_price, intra_price)
        raise ValueError(f"Unknown mode: {config.mode}")
