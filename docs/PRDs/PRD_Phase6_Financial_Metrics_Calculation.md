---
Affected_Projects: [AMS]
---

# PRD: Phase6_Financial_Metrics_Calculation

## 1. Context & Problem (业务背景与核心痛点)
ISSUE-1110. In Phase 5, the data pipeline successfully merged cached fundamental data into high-frequency ticks. However, the ETL script `finance_batch_etl.py` currently only extracts `total_capital` and `net_profit` for A-shares. It lacks the coverage to pull fundamentals for ETFs and Convertible Bonds, and the strategies downstream are using fallback values or missing metrics entirely. To maintain strict **Hot/Cold Data Separation**, the ETL script must remain a pure source of cold data (shares, equity, profits), while the strategies must be upgraded to dynamically compute real-time metrics (like Dynamic PE) using the incoming fast stream (Tick Price) combined with the cached cold stream.

## 2. Requirements & User Stories (需求定义)
- **Functional Requirements:**
  - Update `main()` in `finance_batch_etl.py` to fetch `沪深ETF` and `沪深转债` stock lists in addition to `沪深A股`.
  - Update `strategies/crystal_fly.py` to calculate Dynamic PE on the fly: `pe = (price * total_capital) / net_profit` when profit > 0.
  - Remove the fallback `1.0` for `iopv` in `strategies/etf_arb.py`.
- **Non-Functional Requirements:**
  - Strict Data Separation: The Windows JSON must NEVER cache fast-moving data like `lastPrice` or `iopv`.
  - Prevent division by zero when calculating dynamic metrics in the strategy layer.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Cold Data Expansion**: The Windows ETL script processes stocks in chunks. It will now pull all three asset classes into the fundamental JSON, extracting only static financial tables.
- **Hot Metric Calculation (Strategy Layer)**: The `CrystalFlyStrategy` will act as a real-time calculator. When an `EVENT_TICK` arrives, it extracts the hot `lastPrice` and the cold `total_capital`/`net_profit` from the event payload. It computes the Dynamic PE in memory and makes the signal decision.
- **Strategy Safety**: The ETF strategy will explicitly check for `iopv is not None` instead of defaulting to `1.0`, ensuring it only fires when true real-time net value data is present in the tick.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: ETL List Expansion**
  - **Given** QMT returns A-shares, ETFs, and CBs
  - **When** `finance_batch_etl.py` processes the lists
  - **Then** the generated JSON contains coverage for all three asset classes with static fundamental data.
- **Scenario 2: Strategy Dynamic PE Calculation**
  - **Given** an `EVENT_TICK` payload containing `{"code": "600519.SH", "lastPrice": 10.0, "total_capital": 100.0, "net_profit": 50.0}`
  - **When** `CrystalFlyStrategy.on_tick` is called
  - **Then** it calculates PE as 20.0 dynamically and evaluates the threshold.
- **Scenario 3: Strategy Fallback Removal**
  - **Given** an ETF tick without `iopv`
  - **When** `ETFArbStrategy.on_tick` is called
  - **Then** it ignores the event instead of calculating a false premium using `1.0`.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- Update unit tests in `tests/test_etf_arb.py` to verify that `iopv=None` does not trigger a signal.

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。

- **ETL Main Update (For `windows_bridge/finance_batch_etl.py`)**:
```python
def main():
    if not xtdata:
        return
    a_shares = xtdata.get_stock_list_in_sector('沪深A股')
    etfs = xtdata.get_stock_list_in_sector('沪深ETF')
    cbs = xtdata.get_stock_list_in_sector('沪深转债')
    
    stock_list = list(set(a_shares + etfs + cbs))
    fundamentals = process_financial_data(stock_list)
    
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(fundamentals, f, ensure_ascii=False, indent=2)
```

- **CrystalFly Dynamic PE Calculation (For `strategies/crystal_fly.py`)**:
```python
    def on_tick(self, event):
        data = event.data
        code = data.get("code")
        price = data.get("lastPrice")
        total_capital = data.get("total_capital")
        net_profit = data.get("net_profit")
        
        pe = None
        if price is not None and total_capital is not None and net_profit is not None and net_profit > 0:
            pe = (price * total_capital) / net_profit
            
        if code and pe is not None:
            if self.check_fundamentals(pe):
                print(f"SIGNAL: {code} passed fundamental screening (PE: {pe:.2f})")
```

- **Strategy Fix (For `strategies/etf_arb.py`)**:
```python
    def on_tick(self, event):
        data = event.data
        code = data.get("code")
        price = data.get("lastPrice") # QMT full_tick uses lastPrice
        iopv = data.get("iopv") 
        
        if price is not None and iopv is not None:
            premium = self.calculate_premium(price, iopv)
            if premium > 0.02:
                print(f"!!! SIGNAL: {code} premium is {premium*100:.2f}% (> 2%)")
```