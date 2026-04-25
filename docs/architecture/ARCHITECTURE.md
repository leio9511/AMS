# AMS Architecture & Methodology

This document outlines the core architectural patterns and methodologies that govern the AMS v2.0 framework.

## 1. The "CD Player" Pattern (Dependency Injection)

AMS uses a highly decoupled architecture to ensure maximum extensibility. Think of the `BacktestRunner` as a **CD Player**. It doesn't care what music is playing, it just spins the disc and outputs sound to the speakers.

### The 4 Core Components (Abstract Base Classes):
In our codebase (`ams/core/base.py`), these components are strictly defined as Python Abstract Base Classes (`abc.ABC`). Any new plugin **must** inherit from these base classes and implement their abstract methods.

1. **The CD Player (Runner)**: `BacktestRunner` / `LiveRunner`. Manages the time loop and triggers events.
2. **The CD (DataFeed)**: Inherits `BaseDataFeed`. Provides the raw data (the music tracks) via `get_data()`.
3. **The Decoder Chip (Strategy)**: Inherits `BaseStrategy`. Parses the data via `generate_target_portfolio()` and decides what to buy/sell.
4. **The Speakers (Broker)**: Inherits `BaseBroker`. Takes the buy/sell signals and executes them via `order_target_percent()`.

### How to Extend to a New Strategy (The Plugin System):
You do **not** rewrite the Runner or the Broker. You simply create new plugins by inheriting the base classes:
```python
# ams/core/etf_strategy.py
from ams.core.base import BaseStrategy

class ETFAbitrageStrategy(BaseStrategy):  # Must inherit BaseStrategy
    def generate_target_portfolio(self, context, data):
        # Your custom logic here
        return {"510300": 0.5, "510500": 0.5}
```

Then, inject them into the Runner:
```python
# 1. New DataFeed
feed = HistoryDataFeed("data/etf_history_factors.csv") 

# 2. New Strategy Plugin
strategy = ETFAbitrageStrategy() 

# 3. Reuse the existing Broker and Runner!
broker = SimBroker(initial_cash=1000000.0)
runner = BacktestRunner(feed, broker, strategy)
runner.run()
```

## 2. Data Contracts & Observability

Garbage data permanently ruins backtests. AMS treats data integrity as a first-class citizen.

### Convertible-Bond Source Contract Repair Baseline
For the convertible-bond research dataset, AMS now treats upstream source contracts as an explicit architectural layer rather than an ETL implementation detail.

- `underlying_ticker` must come from `bond.CONBOND_BASIC_INFO.company_code`, not `get_security_info(ticker).parent`.
- `premium_rate` must be joined through the canonical normalized key `bond_code_raw + bond_exchange_code + date` against `bond.CONBOND_DAILY_CONVERT`.
- `is_redeemed` must derive from `bond.CONBOND_BASIC_INFO.delist_Date`, not `finance.CCB_CALL`.
- In this first deterministic redemption contract, `maturity_date`, `last_cash_date`, and `convert_end_date` are fallback informational fields only. They are explicitly documented for future lifecycle observability, but they do not override the rule that `delist_Date` is the only decision field and `delist_Date = null` keeps `is_redeemed = False`.
- The ETL metrics artifact at `/root/projects/AMS/data/cb_history_factors.metrics.json` is the observability surface for source-contract health, and currently must expose:
  - `premium_rate_source_row_count`
  - `premium_rate_joined_row_count`
  - `premium_rate_join_coverage_ratio`
  - `is_redeemed_missing_delist_count`

These source-contract guarantees are the prerequisite input layer for later dataset governance hardening under ISSUE-1142.

### The "Data Circuit Breaker"
Before any ETL script (e.g., fetching historical quotes) saves data to disk, it **MUST** pass through a Data Contract Validator (e.g., `ams.validators.cb_data_validator`).
- **Pandera Schema**: We use `pandera` to declare strict schemas (e.g., `premium_rate` must be between -10.0 and 100.0, no NaNs allowed).
- **Fail-Fast**: If the upstream API returns corrupted data, the Validator will throw a `SchemaError` and halt the pipeline *before* the golden dataset is overwritten.

## 3. Strict Point-in-Time (PiT) Adherence
To prevent **Look-ahead Bias (未来函数)**, historical data must strictly reflect what was knowable at that exact second in history.
- Example: A Convertible Bond's `is_redeemed` status must be triggered by its `pub_date` (Announcement Date), not its `delisting_date` (which is known weeks in advance).

## 4. Directory Definitions

To maintain architectural integrity, the repository strictly adheres to the following directory responsibilities:

- `ams/`: Core Strategy, Runner, and Broker logic (Event-Driven).
- `etl/`: Data acquisition and processing pipelines (Production). All ETL scripts reside here.
- `data/`: Standardized CSV datasets.
- `scripts/`: Legacy 1.0 scripts and experimental tools (Deprecated).

## 5. Validation Strategy & Quant QA

AMS is not validated by static code correctness alone. A backtesting system can appear operational while silently drifting in execution logic, parameter mapping, reporting, or data handling. For that reason, AMS adopts layered validation.

### 5.1 Validation Layers
1. **Data Contract Validation**
   - Validate schema, nullability, price ranges, and required fields before datasets are accepted.
   - Purpose: block corrupted or structurally invalid datasets from entering research or regression flows.

2. **Smoke Test**
   - A real, no-mock execution of the primary CLI path (`main_runner.py`) against a small fixture dataset.
   - Purpose: ensure the unified entrypoint is truly executable, with correct parameter routing across CLI, strategy, runner, broker, and reporting.

3. **Golden Regression Test**
   - Run a fixed strategy on a fixed golden dataset and compare against stable expected outputs or checkpoints.
   - Purpose: detect silent drift in execution logic, financial metrics, or reporting output.

4. **Research Validation**
   - Walk-forward / out-of-sample validation for strategy robustness.
   - Purpose: reduce overfitting and verify that an edge survives beyond a single historical regime.

### 5.2 Canonical Paths
The canonical AMS runtime paths are:
- Code root: `/root/projects/AMS`
- Historical CB dataset: `/root/projects/AMS/data/cb_history_factors.csv`

Production backtests and formal validation should use these canonical paths unless a fixture-based test explicitly overrides them.

### 5.3 Release Gate Before Live QMT
Before entering Phase 2 (Live QMT Integration), AMS must satisfy:
- The unified CLI backtest path is operational.
- A real smoke test passes.
- At least one strategy (`cb_rotation`) has a golden regression baseline.
- Validation framework requirements are documented and enforced in preflight/CI.
- ISSUE-1142 is a blocking issue for AMS Phase 2. AMS must not enter Live QMT Integration until /root/projects/AMS/data/cb_history_factors.csv is the unique canonical CB research/backtest dataset and the semantic quality gates defined in this PRD are enforced.
