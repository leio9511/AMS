---
Affected_Projects: [AMS]
---

# PRD: Phase1_3_RiskControl_CBRotation

## 1. Context & Problem (业务背景与核心痛点)
本 PRD 对应 ISSUE-1136（即 ISSUE-1127 的核心诉求落地）。
Phase 1.2 完成了基础双低轮动引擎，但该引擎尚未包含任何风险控制机制。在实盘中，如果不加入止损和过滤逻辑，一次强赎公告或正股 ST 事件即可导致灾难性损失。
我们必须在 `CBRotationStrategy` 中实装三大风控护栏，同时修复 `BacktestRunner` 中一个关键的仓位再平衡 Bug（当前引擎每天无差别清仓重建，导致双倍滑点摩擦损耗）。

## 2. Requirements & User Stories (需求定义)
### 2.1 Bug 修复：BacktestRunner 再平衡逻辑
- **Given** 当日的目标持仓与前一交易日持仓高度重叠（重合率 > 90%）
- **When** `BacktestRunner` 执行仓位再平衡
- **Then** 系统应只针对差异部分（新增或踢出的标的）发送订单，不应对已在持仓中的标的重复下单，从而避免双倍滑点损耗。

### 2.2 风控增强：`CBRotationStrategy` 三项护栏
在 `generate_target_portfolio()` 方法中，按以下顺序执行数据清洗：

**护栏 1：强赎公告过滤（Force Redemption Filter）**
- 剔除 `is_redeemed == True` 的标的。
- 注意：当前本地 CSV 数据中 `is_redeemed` 字段全为 False（待 JQData 全年权限解决），但代码逻辑必须写死。

**护栏 2：ST/*ST 过滤**
- 剔除 `is_st == True` 的标的。
- 实盘中正股被 ST 后次日可能直接无量跌停，此过滤是保命项。

**护栏 3：日内 -8% 硬止损（Intraday Stop-Loss）**
- 接收 `context` 中的持仓信息，如果某持仓标的在当日行情数据中出现跌幅超过 8% 的情况，应将该标的从目标仓位中移除（视为已强平）。
- 注意：该风控需要 `context` 包含昨日收盘价或日内实时价格比对，暂通过 `daily_return` 字段（如存在）实现。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **策略层变更**：`CBRotationStrategy.generate_target_portfolio()` 在排序之前，增加上述三项过滤链（Chain of Filters），顺序为：强赎过滤 → ST 过滤 → 止损过滤。
- **Runner 层变更**：`BacktestRunner.run()` 在遍历持仓时，加入持仓 Diff 检测。如果目标仓位中某标的已存在于当前持仓且权重接近（差异 < 0.5%），则跳过该标的的订单。
- **Context 增强**：`BacktestRunner` 在每日调仓前，需将前一交易日的收盘价注入 `context.daily_return`，供止损逻辑使用。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 再平衡优化（无意义订单拦截）**
  - **Given** 前一交易日持仓包含 20 只可转债，当日目标持仓相同
  - **When** 运行回测
  - **Then** 系统不应发出任何卖出或买入订单，现金余额保持不变。

- **Scenario 2: ST 标的过滤**
  - **Given** 当日数据中存在 `is_st == True` 的标的 A
  - **When** 调用 `strategy.generate_target_portfolio()`
  - **Then** 返回的目标仓位中不包含标的 A。

- **Scenario 3: 止损风控**
  - **Given** 持仓标的 B 在当日 `daily_return == -0.10`（跌幅 10%，超过 -8% 阈值）
  - **When** 调用 `strategy.generate_target_portfolio()`
  - **Then** 返回的目标仓位中不包含标的 B（视为已在 -8% 时止损触发）。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **核心质量风险**：风控过滤逻辑顺序错误导致漏网之鱼；止损触发后重复买入。
- **单元测试**：
  - `test_cb_rotation_strategy_filters.py`：对三个过滤链逐项测试，构造包含 ST/强赎/暴跌标的的 Mock DataFrame，验证过滤结果。
  - `test_backtest_runner_rebalance.py`：验证 Diff 检测逻辑是否正确拦截无意义订单。
- **集成测试**：使用 2025-01-06 至 2025-02-06 真实数据运行回测，验证加入风控后最大回撤是否收窄。

## 6. Framework Modifications (框架防篡改声明)
- 允许修改 `ams/core/cb_rotation_strategy.py`。
- 允许修改 `ams/runners/backtest_runner.py`。

## 7. Hardcoded Content (硬编码内容)
- **`stop_loss_threshold`**: `-0.08`
- **`rebalance_diff_threshold`**: `0.005` (0.5% 权重差异以下视为无需调仓)
