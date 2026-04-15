---
Affected_Projects: [AMS]
---

# PRD: Phase1_4_Fix_SimBroker_Cash_Allocation

## 1. Context & Problem (业务背景与核心痛点)
在 Phase 1.3 的验证中，我们发现回测引擎的 `SimBroker` 存在一个致命的资金分配 Bug。
目前 `order_target_percent` 方法在执行买入时，直接扣除 `目标金额 * (1 + 滑点)`，而没有检查账户现金余额。当策略要求满仓（如 20 只股票各分配 5%，共计 100% 仓位）时，加上额外 0.1% 的买入滑点，总支出达到了资金的 100.1%。这会导致账户 `cash` 变为负数。
负现金会污染后续每天的 `total_equity` 计算，导致回测净值曲线严重失真。我们需要为模拟券商加入严格的现金流校验和订单按比例缩减（Partial Fill）机制。

## 2. Requirements & User Stories (需求定义)
- **严格的现金约束**：`SimBroker` 绝不允许 `cash` 变为负数。
- **自动降级/部分成交 (Partial Fill)**：
  - 当发出买入指令（`diff > 0`）时，系统需计算理论成本 `cost = diff * (1 + slippage)`。
  - 如果 `cost > self.cash`（余额不足），系统必须将本次买入金额限制为最大可用现金能买到的量：`actual_diff = self.cash / (1 + slippage)`。
  - 随后，全额扣除现有 `cash`（变为 0），并将 `actual_diff` 计入 `holdings`。
- **卖出指令不受限**：卖出操作（`diff < 0`）正常执行，直接将扣除滑点后的净所得（Proceeds）加回现金池。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- 仅修改 `ams/core/sim_broker.py` 中的 `order_target_percent` 核心交易逻辑。
- 采用防守型编程（Defensive Programming），在执行任何买入扣款前加入 `min(cost, self.cash)` 的限幅逻辑。
- 此修复不需要改变接口契约，对外依然接收 `ticker` 和 `percent`，完全对下游的 `BacktestRunner` 和 `CBRotationStrategy` 透明。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 现金余额不足时的自动降级**
  - **Given** 券商当前有 $10,000 现金，滑点为 1% (0.01)
  - **When** 策略要求买入目标价值为 $15,000 的股票
  - **Then** 系统计算出买不起，自动将所有现金用于购买，扣除 $10,000 现金（剩余 $0），并使得该股票的 holdings 增加 `$10,000 / 1.01 = $9,900.99`。

- **Scenario 2: 现金充足时的正常执行**
  - **Given** 券商当前有 $10,000 现金，滑点为 1% (0.01)
  - **When** 策略要求买入目标价值为 $5,000 的股票
  - **Then** 系统扣除 $5,050 现金（剩余 $4,950），该股票的 holdings 增加 $5,000。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **核心质量风险**：资金越界导致净值失真。
- **单元测试**：
  - 在 `tests/test_cb_backtest_engine.py` (或新增 `test_sim_broker.py`) 中增加极端满仓测试用例。
  - 强制连续下达合计超过 100% 权重的买单，断言最终 `broker.cash >= 0.0` 始终成立。

## 6. Framework Modifications (框架防篡改声明)
- 仅允许修改 `ams/core/sim_broker.py`。

## 7. Hardcoded Content (硬编码内容)
- None