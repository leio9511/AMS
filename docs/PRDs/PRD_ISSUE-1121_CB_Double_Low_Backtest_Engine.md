---
Affected_Projects: [AMS]
---

# PRD: QMT-based Offline Convertible Bond Double-Low Backtest Engine

## 1. Context & Problem (业务背景与核心痛点)
The existing convertible bond (CB) rotation strategies suffer from "survivorship bias" when fetching data from simple web APIs, as delisted or defaulted bonds are usually missing. Furthermore, web APIs limit historical data queries for "premium rates," which are crucial for CB strategies. A pure, accurate 1-year backtest requires querying local QMT historical data to reconstruct the daily conversion premium and test advanced "Best Practice" strategies (e.g., dynamic thresholds, momentum enhancement, high dispersion, and weekly rotation) without distortion.

## 2. Requirements & User Stories (需求定义)
- **Goal 1 (Data ETL)**: The engine must extract raw OHLCV and fundamental data (including conversion price history if possible, or robust proxies) from QMT's `xtdata` local cache to reconstruct historical daily premium rates for the entire CB universe (including dead bonds).
- **Goal 2 (Best Practice Filters)**: The strategy engine must implement dynamic watermarks (e.g., dynamically selecting the bottom 30% of price and premium rather than hardcoded 130/30%), and strictly filter out high-risk bonds (ST, delisting, announced forced redemptions, scale < 0.5 billion).
- **Goal 3 (Momentum & Dispersion)**: Enhance the "Double-Low" multi-factor rank with a momentum factor (e.g., 20-day turnover or underlying stock momentum). Enforce a highly dispersed portfolio (e.g., 15-20 holdings, equal weight).
- **Goal 4 (Execution)**: Implement a weekly rotation logic (e.g., rebalance every Friday at close or Monday at open) to simulate realistic trading and minimize friction costs. Calculate metrics including Alpha against the CSI Convertible Bond Index (000832).

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Data Layer (`cb_data_loader.py`)**: A script designed to run on the Windows QMT node (or fetch via SSH). It uses `xtdata.download_history_data2` to pull all CBs. 
  - **Historical Premium & Scale Resolution**: Since QMT's `xtdata` OHLCV does not contain Point-in-Time (PiT) Corporate Action data (forced redemption dates, exact historical conversion prices, or daily outstanding scale), the script MUST integrate with an external data source like `Akshare` (`ak.bond_cb_jsl` / `ak.bond_zh_hs_cov_daily` or similar historical valuation APIs) to fetch the accurate historical conversion prices, scale, and forced-redemption announcement dates.
  - The script will merge QMT's accurate pricing with the external fundamental timeline to reconstruct the PiT daily premium rates (`close / (100 / pit_conversion_price * stock_close) - 1`) and save a flattened historical dataset (e.g., Parquet or JSON).
- **Backtest Layer (`cb_backtest_engine.py`)**: A Python-based vectorized or iterative backtest engine.
  - *Scoring*: `Rank(Price) + Rank(Premium) - Rank(Turnover)`
  - *Rebalancing*: Resample data to weekly (`W-FRI`). Generate target weights.
  - *Accounting*: Calculate portfolio value, apply a realistic two-way friction cost (e.g., 0.1% or 0.2%), and output a performance tear sheet.
- **Integration**: The engine should output results locally and be callable via CLI for rapid parameter tuning.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Accurate Historical ETL**
  - **Given** The QMT node with downloaded history
  - **When** `cb_data_loader.py` is executed
  - **Then** It generates a continuous historical dataset that includes delisted bonds (preventing survivorship bias) and correctly calculated premium rates.
- **Scenario 2: Weekly Rotation Execution**
  - **Given** A 1-year dataset
  - **When** The backtest engine is run with 20 holdings and weekly frequency
  - **Then** It logs exactly one rebalancing event per week, deducts trading costs properly, and calculates the final portfolio NAV and benchmark Alpha.
- **Scenario 3: Risk Filtering**
  - **Given** A specific date where a bond announced forced redemption or dropped below 30 million in scale
  - **When** The engine screens candidates for that week
  - **Then** The risky bond is completely excluded from the candidate pool.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Test Strategy**: 
  - Mock a small dataset of 5 bonds (including 1 that delists halfway) to unit test the survivorship bias handling.
  - Validate the weekly turnover calculation ensures costs are only deducted on changed weights, not the whole portfolio.
- **Quality Goal**: Ensure robust handling of missing data. The engine must not crash if a bond halts trading on a rebalance day.

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
- Benchmark Index: `000832.SH` (中证转债)
- Max Holdings: `20`
- Rebalance Frequency: `Weekly (Friday)`