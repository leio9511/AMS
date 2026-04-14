---
Affected_Projects: [AMS]
---

# PRD: Configurable Intraday Take-Profit for CB Rotation

## 1. Context & Problem (业务背景与核心痛点)
The current Convertible Bond (CB) Double-Low rotation strategy executes entirely on weekly closing prices (Friday close). However, the CB market in China is T+0 and often experiences extreme intraday "demon" spikes (妖风) driven by underlying stock volatility or speculative funds. A purely weekly rotation strategy fails to capture these intraday profits. By introducing an automated, configurable grid-like intraday take-profit (e.g., 5%, 8%) condition, we can lock in these spikes and convert the holding into idle cash until the next weekly rebalancing cycle, thereby significantly improving the strategy's Sharpe ratio and total return.

## 2. Requirements & User Stories (需求定义)
- **Goal 1 (Configurable Threshold)**: The backtest engine must accept a `take_profit_pct` parameter (e.g., `0.05` for 5%, `0.08` for 8%, or `None` to disable) so it can be easily adjusted for parameter optimization or live trading setups.
- **Goal 2 (Data Completeness)**: The data loader (`cb_data_loader.py`) must be upgraded to fetch and store the `high` price field for each trading day. Without the `high` price, the backtest engine cannot determine if an intraday limit order would have been filled.
- **Goal 3 (Intraday Execution Simulation)**: During the daily simulation loop in the engine, if a bond's `high` price is `>=` the cost basis * `(1 + take_profit_pct)`, the engine must simulate an execution exactly at the limit price: `cost basis * (1 + take_profit_pct)`.
- **Goal 4 (Cash Management)**: Once the take-profit is triggered, the holding is liquidated. The proceeds (minus friction cost) must be kept as `cash` in the portfolio. This `cash` balance will not participate in market fluctuations until the next weekly rebalance date (Friday close), at which point the total NAV (holdings value + cash) is equally redistributed among the new Top 20 targets.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Data Layer (`cb_data_loader.py`)**: Update the historical ETL process (both QMT and Akshare paths) to extract the `high` price along with `open`, `close`, `premium_rate`, and `outstanding_scale`. Save the augmented dataset.
- **Backtest Layer (`cb_backtest_engine.py`)**:
  - Add `take_profit_pct: float = None` to the constructor.
  - Modify the `current_holdings` state to track cost basis: e.g., `{symbol: {"weight": 0.05, "cost_price": 110.5}}`.
  - Introduce a `cash_weight` variable to track idle funds.
  - In the daily update loop:
    - Before updating the day's NAV via `close` returns, check if `high >= cost_price * (1 + take_profit_pct)`.
    - If True, simulate a sell at `cost_price * (1 + take_profit_pct)`, deduct `friction_cost / 2.0` (single-side sell cost), remove the bond from `current_holdings`, and add the net proceeds to `cash_weight`.
  - During the weekly rebalance:
    - Total investable capital = current value of remaining holdings + `cash_weight`.
    - Reset `cash_weight = 0.0`.
    - Re-allocate equally to the new top candidates and update their `cost_price` to the current rebalance execution price (`open` or `close` based on design).

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Data Completeness**
  - **Given** The `cb_data_loader.py` script
  - **When** Executed to fetch CB history
  - **Then** The resulting dataframe must contain a valid, numeric `high` column for every trading day.
- **Scenario 2: Intraday Take-Profit Trigger**
  - **Given** A holding bought at a cost price of 100.0, a `take_profit_pct` of `0.05`, and today's `high` is 106.0 and `close` is 102.0.
  - **When** The daily backtest loop processes this day
  - **Then** The holding is sold at exactly 105.0 (minus sell-side friction cost), the proceeds become cash, and the holding is removed from the active portfolio. The daily NAV is updated using the cash proceeds rather than the 102.0 closing price.
- **Scenario 3: Cash Reinvestment**
  - **Given** A portfolio with 20% in `cash_weight` on a Friday rebalance day
  - **When** The weekly rebalance logic executes
  - **Then** The cash is fully deployed, `cash_weight` drops to 0, and the new holdings' cost bases are updated to the rebalance execution prices.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Test Strategy**: 
  - Create a mock `pandas` DataFrame in `tests/test_cb_backtest_engine.py` simulating an intraday spike (e.g., `high=120`, `close=105`, `cost=100`, `tp=0.10`). Assert that the NAV reflects a sell at 110 and that the symbol is dropped from holdings the next day.
  - Assert that if `take_profit_pct=None`, the system ignores the `high` price and relies entirely on `close`.
- **Quality Goal**: Guarantee 100% deterministic accounting of cash vs. invested capital. Ensure no forward-looking bias is introduced via the `high` price.

## 6. Framework Modifications (框架防篡改声明)
- Modify `strategies/cb_backtest_engine.py` and `scripts/cb_data_loader.py` within the AMS project boundaries. No core openclaw SDLC files are modified.

## 7. Hardcoded Content (硬编码内容)
- Tear Sheet Output Keys MUST include: `{"total_return": float, "annualized_return": float, "max_drawdown": float, "sharpe_ratio": float, "alpha_vs_benchmark": float, "win_rate": float}`.