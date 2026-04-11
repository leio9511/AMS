---
Affected_Projects: [AMS]
---

# PRD: Migrate_AkShare_to_QMTClient_for_Radar

## 1. Context & Problem (业务背景与核心痛点)
ISSUE-1001. The current AMS monitoring scripts (specifically `pilot_stock_radar.py`) rely on `akshare` to fetch real-time market data (e.g., `ak.stock_zh_a_spot_em()`). This essentially scrapes free financial websites, which frequently triggers anti-crawling mechanisms and results in `RemoteDisconnected` errors when attempting to batch fetch 5000+ A-shares. This instability prevents the system from running reliably and acts as a blocker for any future automated trading logic. The solution is to migrate these data calls to our newly established, institutional-grade `QMTClient`, leveraging the Windows QMT bridge for robust, local tick data.

## 2. Requirements & User Stories (需求定义)
- **Functional Requirements:**
  - Replace the unreliable `akshare` real-time data fetchers for A-shares and HK shares in `pilot_stock_radar.py` with calls to `QMTClient`.
  - Introduce an "Adapter Layer" that translates the raw JSON response from QMTClient into a `pandas.DataFrame` that perfectly matches the schema previously provided by `akshare` (e.g., columns like `代码`, `名称`, `最新价`, `涨跌幅`, etc.).
  - Ensure the core screening and computational logic within `pilot_stock_radar.py` requires zero to minimal changes.
- **Non-Functional Requirements:**
  - High reliability: The data fetch process must not fail due to network scraping bans.
  - Performance: The Windows node will act as a pure data pipeline, and the Linux node will handle all DataFrame conversions and computations.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Data Flow Separation:** The Windows server provides raw JSON data via endpoints like `/api/get_full_tick`. The Linux side initiates the request.
- **Adapter Pattern (`qmt_data_adapter.py`):** Create a new module/class `QMTDataAdapter` in the AMS project. It will wrap `QMTClient`. Its method `get_stock_zh_a_spot_em()` will mimic the `akshare` API signature but source data from QMT, map the JSON fields to the legacy Chinese column names, and return a DataFrame.
- **Target Files:**
  - `src/qmt_data_adapter.py` (New): Handles QMT JSON to Pandas mapping.
  - `pilot_stock_radar.py` (Modify): Replace `import akshare as ak` with the new adapter for real-time spot data. (Keep `akshare` for low-frequency lookups like `sw_index_first_info`).

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Fetching full A-share market spot data**
  - **Given** the remote Windows QMT bridge is active and reachable
  - **When** the radar script calls the adapter to get full market spot data
  - **Then** it receives a `pandas.DataFrame` with over 4000 rows containing the expected columns (`代码`, `名称`, `最新价`, `涨跌幅`, etc.)
  - **And** no HTTP timeout or `RemoteDisconnected` connection errors occur.

- **Scenario 2: Schema compatibility with existing screening logic**
  - **Given** the new adapter returns the spot data DataFrame
  - **When** the DataFrame is passed into the existing radar screening functions (e.g., volume spikes, price breakouts)
  - **Then** the screening functions execute successfully without throwing `KeyError` or type mismatch exceptions.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Mocking:** For unit testing the `QMTDataAdapter`, mock the `QMTClient` HTTP response with a static, pre-recorded JSON sample of a QMT tick response. This isolates the Adapter logic from the network and the Windows node.
- **Schema Validation:** Unit tests must explicitly assert that the DataFrame output by the Adapter contains the exact column names expected by the legacy `akshare` code.
- **Integration Testing:** Create an integration test script that connects to the live Windows bridge to verify end-to-end data fetching and DataFrame creation.

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**

- **QMT to AkShare Field Mapping (For `qmt_data_adapter.py`)**:
```python
FIELD_MAPPING = {
    "stock_code": "代码",
    "stock_name": "名称",
    "lastPrice": "最新价",
    "open": "今开",
    "high": "最高",
    "low": "最低",
    "preClose": "昨收",
    "volume": "成交量",
    "amount": "成交额",
    "changePercent": "涨跌幅"
}
```