---
Affected_Projects: [AMS]
---

# PRD: Phase1_Core_Engine_and_Legacy_Archive

## 1. Context & Problem (业务背景与核心痛点)
ISSUE-1102. As the first phase of the Epic AMS v2.0 Event-Driven Architecture Refactoring (ISSUE-1101), we need to establish the foundational micro-kernel event bus. The current AMS codebase consists of unstructured procedural scripts. To prepare for pluggable quantitative strategies (ETF, Convertible Bonds, Stock Screening), we must restructure the directories, archive the old procedural scripts to a legacy folder, and introduce a highly decoupled `EventEngine` based on standard quantitative best practices (inspired by `vn.py`).

## 2. Requirements & User Stories (需求定义)
- **Functional Requirements:**
  - Create the new folder structure: `engine/`, `strategies/`, `data_adapters/`, `legacy_scripts/`.
  - Move the existing procedural scripts (`etf_tracker.py`, `crystal_fly_swatter.py`, `pilot_stock_radar.py`) into `legacy_scripts/` so their business logic can be referenced later without cluttering the new architecture.
  - Implement `EventEngine` in `engine/event_engine.py` using a simple pub/sub pattern (handlers list mapped to event types).
  - Implement a basic `TickGateway` in `engine/gateway.py` that wraps the existing `qmt_client` and pushes tick data into the `EventEngine` as tick events.
- **Non-Functional Requirements:**
  - No new complex external dependencies.
  - The EventEngine MUST be stateless and synchronous. It must strictly adhere to the OpenClaw Native Manifesto by avoiding ANY background threads, `queue.Queue`, `time.sleep()`, or `while True` loops.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Strangler Pattern**: We will not delete the old scripts; they move to `legacy_scripts/`.
- **Event-Driven Architecture (EDA)** (Stateless Dispatcher pattern):
  - An `Event` class with a `type` string and a `data` dictionary payload.
  - `EventEngine` acts as a pure stateless dispatcher. It manages a `dict` mapping event types to handler functions.
  - Exposes `register`, `unregister`, and `process(event)` methods. The `process` method simply iterates over registered handlers for that event type and executes them immediately.
  - `gateway.py` exposes a `poll_once(engine)` function. It uses `QMTClient` to fetch a single snapshot of `get_full_tick()`, wraps the data in an `Event`, and directly calls `engine.process(event)`.
  - All looping and continuous execution will be handled EXTERNALLY by the Agent runtime (e.g. background exec scripts), NOT within the Python application logic.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Directory Restructuring**
  - **Given** the AMS project root
  - **When** the SDLC completes
  - **Then** `engine/`, `strategies/`, and `legacy_scripts/` exist, and old scripts are inside `legacy_scripts/`.
- **Scenario 2: Event Dispatching**
  - **Given** an instantiated `EventEngine`
  - **When** a dummy handler is registered for "TICK" and `engine.process(Event(type="TICK", data={"price": 10}))` is called
  - **Then** the dummy handler is executed and receives the data payload.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Testing**: Write `test_event_engine.py` to verify pub/sub functionality, registration, and dispatching.
- **Gateway Testing**: Mock `QMTClient.get_full_tick()` and assert that the gateway correctly transforms the dictionary response into multiple `Event` objects pushed to the engine.

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。

- **Event Constants (For `engine/event_engine.py`)**:
```python
EVENT_TICK = "eTick"
EVENT_TIMER = "eTimer"
```

- **Core Event Class Template (For `engine/event_engine.py`)**:
```python
class Event:
    def __init__(self, type: str, data: dict = None):
        self.type = type
        self.data = data if data else {}
```

- **Directory Structure Requirements**:
The following directories MUST exactly match these names:
```text
engine/
strategies/
data_adapters/
legacy_scripts/
```
