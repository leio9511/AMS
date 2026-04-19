---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: 1157_CB_Strategy_Risk_Enhancement

## 1. Context & Problem (业务背景与核心痛点)
当前 AMS 2.0 (Event-Driven Architecture) 已完成第一阶段历史回测引擎的搭建。在实盘接管前，需解决以下回测失真与功能缺失问题：
1. **盘中止盈与限价单缺失**：真实交易中，止盈是下发带有触发价的条件单（Take-Profit Order）或限价单（Limit Order）。目前的框架仅支持按收盘价进行“目标权重调仓”，缺少日内最高价（`high`）触及止盈价时精准结算锁定利润的机制。
2. **调仓频率与中途退出资金的再分配机制不明确**：当策略以周频运行时，中途风控退出的资金需要可配的“持币等周末”或“立刻打分递补”机制。
3. **极度暴雷事件滑点惩罚不足**：退市等极度流动性枯竭事件，直接按收盘价结算会致回测虚高，需要解耦的滑点减值模型。

## 2. Requirements & User Stories (需求定义)
1. **真实日内止盈撮合 (Take-Profit Order Support)**：支持策略配置 `take_profit_threshold`。回测运行器（Runner）与模拟券商（SimBroker）需联合支持“日内触价止盈”行为：若当日 `high` 触及成本价 * (1 + 阈值)，则必须按止盈价（Limit Price）进行撮合卖出，而非按收盘价卖出。
2. **参数化调仓频率与资金再分配 (Rebalance Config & Fund Reinvestment)**：支持 `rebalance_period` (`daily`/`weekly`) 与 `reinvest_on_risk_exit`（True/False）控制周频策略中途退出资金的处理。
3. **滑点模型注入 (SlippageModel Injection)**：抽象独立的滑点模型注入 `SimBroker`，在订单结算时获取滑点后的真实成交价，避免券商层硬编码业务退市逻辑。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Order Management & SimBroker Upgrade (`ams/core/sim_broker.py` & `ams/runners/backtest_runner.py`)**:
  - `BacktestRunner` 在进入每日收盘 `generate_target_portfolio` 前，需先执行一次**日内风控撮合 (Intraday Match)**。
  - 获取当日最高价 `high`，若持仓标的 `high >= 持仓成本价 * (1 + take_profit_threshold)`，则通知 `SimBroker` 触发止盈。
  - `SimBroker` 执行平仓时，**成交价强制锁定为止盈触发价**（即 `持仓成本价 * (1 + 阈值)`），而非收盘价，从而完美分离信号层（策略不用管怎么卖）与执行层（券商真实模拟触价成交）。
- **CBRotationStrategy (`ams/core/cb_rotation_strategy.py`)**: 
  - 不在策略信号层偷看 `high` 来做止盈。
  - 构造函数增加 `rebalance_period`（默认 'daily'），`reinvest_on_risk_exit`（默认 False），以及传递给框架的 `take_profit_threshold`。
  - 仅负责基于收盘数据的常规打分与周频/日频节奏控制。
- **SlippageModel Injection (`ams/core/slippage.py`)**:
  - 新建模块定义 `BaseSlippageModel` 与 `ExtremeRiskSlippageModel`，注入到 `SimBroker` 中，用于结算时调整价格。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: 真实触价止盈 (Limit Price Execution)**
  - **Given** 策略配置 `take_profit_threshold = 0.10`，持仓A成本100元，当日最高价112元，收盘价102元。
  - **When** 框架进入当日回测。
  - **Then** `SimBroker` 在日内撮合阶段触发平仓，该笔卖出单的成交价必须为 `110元`（触发价），而不是收盘价102元，锁定日内利润。

- **Scenario 2: 周频调仓下的持币观望配置 (Weekly Hold in Cash)**
  - **Given** `rebalance_period='weekly'`, `reinvest_on_risk_exit=False`，非周五。
  - **When** 某标的触发止损平仓。
  - **Then** 日终策略计算目标仓位时，不新增买入指令，平仓资金保留在现金池中。

- **Scenario 3: 基于独立滑点模型的惩罚成交 (Slippage Injection)**
  - **Given** `SimBroker` 注入了设置 50% 减值的极端滑点模型，遭遇退市标的卖出。
  - **When** 发出卖出指令。
  - **Then** 结算价应用模型返回值，体现出 50% 的巨幅折损。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Test (日内撮合)**: 验证 `BacktestRunner` 和 `SimBroker` 能否基于给定的 `high` 触发止盈，并断言结算的现金额是否按 Limit Price 累加，绝不能按 Close Price。
- **Unit Test (策略控制与注入)**: 验证周频休眠逻辑；构建 `DummySlippageModel` 测试 `SimBroker` 价格扣减机制。

## 6. Framework Modifications (框架防篡改声明)
- `/root/projects/AMS/ams/runners/backtest_runner.py`
- `/root/projects/AMS/ams/core/cb_rotation_strategy.py`
- `/root/projects/AMS/ams/core/sim_broker.py`
- `/root/projects/AMS/ams/core/slippage.py` (New File)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0/v2.0**: 试图在策略打分阶段利用 `high` 剔除目标权重来模拟止盈，被 Auditor 驳回（Look-ahead Bias / Signal-Execution Coupling）。
- **v3.0 Revision Rationale**: 采纳真实限价单逻辑，将日内触价判断移入执行层（Runner & Broker的日内撮合阶段），严格按照 Limit Price 计算止盈收益，彻底解耦策略信号与订单执行。

---

## 7. Hardcoded Content (硬编码内容)
None
