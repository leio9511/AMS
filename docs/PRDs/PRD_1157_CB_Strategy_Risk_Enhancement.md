---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: 1157_CB_Strategy_Risk_Enhancement

## 1. Context & Problem (业务背景与核心痛点)
当前 AMS 2.0 已完成历史回测引擎的雏形，但在向实盘（Live QMT接管）演进的过程中，暴露出严重的“玩具脚本”架构缺陷：
1. **指令与撮合未解耦 (Signal-Execution Coupling)**：目前通过修改“目标权重”来控制仓位，无法真实表达限价单（Limit Order）与条件单，导致无法实现盘内精确的触价止盈/止损（Take-Profit/Stop-Loss）。在日终打分阶段偷看 `high` 价格是严重的未来函数。
2. **缺乏标准订单簿 (Missing OrderBook)**：`BacktestRunner` 越权参与了交易结算，构成了 God Object 反模式。这导致回测逻辑无法平滑过渡到实盘。
3. **极度暴雷事件惩罚模拟不足**：退市等极度流动性枯竭事件缺乏独立的滑点/折损评估模型。
4. **资金再分配机制不灵活**：周频轮动中途退出的资金缺乏“持币等周末（Hold in Cash）”或“立刻递补”的机制支持。

## 2. Requirements & User Stories (需求定义)
1. **订单驱动架构升级 (Order-Driven Architecture Upgrade)**：引入标准 `Order` 对象。`SimBroker` 必须升级为包含 `OrderBook` 的虚拟券商，完全接管撮合逻辑，通过接收限价/条件单来实现日内精准止盈。
2. **策略信号层剥离 (Strategy Decoupling)**：策略基类提供 `order_target_percent` 等辅助函数（PMS角色），自动将目标权重转换为具体 `Order` 提交给 Broker。策略层禁止直接干预 Broker 资金池，杜绝未来函数。
3. **参数化配置 (Strategy Parameters)**：支持 `rebalance_period` (`daily`/`weekly`) 与 `reinvest_on_risk_exit` 控制资金留存；支持生成限价止盈单。
4. **滑点模型注入 (SlippageModel Injection)**：抽象独立滑点模型注入 `SimBroker`，在订单结算时由滑点模型决定最终成交价或直接拒单。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **ams/core/order.py (New)**: 定义 `Order` 数据结构（包含 ticker, direction, quantity, order_type [MARKET, LIMIT], limit_price, status）。
- **ams/core/sim_broker.py**:
  - 引入内部 `OrderBook` 队列。
  - 新增 `match_orders(bar_data)` 方法。接收每日/每分钟的 OHLC 数据，遍历 OrderBook：若 `high` 穿透 Limit Sell 价格，则按 `limit_price` 撮合成交并更新资金。
  - 构造函数注入 `slippage_model: BaseSlippageModel`，在市价单或特定结算时调用计算最终滑点。
- **ams/core/cb_rotation_strategy.py & ams/core/base.py**:
  - 策略的基类（如 PMS 模块）负责将 `order_target_percent` 翻译为计算出的所需股数，并生成 `Order` 发送给 `SimBroker.submit_order()`。
  - 止盈机制：每次买入建仓后，连带发送一个有效期一日的 Limit Sell Order (价格为 `成本价 * (1 + take_profit_threshold)`) 给 Broker。
- **ams/runners/backtest_runner.py**:
  - 退化为纯粹的“发条装置”。标准事件流：`broker.match_orders(daily_data)` -> `broker.update_equity()` -> `strategy.generate_target_portfolio(context)`。禁止在 Runner 内部写任何撮合/价格判定逻辑。
- **Rollback Strategy & Redline Protocol (核心模块修改防瘫痪回滚策略)**:
  - **隔离分支**：此次涉及核心底层组件（Runner, Broker）重构，严禁直接在 `master` 分支 push。必须在 `feature/order_driven_broker` 分支执行。
  - **Fallback 机制**：若重构导致原有的回测基准测试（Baseline Integration Tests）崩溃，流水线必须无条件回滚到上一个健康 commit（即 `BacktestRunner` 改造前），并通过隔离分支提供法证分析。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: 虚拟券商限价单撮合 (Limit Order Matching in Broker)**
  - **Given** 订单簿中存在一笔卖出标的A的 Limit Order，触发价设为110元。
  - **When** `SimBroker.match_orders()` 接收到当日数据，其中标的A的 `high` 为 112，`close` 为 105。
  - **Then** `SimBroker` 判定该订单成交，结算金额按 `110元` (限价单价格) 增加现金，而非 105 或 112。

- **Scenario 2: 基于独立滑点模型的惩罚成交 (Slippage Injection)**
  - **Given** `SimBroker` 注入了固定扣除 50% 的 `ExtremeRiskSlippageModel`。
  - **When** 一笔市价卖出单（Market Order）遭遇被标记为退市/暴雷的标的被撮合。
  - **Then** 结算价应用滑点模型返回值，成交价等于真实收盘价的 50%。

- **Scenario 3: 周频调仓休眠 (Weekly Rebalance Sleep)**
  - **Given** 策略配置 `rebalance_period='weekly'`, `reinvest_on_risk_exit=False`。
  - **When** 在周三，Broker 回报某限价止盈单已成交，资金退回现金池。
  - **Then** 策略当日 `generate_target_portfolio` 不下发新的补仓买入 Order，资金持续闲置直到周五。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **隔离测试 (Isolated Component Testing)**:
  - 必须编写脱离 `BacktestRunner` 的独立 Broker 单元测试（`test_sim_broker_order_matching.py`）。单独实例化 `SimBroker`，手动 `submit_order`，喂入人工伪造的 `bar_data`，断言订单状态从 `PENDING` 跃迁到 `FILLED` 及资金的精确变动。
- **Mocking**: 测试滑点时，使用 `MockSlippageModel` 注入以精确控制返回的折损率。

## 6. Framework Modifications (框架防篡改声明)
- `/root/projects/AMS/ams/runners/backtest_runner.py`
- `/root/projects/AMS/ams/core/base.py`
- `/root/projects/AMS/ams/core/cb_rotation_strategy.py`
- `/root/projects/AMS/ams/core/sim_broker.py`
- `/root/projects/AMS/ams/core/slippage.py` (New File)
- `/root/projects/AMS/ams/core/order.py` (New File)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0/v2.0**: 违背分离原则被拒。
- **v3.0**: 未引入订单簿，利用 Runner 干预 Broker，产生 God Object 和缺乏回滚策略被拒。
- **v4.0 Revision Rationale**: 彻底转向工业级 Order-Driven 架构，增加回滚与隔离测试红线约束，符合量化系统实盘对接标准最佳实践。

---

## 7. Hardcoded Content (硬编码内容)
None
