---
Affected_Projects: [AMS]
---

# PRD: Phase1_5_Hotfix_UAT_Issues

## 1. Context & Problem (业务背景与核心痛点)
本补丁 PRD 旨在修复 Phase 1.5 UAT 阶段发现的逻辑漏洞，并防御由于引入高精度计算可能导致的系统级联崩溃。
1. **停牌股估值回滚逻辑缺失**：标的缺失价格时被计为 0，而非“按前一交易日价格计”。
2. **高精度计算与爆炸半径风险**：金融金额计算需 Decimal，但 Decimal 无法被标准 JSON 序列化，且直接变更核心属性类型会炸毁下游组件。
3. **测试缺失**：缺少要求的 `tests/test_lot_based_broker.py`。

## 2. Requirements & User Stories (需求定义)
- **内部高精度，外部兼容 (Internal Decimal, External Float)**：
  - `SimBroker` 内部私有变量（如存储现金和计算过程）使用 `Decimal`。
  - 对外暴露的属性（如 `total_equity`, `cash`）以及任何输出给日志/序列化的接口，**必须**返回 `float`，确保不破坏现有系统的 JSON 兼容性。
- **完善停牌估值与状态机**：
  - 修改 `update_equity`。若当前快照缺少价格，必须回溯至 `self.last_prices`（Broker 私有状态）取值。
- **补齐测试合规性**：
  - 创建 `tests/test_lot_based_broker.py`，包含高精度计算、10张一手取整、以及停牌估值稳定性的集成测试。

## 3. Architecture & Technical Strategy (架构设计)
- **边界转换规则 (API Boundary)**：
  - **入场**：接收到的外部 `price` (float) 在进入计算前立即通过 `Decimal(str(p))` 强转。
  - **出场**：`total_equity` 属性在 `getter` 方法中必须通过 `float(internal_val)` 还原。
- **计算逻辑**：
  - 使用 `from decimal import Decimal, ROUND_HALF_UP`。
  - 所有涉及金额扣除（现金池更新）的计算，必须通过 `.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)` 保留两位小数。
- **状态维护**：在 `SimBroker` 初始化时定义 `self._last_prices = {}`。
- **冷启动兜底**：若持仓标的在 `_last_prices` 中亦无记录且当前价格缺失，该标的市值计为 0。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 停牌估值守恒 (集成验证)**
  - **Given** 持仓 100 张 A 债，昨日收盘价 100.55
  - **When** 今日调用 `update_equity` 但 `current_prices` 缺少 A 债
  - **Then** 对外暴露的 `total_equity` 统计出的 A 债部分应保持为 10055.00。

- **Scenario 2: JSON 序列化兼容性**
  - **Given** 执行完一轮交易逻辑
  - **When** 对 `broker.total_equity` 进行 `json.dumps()` 操作
  - **Then** 系统应正常工作，不抛出 "Decimal is not JSON serializable" 异常。

## 5. Overall Test Strategy & Quality Goal (测试策略)
- **核心质量风险**：Decimal 溢出到外部 API 导致下游崩溃。
- **集成回归**：运行现有的全链路回测流程，验证逻辑修复后的净值不再是直线且无类型错误报错。

## 6. Framework Modifications (框架防篡改声明)
- 允许修改 `ams/core/sim_broker.py`。
- 允许创建 `tests/test_lot_based_broker.py`。

## 7. Hardcoded Content (硬编码内容)
- None
