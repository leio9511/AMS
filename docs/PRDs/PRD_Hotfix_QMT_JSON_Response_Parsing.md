---
Affected_Projects: [AMS]
---

# PRD: Hotfix_QMT_JSON_Response_Parsing

## 1. Context & Problem (业务背景与核心痛点)
ISSUE-1106. In the final integration test, we discovered two payload structure issues from the Windows QMT node:
1. The QMT client returns tick data wrapped in a nested JSON structure `{"status": "success", "data": {...}}`. The original `TickGateway` implementation assumed a flat dictionary and failed to parse it.
2. The QMT tick payload uses the exact key `lastPrice` instead of `price`. The `ETFArbStrategy` failed to extract the price correctly.
These fixes must be implemented properly through the SDLC pipeline to maintain code integrity and auditability.

## 2. Requirements & User Stories (需求定义)
- **Functional Requirements:**
  - Modify `engine/gateway.py`'s `poll_once` method to correctly unpack the `{"status": "success", "data": {...}}` JSON envelope returned by the API.
  - Modify `strategies/etf_arb.py`'s `on_tick` method to extract the price using the `lastPrice` key.
- **Non-Functional Requirements:**
  - Ensure the gateway is backwards compatible with the flat dictionary format if possible, to prevent test breakages.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- Update the parsing logic in `TickGateway.poll_once` to safely retrieve `.get("data", response)` assuming it might be wrapped.
- Update the dictionary `.get("lastPrice")` lookup in the strategy's `on_tick` handler.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Gateway Unpacking**
  - **Given** a mock QMTClient returning `{"status": "success", "data": {"510300.SH": {"lastPrice": 4.6}}}`
  - **When** `gateway.poll_once(engine)` is called
  - **Then** an Event is pushed to the engine containing `{"code": "510300.SH", "lastPrice": 4.6}`.
- **Scenario 2: Strategy Price Extraction**
  - **Given** an `Event` payload containing `{"code": "510300.SH", "lastPrice": 4.6, "iopv": 1.0}`
  - **When** `on_tick` is called in `ETFArbStrategy`
  - **Then** it correctly extracts the price and processes the premium.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- Ensure existing tests in `tests/test_etf_arb.py` are updated to send `lastPrice` instead of `price` in the mock Event data.

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。

- **Gateway Parsing Logic (For `engine/gateway.py`)**:
```python
    def poll_once(self, engine, code_list=None):
        response = self.qmt_client.get_full_tick(code_list)
        # Handle both raw dict or success-wrapped dict
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
                event = Event(type=EVENT_TICK, data=data_payload)
                engine.process(event)
        else:
            print(f"Gateway poll failed: {response}")
```

- **Strategy Price Extraction (For `strategies/etf_arb.py`)**:
```python
    def on_tick(self, event):
        data = event.data
        code = data.get("code")
        price = data.get("lastPrice") # QMT full_tick uses lastPrice
        iopv = data.get("iopv", 1.0) 
        
        if price is not None and iopv is not None:
            premium = self.calculate_premium(price, iopv)
            if premium > 0.02:
                print(f"!!! SIGNAL: {code} premium is {premium*100:.2f}% (> 2%)")
```