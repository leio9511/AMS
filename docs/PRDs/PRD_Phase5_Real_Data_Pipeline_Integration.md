---
Affected_Projects: [AMS]
---

# PRD: Phase5_Real_Data_Pipeline_Integration

## 1. Context & Problem (业务背景与核心痛点)
ISSUE-1108. The AMS v2.0 EventEngine and Strategies (ETF, Convertible Bond, Crystal Fly) are fully functional, but they currently operate on partial data. The QMT `get_full_tick` endpoint provides `lastPrice`, but the strategies require additional contextual data to calculate accurate signals:
1. `iopv` for ETFs to calculate premium.
2. `conv_value` (convertible value) for Convertible Bonds to calculate discount.
3. `pe` (Price-to-Earnings) for Crystal Fly fundamental screening.
In Phase 2, we built `/api/fundamentals` on the Windows node to serve fundamental data. We must now upgrade `QMTClient` and `TickGateway` to fetch these supplementary datasets and merge them into the `EVENT_TICK` payload.

## 2. Requirements & User Stories (需求定义)
- **Functional Requirements:**
  - Update `scripts/qmt_client.py` (`QMTClient`) to include a new method `get_fundamentals()` that fetches data from the Windows node's `/api/fundamentals` endpoint.
  - Update `engine/gateway.py` (`TickGateway`) to introduce an in-memory cache and a new method `update_fundamentals()` to populate it.
  - Merge the cached fundamental data (e.g., `pe`, `iopv`, `conv_value`) into the tick data dictionary during `poll_once` purely in memory.
  - Update `main_runner.py` to call `gateway.update_fundamentals()` ONCE before entering the polling phase.
- **Non-Functional Requirements:**
  - Fast/Slow Decoupling: `poll_once` must NEVER make synchronous HTTP calls for fundamentals.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Fast/Slow Stream Decoupling (In-Memory Snapshot)**: The system must NEVER make synchronous HTTP calls for slow-changing fundamental data inside the high-frequency `poll_once` hot path.
- `TickGateway` will maintain an internal state `self.fundamentals_cache`.
- A new method `update_fundamentals(self)` will be introduced to fetch data from `/api/fundamentals` and populate the cache. This is meant to be called infrequently (e.g., once at startup by `main_runner.py`).
- **O(1) Memory Merge**: `poll_once` will fetch only the high-frequency tick data and merge it with the existing `self.fundamentals_cache` purely in memory. 
- **Resilience**: If `update_fundamentals()` fails, the cache remains as previously set (or empty), allowing `poll_once` to continue dispatching ticks safely without crashing.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Fundamental Data Fetching into Cache**
  - **Given** an initialized `TickGateway`
  - **When** `update_fundamentals` is called
  - **Then** `gateway.fundamentals_cache` successfully stores the parsed dictionary.
- **Scenario 2: O(1) Memory Merging in Gateway**
  - **Given** `gateway.fundamentals_cache` contains `{"510300.SH": {"iopv": 4.4, "pe": 15.0}}`
  - **When** `poll_once` fetches tick data `{"510300.SH": {"lastPrice": 4.6}}`
  - **Then** the engine receives an event with `{"code": "510300.SH", "lastPrice": 4.6, "iopv": 4.4, "pe": 15.0}` without any additional network calls.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- Write unit tests for `TickGateway.poll_once` validating that it correctly pulls from the `fundamentals_cache` during Event creation.
- Verify `main_runner.py` is updated to call `gateway.update_fundamentals()` before `poll_once`.

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。

- **Gateway Merging Logic (For `engine/gateway.py`)**:
```python
class TickGateway:
    def __init__(self, qmt_client=None):
        self.qmt_client = qmt_client or QMTClient()
        self.fundamentals_cache = {}

    def update_fundamentals(self):
        try:
            response = self.qmt_client.get_fundamentals()
            if isinstance(response, dict):
                self.fundamentals_cache = response.get("data", response) if response.get("status") == "success" else response
        except Exception as e:
            print(f"Failed to update fundamentals cache: {e}")

    def poll_once(self, engine, code_list=None):
        response = self.qmt_client.get_full_tick(code_list)
        if isinstance(response, dict):
            tick_data = response.get("data", response) if response.get("status") == "success" else response
            if not isinstance(tick_data, dict):
                print(f"Gateway poll failed, unexpected data type: {type(tick_data)}")
                return
            
            for code, tick in tick_data.items():
                if code in ["status", "data"]: continue
                data_payload = {"code": code}
                if isinstance(tick, dict):
                    data_payload.update(tick)
                else:
                    data_payload["data"] = tick
                
                # O(1) In-memory merge from cache
                if code in self.fundamentals_cache and isinstance(self.fundamentals_cache[code], dict):
                    data_payload.update(self.fundamentals_cache[code])

                event = Event(type=EVENT_TICK, data=data_payload)
                engine.process(event)
        else:
            print(f"Gateway poll failed: {response}")
```

- **Runner Update (For `main_runner.py`)**:
```python
    logger.info("Strategies started. Fetching fundamentals snapshot...")
    gateway.update_fundamentals()
    
    logger.info("Polling gateway once...")
    gateway.poll_once(engine)
```