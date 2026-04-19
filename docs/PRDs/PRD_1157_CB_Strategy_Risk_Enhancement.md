---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: 1157_CB_Strategy_Risk_Enhancement

## 1. Context & Problem (业务背景与核心痛点)
当前 AMS 2.0 (Event-Driven Architecture) 已完成第一阶段历史回测引擎的搭建。现有的双低轮动策略 (`CBRotationStrategy`) 在回测中已实现基础打分与周频/日频调仓机制。然而，在推进到实盘接管前，必须解决回测在应对极端风险和细节模拟上的失真问题：
1. **盘中止盈缺失**：目前仅有单日 -8% 的绝对止损机制，缺少对盘中冲高（Take-Profit）及时锁定利润的机制，导致收益回撤过大。
2. **调仓频率与中途退出资金的再分配机制不明确**：当策略以周频 (`weekly`) 运行时，如果在周三发生了止损或止盈退出，系统目前的处理方式不具备可配置性，需要支持“持币等周末（Hold in Cash）”与“立刻递补（Immediate Replenishment）”两种模式。
3. **退市/极度暴雷事件惩罚模拟不足**：当遇到可转债强制退市或极度暴雷（例如单日跌幅或归零）时，当前的 `SimBroker` 对此依然可以按收盘价正常结算，导致回测结果虚高，无法真实反映流动性枯竭带来的财务计提损失（Slippage & Delisting Penalty）。

## 2. Requirements & User Stories (需求定义)
1. **参数化止盈机制 (Take-Profit Threshold)**：`CBRotationStrategy` 需新增 `take_profit_threshold` 参数，当日内最高价达到止盈线时，将其调出当日的目标持仓，实现回测日内止盈卖出。
2. **参数化调仓频率与资金再分配 (Rebalance Config & Fund Reinvestment)**：
   - 新增 `rebalance_period` 参数，支持 `daily` (每日调仓打分) 和 `weekly` (仅每周五调仓打分)。
   - 新增 `reinvest_on_risk_exit` 配置开关：当策略为周频时，若因风控（止盈/止损）导致仓位空缺，该配置若为 `False`，空缺权重趴在现金；若为 `True`，则立刻在当日日终触发打分递补。
3. **退市结算与极端滑点减值 (Delisting & Extreme Risk Slippage in SimBroker)**：在 `SimBroker` 撮合结算时，识别特定被标记为退市/极度异常的标的（例如在 context 或 datafeed 中带有 `delisted: True` 标签），或通过传入的参数，对其卖出结算强制扣除一定比例（如 30% 或 50%）的清算减值。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **CBRotationStrategy (`ams/core/cb_rotation_strategy.py`)**: 
  - 构造函数增加 `take_profit_threshold`（默认 0.10 等），`rebalance_period`（默认 'daily'），`reinvest_on_risk_exit`（默认 False）。
  - 在 `generate_target_portfolio` 函数中分离“风控拦截”和“常规打分轮动”。
  - 风控拦截每天执行：若触及止损（计算逻辑已存在）或止盈（若日最高价 `high` 存在，判断 `(high - previous_close) / previous_close >= take_profit_threshold`），则在当日剔除该标的。
  - 常规打分轮动：判断是否是调仓日。如果是日频，每天打分；如果是周频且当天不是周五，仅在 `reinvest_on_risk_exit == True` 且目标仓位数不足 `top_n` 时才重新打分，否则沿用上一日的最终打分名录。
- **SimBroker (`ams/core/sim_broker.py`)**:
  - 在 `order_target_percent` 结算时，引入惩罚因子逻辑。由于该层可能拿不到深层标的异常属性，可通过向 `SimBroker` 传入一张退市/暴雷黑名单（或在价格更新时标注），在卖出成交时强制应用打折成交价，模拟极端的流动性枯竭。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: 触发日内止盈 (Intraday Take-Profit)**
  - **Given** 策略配置 `take_profit_threshold = 0.10`，持仓含有标的A。
  - **When** 标的A当日最高价 `high` 相对于昨收上涨 >= 10%。
  - **Then** 策略当日生成的 `target_portfolio` 中，标的A的权重为 0（被剔除），触发清仓。

- **Scenario 2: 周频调仓下的持币观望配置 (Weekly Hold in Cash)**
  - **Given** 配置为 `rebalance_period='weekly'` 且 `reinvest_on_risk_exit=False`。当前为周三，满仓 20 只。
  - **When** 其中一只标的触发止损，在当日被踢出持仓。
  - **Then** `target_portfolio` 当日只包含剩下的 19 只，总仓位不足 100%，资金留在现金池中不触发递补买入，直至周五再进行满仓分配。

- **Scenario 3: 模拟券商退市减值 (Delisting Penalty in SimBroker)**
  - **Given** 标的X遭遇退市，`SimBroker` 被告知或标的进入黑名单。
  - **When** 策略发指令卖出清仓标的X。
  - **Then** `SimBroker` 最终结算金额不仅按收盘价，还需额外扣减至少 50% 的清算惩罚，产生巨幅真实亏损。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Test (策略逻辑)**: 针对 `CBRotationStrategy` 提供含有 `high` 字段和无 `high` 字段的测试数据帧，验证止损和止盈条件下的目标仓位输出。模拟周一至周五的序列，验证 `rebalance_period` 的开关隔离功能。
- **Unit Test (券商逻辑)**: 测试 `SimBroker` 能够接收特定清算黑名单或惩罚因子，并在调用 `order_target_percent` 削减仓位时，按照惩罚因子正确减持权益金额。

## 6. Framework Modifications (框架防篡改声明)
- `/root/projects/AMS/ams/core/cb_rotation_strategy.py`
- `/root/projects/AMS/ams/core/sim_broker.py`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: 初始方案，包含止盈、周频控制以及券商黑名单模拟。

---

## 7. Hardcoded Content (硬编码内容)
None
