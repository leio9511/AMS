---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: 1157_CB_Strategy_Risk_Enhancement

## 1. Context & Problem (业务背景与核心痛点)
当前 AMS 2.0 (Event-Driven Architecture) 已完成第一阶段历史回测引擎的搭建。现有的双低轮动策略 (`CBRotationStrategy`) 在回测中已实现基础打分与周频/日频调仓机制。然而，在推进到实盘接管前，必须解决回测在应对极端风险和细节模拟上的失真问题：
1. **盘中止盈缺失**：目前仅有单日 -8% 的绝对止损机制，缺少对盘中冲高（Take-Profit）及时锁定利润的机制，导致收益回撤过大。
2. **调仓频率与中途退出资金的再分配机制不明确**：当策略以周频 (`weekly`) 运行时，如果在周三发生了止损或止盈退出，系统目前的处理方式不具备可配置性，需要支持“持币等周末（Hold in Cash）”与“立刻递补（Immediate Replenishment）”两种模式。
3. **退市/极度暴雷事件惩罚模拟不足**：当遇到可转债强制退市或极度暴雷（例如单日跌幅或归零）时，目前的框架对模拟券商（`SimBroker`）缺乏科学的滑点惩罚机制。强行在券商层写入业务退市逻辑会破坏架构通用性（Leaky Abstraction）。

## 2. Requirements & User Stories (需求定义)
1. **参数化止盈机制 (Take-Profit Threshold)**：`CBRotationStrategy` 需新增 `take_profit_threshold` 参数，当日内最高价达到止盈线时，将其调出当日的目标持仓，实现回测日内止盈卖出。
2. **参数化调仓频率与资金再分配 (Rebalance Config & Fund Reinvestment)**：
   - 新增 `rebalance_period` 参数，支持 `daily` (每日调仓打分) 和 `weekly` (仅每周五调仓打分)。
   - 新增 `reinvest_on_risk_exit` 配置开关：当策略为周频时，若因风控（止盈/止损）导致仓位空缺，该配置若为 `False`，空缺权重趴在现金；若为 `True`，则立刻在当日日终触发打分递补。
3. **滑点模型注入 (SlippageModel Injection)**：设计一套独立的滑点模型抽象，以依赖注入的方式传入 `SimBroker`，以解耦底层的通用撮合与上层的风控惩罚。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **CBRotationStrategy (`ams/core/cb_rotation_strategy.py`)**: 
  - 构造函数增加 `take_profit_threshold`（默认 0.10 等），`rebalance_period`（默认 'daily'），`reinvest_on_risk_exit`（默认 False）。
  - 在 `generate_target_portfolio` 函数中分离“风控拦截”和“常规打分轮动”。
  - 风控拦截每天执行：若触及止损（计算逻辑已存在）或止盈（若日最高价 `high` 存在，判断 `(high - previous_close) / previous_close >= take_profit_threshold`），则在当日剔除该标的。
  - 常规打分轮动：判断是否是调仓日。如果是日频，每天打分；如果是周频且当天不是周五，仅在 `reinvest_on_risk_exit == True` 且目标仓位数不足 `top_n` 时才重新打分，否则沿用上一日的最终打分名录。
- **SlippageModel Injection (`ams/core/slippage.py` & `ams/core/sim_broker.py`)**:
  - 新建模块 `ams/core/slippage.py`，定义 `BaseSlippageModel` 以及派生类 `ExtremeRiskSlippageModel`。
  - `SimBroker` 构造函数新增可选参数 `slippage_model: BaseSlippageModel = None`。
  - `SimBroker` 在处理 `order_target_percent` 结算获取成交价时，调用 `slippage_model.get_trade_price(ticker, current_price, direction, context)` 获取滑点后的实际成交价。从而避免在 `SimBroker` 内部硬编码退市等业务逻辑，严格遵循关注点分离（Separation of Concerns）。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: 触发日内止盈 (Intraday Take-Profit)**
  - **Given** 策略配置 `take_profit_threshold = 0.10`，且持仓包含标的A。
  - **When** 标的A的当日行情中，最高价相对于前收盘价涨幅 >= 10%。
  - **Then** 策略生成的 `target_portfolio` 剔除标的A。

- **Scenario 2: 周频调仓下的持币观望配置 (Weekly Hold in Cash)**
  - **Given** 策略配置为 `rebalance_period='weekly'` 且 `reinvest_on_risk_exit=False`。当前为周三（非调仓日），持仓数等于目标数。
  - **When** 一只标的触发风控被移除。
  - **Then** `target_portfolio` 总权重下移，不再触发新的标的买入打分，资金保留在账户中。

- **Scenario 3: 基于独立滑点模型的惩罚成交 (Slippage Injection)**
  - **Given** 一个初始化并注入了 `ExtremeRiskSlippageModel`（设置了 50% 减值）的 `SimBroker`，且标的处于极端退市风险名单中。
  - **When** 发起针对该标的的卖出平仓指令。
  - **Then** 最终平仓结算价为 `current_price * 0.5`，体现出独立的滑点模型成功介入结算过程，而未污染基础券商。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Test (策略逻辑)**: 针对 `CBRotationStrategy` 提供包含和不包含 `high` 字段的数据帧，模拟连续多日的事件流。验证在周频模式下，触发止损/止盈后的持币现象是否符合预期。
- **Unit Test (滑点模型注入)**: 构建一个 `DummySlippageModel`，注入 `SimBroker`。测试买入卖出时，`SimBroker` 是否正确调用了注入对象的计算接口并按照返回值结算资金。

## 6. Framework Modifications (框架防篡改声明)
- `/root/projects/AMS/ams/core/cb_rotation_strategy.py`
- `/root/projects/AMS/ams/core/sim_broker.py`
- `/root/projects/AMS/ams/core/slippage.py` (New File)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: 初始草案，试图直接在 `SimBroker` 中增加黑名单以模拟退市惩罚。
- **Audit Rejection (v1.0)**: 被 Auditor 驳回。理由为违反 Separation of Concerns，在基础设施层耦合业务黑名单引发 Leaky Abstraction，且缺乏底层回滚策略。
- **v2.0 Revision Rationale**: 引入依赖注入（Dependency Injection），抽象出独立的 `SlippageModel` 并注入 `SimBroker`，确保基础券商代码的纯洁性，将业务级退市判定下移到独立的风控/滑点组件中。

---

## 7. Hardcoded Content (硬编码内容)
None
