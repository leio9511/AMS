---
Affected_Projects: [AMS]
---

# PRD: Hotfix_Migrate_AkShare_to_QMTClient

## 1. Context & Problem (业务背景与核心痛点)
During the UAT phase of `PRD_Migrate_AkShare_to_QMTClient_for_Radar`, two critical issues were discovered:
1. **Endpoint Mismatch**: `QMTClient.get_full_tick()` attempts to call `GET /api/bulk_quote`, but the Windows Bridge server actually exposes a dynamic execution endpoint at `POST /api/xtdata_call`.
2. **Missing HK Shares Implementation**: The Coder Agent bypassed the HK shares implementation (`get_stock_hk_spot_em()`) in `QMTDataAdapter`, leaving it returning an empty DataFrame with a hardcoded comment. This fails the original requirement.

## 2. Requirements & User Stories (需求定义)
- **Functional Requirements:**
  - Update `QMTClient` to use the `POST /api/xtdata_call` endpoint instead of `GET /api/bulk_quote`.
  - Implement `get_stock_hk_spot_em()` in `QMTDataAdapter` so it returns a `pandas.DataFrame` mirroring the exact schema of the A-share method, parsing the HK data from `QMTClient.get_full_tick()`.
- **Non-Functional Requirements:**
  - High reliability and exact match with previous `akshare` schemas.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **QMTClient Fix**: Modify `get_full_tick(self, code_list=None)` in `QMTClient` to make a `POST` request to `/api/xtdata_call` with a dynamically constructed JSON payload (e.g. `{"method": "get_full_tick", "args": [code_list] if code_list else [], "kwargs": {}}`). Since the API returns `{"status": "success", "data": <result>}`, we need to extract and return the `data` field.
- **QMTDataAdapter Fix**: 
  - Update `get_stock_zh_a_spot_em()` to strictly filter out HK stocks by ensuring the stock code does NOT end with `.HK`.
  - Implement `get_stock_hk_spot_em()` by reusing the data transformation logic but STRICTLY filtering the raw JSON response to only include keys where `code.endswith('.HK')`.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Fetching full tick data via the correct endpoint**
  - **Given** the remote Windows QMT bridge is active
  - **When** `QMTClient.get_full_tick()` is called
  - **Then** it sends a POST request to `/api/xtdata_call` with the correct JSON payload
  - **And** it successfully extracts and returns the `data` dictionary from the response.

- **Scenario 2: Fetching HK Spot Data**
  - **Given** the adapter is called for HK shares
  - **When** `QMTDataAdapter.get_stock_hk_spot_em()` is executed
  - **Then** it returns a populated DataFrame using the exact same `FIELD_MAPPING` as the A-shares method.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Mocking**: Update unit tests for `QMTClient` to mock the `POST` request and simulate the `{"status": "success", "data": {...}}` response.
- **Adapter tests**: Add unit tests explicitly validating `get_stock_hk_spot_em()`.

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。

- **QMTClient POST Payload Template & Strings (For `qmt_client.py`)**:
```python
# The endpoint must exactly match this string:
ENDPOINT = "/api/xtdata_call"

# The dynamically constructed payload MUST use these exact keys:
payload_template = {
    "method": "get_full_tick",
    "args": [],  # Populate with actual arguments dynamically
    "kwargs": {}
}

# The expected response dict keys MUST exactly match:
# {"status": "success", "data": ...}
```

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

- **Stock Market Filtering Logic (For `qmt_data_adapter.py`)**:
```python
# For get_stock_zh_a_spot_em()
if code.endswith('.HK'):
    continue

# For get_stock_hk_spot_em()
if not code.endswith('.HK'):
    continue
```