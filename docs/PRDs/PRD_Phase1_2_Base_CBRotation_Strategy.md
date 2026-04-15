---
Affected_Projects: [AMS]
---

# PRD: Phase1_2_Base_CBRotation_Strategy

## 1. Context & Problem (业务背景与核心痛点)
本 PRD 对应 ISSUE-1135。在 Phase 1.1 完成了 JQData 数据基建后，我们现在需要实现第一个真实的策略引擎算法。
目前的 `CBRotationStrategy` 仅是一个基类实现，缺乏具体的选股和调仓逻辑。我们需要在该类中实装“基础双低轮动”算法，并在 `BacktestRunner` 中跑通闭环，从而为后续 ISSUE-1127 的风控增强提供性能基准（Baseline）。

## 2. Requirements & User Stories (需求定义)
1. **实现核心算法 (`ams/core/cb_rotation_strategy.py`)**:
   - 实现 `generate_target_portfolio(context, data)` 方法。
   - **过滤逻辑**：
     - 剔除当日无成交、停牌或数据缺失的标的。
     - 剔除日均成交额 < 1000 万的标的（流动性门槛）。
   - **评分逻辑**：
     - 计算 `双低值 = 收盘价 + 溢价率 * 100`。
   - **选股逻辑**：
     - 将所有候选券按“双低值”由小到大排序。
     - 选取排名前 20 只标的作为目标持仓。
   - **权重分配**：
     - 采用等权重分配，每只标的目标权重为 5%。
2. **跑通回测脚本 (`ams/runners/backtest_runner.py`)**:
   - 确保 Runner 能正确加载 `HistoryDataFeed` 提供的 JQData 本地数据。
   - 驱动策略引擎按天运行，并输出最终的累计收益率、回撤等统计指标。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **策略纯粹性**：`CBRotationStrategy` 必须保持“纯算法”特征，其内部不得包含任何 `read_csv` 或 `requests` 调用，所有行情数据必须通过输入参数 `data` 获取。
- **状态管理**：通过 `context` 对象管理账户资金和当前持仓，确保回测过程中的资金曲线是闭环计算的。
- **解耦设计**：策略输出的是“目标权重字典” `{ticker: weight}`，具体的调仓差分（Diff）和撮合由 `SimBroker` 处理。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 基础双低选股准确性**
  - **Given** 一组包含不同价格和溢价率的可转债测试数据
  - **When** 调用 `strategy.generate_target_portfolio()`
  - **Then** 返回的字典应包含且仅包含双低值最低的前 20 只标的，且每只权重为 0.05。

- **Scenario 2: 回测流程闭环**
  - **Given** 2025-01-06 至 2025-02-06 的本地历史数据
  - **When** 启动 `backtest_runner.py`
  - **Then** 系统应能无报错运行至结束，并打印出包含“Total Return”和“Max Drawdown”的分析报告。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **核心质量风险**：排序算法逻辑错误、等权计算精度问题。
- **单元测试要求**：
  - 在 `test_cb_rotation_strategy.py` 中，构造一个包含 50 只债的 Mock DataFrame，验证排序和截断逻辑。
  - 验证成交额过滤阈值（1000万）是否生效。
- **集成测试**：
  - 运行一个极短周期（如 3 天）的小规模回测，验证 `Runner -> Strategy -> Broker` 的数据流转是否正确。

## 6. Framework Modifications (框架防篡改声明)
- 允许修改 `ams/core/cb_rotation_strategy.py`。
- 允许完善 `ams/runners/backtest_runner.py`。

## 7. Hardcoded Content (硬编码内容)
- **`liquidity_threshold`**: 10,000,000 (1000万成交额)
- **`max_hold_count`**: 20
- **`weight_per_position`**: 0.05
