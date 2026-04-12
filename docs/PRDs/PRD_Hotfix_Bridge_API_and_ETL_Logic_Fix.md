---
Affected_Projects: [AMS]
---

# PRD: Hotfix_Bridge_API_and_ETL_Logic_Fix

## 1. Context & Problem (业务背景与核心痛点)
ISSUE-1109. During the final E2E test of Phase 5, the following critical bugs were identified:
1. **API Endpoint Mismatch**: The `TickGateway` calls `/api/xtdata_call`, but the Windows `server.py` bridge only implements `/api/bulk_quote` and `/api/fundamentals`. This causes a 404 error.
2. **ETL Logic Bug**: The `finance_batch_etl.py` script fails with a `ValueError: The truth value of a DataFrame is ambiguous` when checking `if capital_data`.
3. **Robustness**: The `main_runner.py` crashes on network errors instead of failing gracefully.

## 2. Requirements & User Stories (需求定义)
- **Functional Requirements:**
  - Standardize the Windows `server.py` to support the `/api/xtdata_call` endpoint as expected by the `QMTClient`.
  - Fix the pandas check in `finance_batch_etl.py` to use `.empty` or explicit length checks.
  - Add try-except blocks in `main_runner.py` to prevent a total crash if the Windows bridge is temporarily unavailable.
- **Non-Functional Requirements:**
  - Maintain the "Stateless Gateway" principle.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Server Update (Secure RPC & Whitelisting)**: Modify `windows_bridge/server.py` to add the `@app.post('/api/xtdata_call')` route. Crucially, the method execution must be restricted by a hardcoded `ALLOWED_METHODS` list (e.g., `["get_full_tick", "get_market_data"]`). Any request outside this list must be rejected with a 403.
- **ETL Update**: Fix `finance_batch_etl.py` to use `if capital_data is not None and not capital_data.empty:` instead of `if capital_data:`.
- **Runner Update (Exponential Backoff)**: Add an exponential backoff retry mechanism (e.g., retrying up to 3 times with increasing delays) in `main_runner.py` for `gateway.update_fundamentals()` and `gateway.poll_once()`.
- **Rollback Strategy**: Since we are modifying the core Windows bridge, `deploy_to_windows.py` should be updated (or used carefully) so that if the new `server.py` crashes on startup, the old version can be easily reverted. The testing will isolate changes in mock layers before deployment.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: API Endpoint Resolution (Happy Path)**
  - **Given** the updated `server.py` running on Windows
  - **When** `QMTClient` sends a POST to `/api/xtdata_call` with `method="get_full_tick"`
  - **Then** it returns a success status with the expected tick data.
- **Scenario 2: API Endpoint Whitelist Security (Unhappy Path)**
  - **Given** the updated `server.py` running on Windows
  - **When** a malicious payload sends a POST to `/api/xtdata_call` with `method="os.system"` or an unregistered `xtdata` method
  - **Then** the server forcefully rejects the request and returns a `403 Method not allowed` status.
- **Scenario 3: Runner Network Resilience (Unhappy Path)**
  - **Given** the Windows bridge is temporarily down (returning 502/Timeout)
  - **When** `main_runner.py` attempts to update fundamentals or poll
  - **Then** it does not crash immediately, but triggers the exponential backoff retry mechanism, logging each retry attempt.
- **Scenario 4: ETL Execution**
  - **When** `finance_batch_etl.py` is executed on Windows with an empty DataFrame
  - **Then** it completes without `ValueError: The truth value of a DataFrame is ambiguous`.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- Update mock tests to simulate the new `/api/xtdata_call` endpoint.

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。

- **Windows Server Fix (For `windows_bridge/server.py`)**:
```python
ALLOWED_METHODS = {"get_full_tick", "get_market_data", "get_instrument_detail"}

@app.post('/api/xtdata_call')
async def xtdata_call(request: dict):
    method = request.get('method')
    args = request.get('args', [])
    kwargs = request.get('kwargs', {})
    
    if method not in ALLOWED_METHODS:
        raise HTTPException(status_code=403, detail="Method not allowed")
        
    try:
        from xtquant import xtdata
        func = getattr(xtdata, method)
        res = func(*args, **kwargs)
        return {"status": "success", "data": res}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

- **ETL Fix (For `windows_bridge/finance_batch_etl.py`)**:
```python
if capital_data is not None and not capital_data.empty:
    # process logic
```