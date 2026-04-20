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
