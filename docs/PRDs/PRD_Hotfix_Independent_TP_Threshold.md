---
Affected_Projects: [AMS]
Related_Issue: ISSUE-1163
---

# PRD: Professional Strategy Configuration with Encapsulated Risk Policy (Final)

## 1. Context & Problem
AMS 2.0 requires industrial-grade risk control configuration. Current loose parameter handling leads to "Primitive Obsession." To align with professional quantitative standards, we must transition to a structured, type-safe, and decoupled architecture that separates configuration data from decision-making logic using the Policy Pattern.

## 2. Requirements & User Stories
1.  **US 1 (Domain Models)**: Establish `TakeProfitMode` (Enum) and `TakeProfitConfig` (Dataclass) as the standardized way to define take-profit parameters.
2.  **US 2 (Defensive Initialization)**: `TakeProfitConfig` must perform mandatory validation during instantiation to ensure thresholds are positive and non-None for the active mode.
3.  **US 3 (Encapsulated Policy)**: Implement `TakeProfitPolicy` to encapsulate the math logic for calculating converged take-profit prices, keeping the Strategy class focused on high-level portfolio composition.
4.  **US 4 (Backward Compatibility)**: The system must automatically map legacy individual parameters to the new typed configuration objects.

## 3. Architecture & Technical Strategy
*   **Modular Isolation**: All new models reside in `/root/projects/AMS/ams/models/config.py`.
*   **The Policy Pattern**:
    - `TakeProfitConfig`: A frozen dataclass serving as a pure DTO with a `__post_init__` validator.
    - `TakeProfitPolicy`: A service class that consumes a `TakeProfitConfig` and market data to output a single `Decimal` price.
*   **Integration**: `CBRotationStrategy` delegates all TP pricing requests to the `TakeProfitPolicy`.
*   **Rollback Strategy**:
    - **Baseline Commit**: `7ddc459`.
    - **Recovery**: `git reset --hard 7ddc459 && git clean -fd`.

## 4. Acceptance Criteria
*   **Scenario 1: Black-Box Price Convergence**
    - **Given** a strategy configured with POSITION=20% and INTRADAY=8% (Mode: BOTH).
    - **Given** a position with cost=100 and yesterday_close=110.
    - **When** a daily order is generated.
    - **Then** the final limit price must be exactly **118.8**.
*   **Scenario 2: Black-Box Crash Prevention**
    - **Given** an attempt to create a strategy with Mode: BOTH but providing only one threshold.
    - **When** the system initializes.
    - **Then** it must raise a `ValueError` containing the specific validation error message defined in Section 7.

## 5. Overall Test Strategy & Quality Goal
*   **Type Safety Audit**: Verify via unit tests that invalid config combinations are blocked before execution.
*   **Regression**: Ensure the refactored engine produces identical backtest equity results for the standard 2025-2026 dataset.

## 6. Framework Modifications
- `/root/projects/AMS/ams/models/config.py` (New)
- `/root/projects/AMS/ams/core/cb_rotation_strategy.py` (Refactor)
- `/root/projects/AMS/tests/test_cb_rotation_strategy.py` (Update)

## 7. Hardcoded Content (Anti-Hallucination)

### Mandatory Model & Validation Implementation:
```python
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
```

### Policy Method Signature:
```python
@staticmethod
def calculate_tp_price(config: TakeProfitConfig, avg_cost: Decimal, prev_close: Decimal) -> Decimal:
```
