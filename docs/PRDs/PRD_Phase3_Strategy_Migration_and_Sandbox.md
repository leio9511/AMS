---
Affected_Projects: [AMS]
---

# PRD: Phase3_Strategy_Migration_and_Sandbox

## 1. Context & Problem (业务背景与核心痛点)
ISSUE-1104. In Phase 1, we established the core stateless `EventEngine`. In Phase 2, we built the financial ETL on Windows to supply pre-market fundamental data. Now, in Phase 3, we must migrate the actual business logic from the procedural legacy scripts (`legacy_scripts/etf_tracker.py`, `legacy_scripts/crystal_fly_swatter.py`) into proper, encapsulated quantitative strategies that natively run on the `EventEngine`.
The problem with the old code is that it mixes data fetching, signal generation, and notification sending. We need to decouple the "brain" (Alpha/Signal logic) into a clean, pluggable Object-Oriented structure.

## 2. Requirements & User Stories (需求定义)
- **Functional Requirements:**
  - Define a generic `StrategyBase` class inside `strategies/base_strategy.py` that automatically registers lifecycle event handlers (`on_tick`, `on_timer`) to the `EventEngine`.
  - Migrate the ETF arbitrage logic into `strategies/etf_arb.py` (inheriting from `StrategyBase`).
  - Migrate the Crystal Fly Swatter fundamental screening logic into `strategies/crystal_fly.py` (inheriting from `StrategyBase`).
  - Migrate the Convertible Bond monitoring logic into `strategies/convertible_bond.py` (inheriting from `StrategyBase`).
  - The strategies must solely process data passed through the events and output actionable signals/logs (simulated for now, without directly placing trades).
- **Non-Functional Requirements:**
  - High cohesion: A strategy should only contain its own parameters and alpha logic.
  - The strategies must NOT block the event engine loop.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Object-Oriented Pluggable Architecture**:
  - The `StrategyBase` abstract base class provides the fundamental structure, exposing `start()` and `stop()` lifecycle methods, alongside an `active` boolean flag.
  - It does NOT automatically bind to specific event types in `__init__`. Instead, concrete subclasses (e.g., `ETFArbStrategy`) explicitly call `self.engine.register(EVENT_TICK, self.on_tick)` inside their overridden `start()` method, preventing race conditions during initialization.
  - **Domain Logic Separation (Fat Handler Anti-Pattern Avoidance)**: 
    - The legacy calculation logic (e.g., premium/discount formulas, fundamental filters) MUST NOT be pasted monolithically inside `on_tick` or `on_timer`.
    - Instead, calculations must be encapsulated into pure functions or isolated internal methods (e.g., `def calculate_premium(price, iopv)`) that do not depend on the `Event` object or `EventEngine`.
    - The event handlers (`on_tick`, `on_timer`) act ONLY as dispatchers: they extract payload data, pass it to the pure computation functions, and conditionally log signals based on the result.
  - For Phase 3, if a strategy detects a signal (e.g., ETF premium > 2%), it will simply `print` or log the signal (Execution and notification layers will be formalized later).

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Instantiating and Registering a Strategy**
  - **Given** an initialized `EventEngine`
  - **When** an `ETFArbStrategy` is instantiated with the engine AND `strategy.start()` is explicitly called
  - **Then** the engine's internal handler dict successfully registers the strategy's `on_tick` and `on_timer` methods.
- **Scenario 2: Triggering Strategy Logic via Events**
  - **Given** the `ETFArbStrategy` registered to the engine (after `start()` is called)
  - **When** the engine processes an `Event("eTick", {"code": "510300.SH", "price": 4.1})`
  - **Then** the strategy's `on_tick` method executes and successfully logs or processes the payload without crashing.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Testing**: 
  - Write `tests/test_strategy_base.py` to ensure `StrategyBase` correctly binds to the `EventEngine` ONLY AFTER `start()` is called, and unbinds when `stop()` is called.
  - Write mock-based tests for `etf_arb.py` and `crystal_fly.py` by feeding them dummy `Event` payloads and asserting their internal state/output without requiring network access.

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。

- **StrategyBase API Contract (For `strategies/base_strategy.py`)**:
```python
from engine.event_engine import EventEngine

class StrategyBase:
    def __init__(self, engine: EventEngine, strategy_name: str = "Base"):
        self.engine = engine
        self.strategy_name = strategy_name
        self.active = False

    def start(self):
        """Called to explicitly begin event subscription and processing."""
        self.active = True

    def stop(self):
        """Called to explicitly end event subscription and processing."""
        self.active = False
```