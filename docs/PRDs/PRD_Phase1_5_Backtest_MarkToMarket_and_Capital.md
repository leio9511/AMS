---
Affected_Projects: [AMS]
---

# PRD: Phase1_5_Backtest_MarkToMarket_and_Capital

## 1. Context & Problem (业务背景与核心痛点)
目前的可转债回测引擎虽然能执行买卖，但存在三个严重影响结果真实性的问题：
1. **记账法逻辑落后**：目前的 `SimBroker` 记录的是“金额”而非“张数”，无法模拟真实价格波动带来的盈亏，且存在浮点数误差。
2. **忽视交易限制**：A 股可转债买入必须是“手”的倍数（1手=10张），之前的设计允许买入“碎股”，不符合实盘规则。
3. **本金与流动性匹配**：原定 100 万本金平摊到 20 只债后（每只 5 万），在执行“10 张一手”的取整规则后，会导致建仓偏差过大，需要提升至更合理的规模。

## 2. Requirements & User Stories (需求定义)
- **实现“整手”记账法 (Lot-based Accounting)**：
  - `SimBroker.holdings` 必须记录 `ticker -> 数量(张)`。
  - **强制取整规则**：买入张数必须是 **10 的整数倍**。向下取整，余下的资金保留在现金池中。
- **动态市值更新 (Daily Mark-to-Market)**：
  - 账户总资产 `total_equity` 实时计算公式：`现金 + Sum(持仓张数 * 当前收盘价)`。
- **调整初始资金**：
  - 将 `backtest_runner.py` 中默认的初始资金提升至 **4,000,000 (400万)**。
- **除零与停牌保护**：
  - 若标的当日收盘价 <= 0 或缺失，禁止执行该标的的任何买入操作；持仓价值按前一交易日价格计。
- **标准化输出**：
  - 必须严格按照 Hardcoded 章节定义的格式打印回测统计指标。

## 3. Architecture & Technical Strategy (架构设计 with Real-world Constraints)
- **Broker 精确算法**：
  - 买入张数计算：`target_shares = math.floor(target_value / price / 10) * 10`。
  - 执行成交：`self.holdings[ticker] += actual_bought_shares`。
  - 现金扣除：`actual_bought_shares * price * (1 + slippage)`。
- **Runner 层适配**：
  - 每日循环开始前，先根据 `data_slice` 的价格调用 `broker.update_equity()`，确保策略获取的是最新的净值用于计算仓位比例。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: “一手”交易约束验证**
  - **Given** 某债价格 125 元，目标买入金额 10,000 元
  - **When** 执行买入
  - **Then** 系统应计算出 10,000 / 125 = 80 张（正好是10的倍数）；若目标金额为 10,100 元，应依然只买入 80 张，而不是 80.8 张。

- **Scenario 2: 初始资金调整验证**
  - **Given** 实例化 BacktestRunner
  - **Then** 默认 `initial_cash` 必须为 4,000,000。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **核心质量风险**：取整逻辑导致现金与持仓不守恒。
- **单元测试**：
  - `test_lot_based_broker.py`：模拟各种极端价格，验证买入数量是否始终为 10 的倍数，且现金扣除是否精确到分。

## 6. Framework Modifications (框架防篡改声明)
- 允许修改 `ams/core/sim_broker.py`。
- 允许修改 `ams/runners/backtest_runner.py`。

## 7. Hardcoded Content (硬编码内容)
- **`initial_capital`**: `4000000.0`
- **`lot_size`**: `10`
- **`final_report_format`**: 
```text
Total Return: {:.4%}
Max Drawdown: {:.4%}
Final Equity: {:.2f}
```
