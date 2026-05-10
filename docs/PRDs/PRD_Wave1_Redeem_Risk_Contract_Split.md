---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Wave1 Redeem Risk Contract Split

## 1. Context & Problem (业务背景与核心痛点)
AMS 当前可转债回测/研究数据中，`is_redeemed` 由 `delist_Date` 直接派生：`date >= delist_Date` 即为 `True`。这是一种终态（terminal-state）语义，而不是交易风险（trading-risk）语义。

当前问题不在于“字段缺失”，而在于“字段语义错位”：
- 策略层把 `is_redeemed` 当成强赎/赎回风险过滤条件使用；
- 但现实现只能在退市/赎回完成当天及以后才翻成 `True`；
- 这会遗漏“公告后到退市前”的风险窗口，导致回测可能继续持有/买入理论上应当规避的标的；
- 进一步导致回测收益偏乐观，且未来会把错误语义带入实盘风控。

结合当前讨论，本问题不应被定义为“重写策略”或“立即搭完整实盘事件平台”，而应被定义为 **Phase 1.5 收尾阶段的 redemption contract 升级**：
- 保留当前 `is_redeemed` 作为终态语义；
- 新增 `redeem_risk` 作为交易风险语义；
- 先在回测研究数据和策略过滤层完成最小闭环；
- 后续再由下一波 issue 接管 validator / metrics / event ledger / live-backtest shared-state 统一问题。

本 PRD 只覆盖 Wave 1：语义拆分 + 策略最小切换。

## 2. Requirements & User Stories (需求定义)
### 2.1 Functional Requirements
1. AMS 必须在可转债研究数据 contract 中新增 `redeem_risk` 字段。
2. `is_redeemed` 必须保留为终态语义，不得在本波中被重定义为公告后风险态。
3. `CBRotationStrategy` 必须停止仅依赖 `is_redeemed` 做赎回风险过滤，改为优先使用 `redeem_risk`，并保留 `is_redeemed` 作为终态兜底过滤。
4. AMS 必须能够表示如下合法状态：
   - `redeem_risk=True`
   - `is_redeemed=False`
   该状态代表“已进入赎回风险窗口，但尚未进入终态/退市态”。
5. 本波允许 `redeem_risk` 的上游先采用受控 placeholder / fixture 驱动的 contract 接线与策略切换，只要文档与测试明确其为过渡形态；但不得把 `is_redeemed` 语义偷换为 `redeem_risk`。
6. 回测主路径、策略主路径、数据 schema 必须对新字段兼容，不得要求重写 Runner / Broker / 排名逻辑。

### 2.2 Non-Functional Requirements
1. 本波改动必须局限在 data contract、ETL 输出面、strategy filter 语义与对应测试，不得扩散为无边界架构重写。
2. 本波必须为后续 Wave 2 / Wave 3 保留清晰演进接口：
   - Wave 2 将接 validator / metrics / audit semantics
   - Wave 3 将接 redemption event ledger 与 live/backtest shared-state
3. 文档必须明确区分：
   - `redeem_risk` = 交易风险态
   - `is_redeemed` = 终态/退市态

### 2.3 User Stories
- 作为量化研究者，我希望策略能够排除“已进入赎回风险窗口但尚未退市”的转债，而不是等到退市当天才排除。
- 作为架构维护者，我希望在不重写 AMS 策略框架的前提下，把 redemption semantics 拆清楚，为后续 live/backtest 一致性铺路。
- 作为 QA / Auditor，我希望能够看到一个明确的 contract split，而不是继续让终态字段承担风险态职责。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Core Design Decision
本波采用 **双字段语义拆分**，而不是原地重定义 `is_redeemed`：
- `redeem_risk`: 交易风险态（用于策略过滤）
- `is_redeemed`: 终态/退市态（保留现有终态职责）

这样做的原因：
1. 兼容当前已有数据 contract 与 validator / metrics 基线，避免一次性打爆所有口径；
2. 避免把“公告风险态”和“生命周期终态”重新揉成一个歧义字段；
3. 让策略层以最小改动切换到正确方向；
4. 为后续 event-ledger 驱动的真实 `redeem_risk` 留出演进空间。

### 3.2 Scope of Code Changes
本波授权修改的目标区域应限定为：
- `etl/cb_etl_pipeline.py`
- `etl/cb_field_registry.py`
- `etl/cb_etl_runner.py`（若需要最小 contract 对齐）
- `ams/core/cb_rotation_strategy.py`
- 与上述 contract/strategy 直接相关的 tests
- 必要的 docs / contract 注释

### 3.3 Required Semantic Contract
#### `is_redeemed`
- 本波继续表示终态语义；
- 当前已有 `delist_Date` 驱动逻辑可继续保留；
- 不得在本波偷偷改成公告后持续 `True`。

