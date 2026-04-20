---
Affected_Projects: [AMS]
Related_Issue: ISSUE-1161
---

# PRD: Professional Order Lifecycle and Precision Take-Profit

## 1. Context & Problem
AMS 2.0 requires professional-grade execution mechanics to align with QMT standards:
1.  **Floating Point Drift**: Current simple division for average cost calculation leads to precision errors in financial bookkeeping.
2.  **Zombie Orders**: Lack of automated daily order expiration creates long-term execution risks.
3.  **Split-Brain State**: The strategy must not maintain local cost records; the Broker must provide the Single Source of Truth (SSoT).

## 2. Requirements & User Stories
1.  **US 1 (High-Precision SSoT)**: `SimBroker` must calculate and store weighted average cost using `decimal.Decimal` to ensure absolute financial accuracy.
2.  **US 2 (Day-Order Lifecycle)**: `SimBroker` must automatically invalidate all `PENDING` orders from previous days at the start of each daily cycle.
3.  **US 3 (Converged Dual-Mode TP)**: Strategy shall fetch the SSoT cost from the Broker and issue a single limit order at `min(cost_tp, intraday_tp)`.
4.  **US 4 (Standardized QMT Interface)**: Implement `get_position(ticker)` to return a standard position object containing `avg_price`.

## 3. Architecture & Technical Strategy
*   **Precision Layer**: All internal calculations for `avg_price` and `total_equity` in `SimBroker` must utilize the `Decimal` class.
*   **Order Metadata**: `Order` objects gain an `effective_date`.
*   **Self-Cleaning Broker**: `SimBroker.match_orders` will invoke an internal `_expire_old_orders(current_date)` method *before* processing any market data.
*   **Cost Logic**: `new_avg_price = (old_qty * old_avg + buy_qty * buy_price) / (old_qty + buy_qty)`. All variables cast to `Decimal`.
*   **Rollback Strategy**:
    - **Git**: `git reset --hard 1759781` (The validated baseline before this PRD).
    - **Audit**: All changes must pass `test_broker_precision.py` before merging.

## 4. Acceptance Criteria
*   **Scenario 1: Infinite Precision**
    - **Given** multiple buy sequences with non-trivial decimals (e.g., 103.456).
    - **Then** the Broker's reported `avg_price` must match a manual `Decimal` calculation with zero drift.
*   **Scenario 2: Automatic Expiry**
    - **Given** an order submitted on Day T.
    - **When** the simulation reaches Day T+1.
    - **Then** the order status must transition to `CANCELED` before the first bar of Day T+1 is matched.

## 5. Overall Test Strategy & Quality Goal
*   **Precision Audit**: A specialized test suite involving 100+ random trades to verify no drift in `total_equity`.
*   **Lifecycle Trace**: Log analysis to confirm the `PENDING` -> `CANCELED` transition during the day-switch.

## 6. Framework Modifications
- `/root/projects/AMS/ams/core/order.py`
- `/root/projects/AMS/ams/core/sim_broker.py`
- `/root/projects/AMS/ams/core/cb_rotation_strategy.py`
- `/root/projects/AMS/ams/runners/backtest_runner.py`

## 7. Hardcoded Content (Anti-Hallucination)

### Order Status Strings:
```python
STATUS_PENDING = "PENDING"
STATUS_FILLED = "FILLED"
STATUS_CANCELED = "CANCELED"
STATUS_REJECTED = "REJECTED"
```

### Strategy Modes:
```python
TP_MODE_POSITION = "position"
TP_MODE_INTRADAY = "intraday"
TP_MODE_BOTH = "both"
```

### Calculation Types:
```python
from decimal import Decimal, ROUND_HALF_UP
```