#### `redeem_risk`
- 本波定义其 contract 与消费面；
- 必须能出现在 canonical dataset / strategy input 中；
- 本波重点是 **先让系统能正确表达和消费该字段**；
- 后续真实事件来源与 shared-state 统一由 Wave 3 完成。

### 3.4 Strategy Filtering Contract
`CBRotationStrategy.generate_target_portfolio()` 的赎回相关过滤必须升级为：
- 先过滤 `redeem_risk == True`
- 再过滤 `is_redeemed == True`
- 并与 `is_st` 过滤共同组成风险过滤链

推荐目标形态：
```python
exclude_if = is_st or redeem_risk or is_redeemed
```

### 3.5 Risk Boundaries
本波明确 **不做**：
- 不接完整 redemption event ledger
- 不要求 live runtime 已经共享该状态引擎
- 不要求完备处理公告撤回 / revision / 多源 reconciliation
- 不重写 Runner / Broker / 排名逻辑

### 3.6 Evolution Intent
本波是 Phase 1.5 收尾中的 contract split，目标是：
- 先消除语义错位
- 再为 Wave 2 observability correction 和 Wave 3 event-driven shared-state 铺路

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Canonical dataset exposes semantic split**
  - **Given** AMS 生成一份可转债研究数据集
  - **When** 数据集落盘并被读取
  - **Then** 其中必须同时包含 `redeem_risk` 与 `is_redeemed` 字段
  - **And** 两个字段的语义必须在文档/contract 中被明确区分

- **Scenario 2: Strategy excludes risk-window bonds before terminal state**
  - **Given** 某转债样本 `redeem_risk=True` 且 `is_redeemed=False`
  - **When** `CBRotationStrategy.generate_target_portfolio()` 执行候选过滤
  - **Then** 该转债必须被排除出可交易候选池

- **Scenario 3: Terminal-state compatibility remains intact**
  - **Given** 某转债样本 `is_redeemed=True`
  - **When** 策略执行候选过滤
  - **Then** 该转债必须继续被排除，即使 `redeem_risk=False`

- **Scenario 4: Non-risk bonds remain eligible**
  - **Given** 某转债样本 `redeem_risk=False`、`is_redeemed=False`、`is_st=False`
  - **When** 策略执行候选过滤
  - **Then** 该转债不得仅因 redemption contract 变更而被错误排除

- **Scenario 5: AMS can represent split-state rows explicitly**
  - **Given** 一个 redemption 风险窗口早于 terminal delist 的样本场景
  - **When** fixture 或研究数据样本被构造
  - **Then** 系统必须能够表示 `redeem_risk=True && is_redeemed=False` 的行

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### 5.1 Core Quality Risk
本波的核心风险不是代码跑不起来，而是：
- 语义仍然混淆；
- `redeem_risk` 加了但策略没真正切过去；
- 或 coder 直接把 `is_redeemed` 偷偷改语义，导致 blast radius 失控。

### 5.2 Recommended Test Layers
1. **Contract / schema-level tests**
   - 验证 dataset 输出包含双字段；
   - 验证可以表示 split-state row。
2. **Strategy filter tests**
   - 使用 deterministic fixture DataFrame；
   - 精确断言 `redeem_risk=True` / `is_redeemed=False` 被过滤；
   - 精确断言 `is_redeemed=True` 被过滤；
   - 精确断言普通样本不过滤。
3. **No unnecessary E2E expansion in Wave 1**
   - 本波不要求 live-source E2E；
   - 重点是 contract split 是否真实落地。

### 5.3 Mocking Guidance
- 允许对 redemption risk 样本使用 fixture / mock 数据；
- 不要求此波接真实公告源；
- 但不得使用 mock 来掩盖字段语义错位。

### 5.4 Quality Goal
Wave 1 完成后，AMS 必须达到：
- redemption 语义已经拆开；
- 策略过滤方向已改正；
- 后续工作不再需要通过“重定义 `is_redeemed`”来修风险语义。

## 6. Framework Modifications (框架防篡改声明)
- 无。
- 本 PRD 不授权修改 SDLC framework 脚本。

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial execution brief created from Issue #13 / #14 discussion. The key conclusion is that Phase 1.5 should first split terminal redemption semantics from trading-risk semantics, instead of attempting a one-wave event-ledger rollout.
- **Audit Rejection (v1.0)**: Pending.
- **v2.0 Revision Rationale**: Pending.

---

## 7. Hardcoded Content (硬编码内容)
### `recommended_filter_shape`
```python
exclude_if = is_st or redeem_risk or is_redeemed
```

### `required_new_field_name`
```python
"redeem_risk"
```

### `required_existing_terminal_field_name`
```python
"is_redeemed"
```

### `required_split_state_example`
```python
redeem_risk == True and is_redeemed == False
```

### `phase_positioning_statement`
```text
This change is a Phase 1.5 closeout contract upgrade, not a Phase 2 feature expansion.
```
