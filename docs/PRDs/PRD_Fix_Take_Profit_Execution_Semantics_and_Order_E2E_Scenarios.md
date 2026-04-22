---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix_Take_Profit_Execution_Semantics_and_Order_E2E_Scenarios

## 1. Context & Problem (业务背景与核心痛点)
AMS 当前已经具备可运行的可转债双低轮动回测能力，`HistoryDataFeed`、`CBRotationStrategy`、`SimBroker`、`BacktestRunner` 均已存在，`main_runner.py` 统一 CLI 主路径也已打通，能够在指定数据路径下执行真实回测。这意味着系统现在的主要矛盾不再是“回测跑不起来”，而是“回测结果是否可信、是否真实反映交易执行语义”。

当前暴露出的核心问题集中在 Take-Profit（TP）执行语义上：`--tp-mode` / `--tp-pos` / `--tp-intra` 虽然能够被 CLI 与策略接收，但改变止盈阈值不会改变回测结果。已现场复现实验表明，无论在 daily rebalance 还是 weekly rebalance 下，把 `tp_pos/tp_intra` 从 `1%/1%` 调整为 `8%/8%` 乃至 `20%/8%`，`final_equity` 与 `total_return` 都完全一致。

这说明问题不是参数没有传入，而是 **Take-Profit 订单虽然被配置和创建，却没有真实影响持仓演化、成交路径与最终权益**。根据目前排查，最可疑的根因是回测执行顺序与 day-order expiration 语义存在冲突：策略在 bar 末尾创建 TP LIMIT SELL，而下一轮撮合前先执行过期逻辑，导致订单在真正有机会成交前被取消或失效。换句话说，系统现在可能出现这样一种危险假象：
- CLI 表面支持 TP 参数；
- 策略对象表面持有 TP 配置；
- 订单簿里表面出现 TP order；
- 但这些 TP order 对未来成交、持仓、现金、权益没有任何真实影响。

这类问题的危险性很高，因为它不会像语法错误那样直接崩溃，而是会制造一种“系统正常工作”的错觉，最终污染策略研究结论。Boss 当前关心的不是某一组参数收益高低，而是：**回测、后续 miniQMT 模拟盘、以及未来实盘，是否都基于可信的一致交易语义。** 如果在回测层就允许出现“参数存在但行为失效”的情况，那么后续整个执行体系都会失去可信性。

因此，这个工作不是单纯的“调一个参数 bug”，而是要同时解决两件绑定的事情：
1. **修复 TP 执行语义问题（ISSUE-1175）**，让 TP 阈值变化能够真实影响回测结果；
2. **建立专有 deterministic E2E order scenario dataset 与场景测试（ISSUE-1177）**，把订单生成、撮合、过期、再平衡冲突等行为钉死，避免今后再次出现“参数存在但功能无效”的 silent drift。

这里的关键升级是：本次验收不再满足于“结果必须有变化”，而是要求在**专有 E2E fixture dataset** 上对订单状态迁移、成交价格、持仓、现金、权益进行**精确断言**。也就是说，这批测试数据不是通用研究数据，也不是大历史样本，而是专门为了验证执行语义而设计的小型黄金场景数据集。

本 PRD 属于 AMS `Phase 1.5: Backtest Reliability Hardening` 的 P0 修复波次，是进入更大规模 Validation Framework（ISSUE-1172）和 Unified Broker Contract（ISSUE-1176）之前的阻塞项。它的目标不是一次性建完整框架，而是用一个真实且高价值的执行语义问题，驱动出第一批可信的 order-semantics E2E fixtures 与修复闭环。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. 改变 `tp_pos / tp_intra` 必须改变至少一项可观测回测结果，例如：
   - 卖出时点
   - trade path
   - `final_equity`
   - `weekly_performance`
2. Take-Profit 订单必须具备可信的生命周期：
   - 被真实创建
   - 在正确的 bar 窗口中可参与撮合
   - 若价格触发则成交
   - 若未触发则按明确定义过期或保留
3. Weekly rebalance 与 mid-week TP 必须具备明确优先级和一致语义，不能相互吞掉或导致重复卖出。
4. 同一持仓上的 TP / rebalance / stop-loss 行为必须具有一致的 order state transition 语义，不允许出现“表面挂单但对 holdings/cash/equity 无影响”。
5. 必须建立一批 **专有 deterministic E2E fixture datasets**，用于验证订单语义，而不仅仅是最终收益。
6. 在这些专有 E2E fixtures 上，测试断言应尽量精确到预期值，而不是只要求“结果要有变化”。
7. 这批 fixture 的设计与实现由 coder 完成，但 PRD 必须先定义清楚：
   - 必测场景有哪些；
   - 每个场景必须验证哪些外部可观察结果；
   - 哪些结果必须精确断言；
   - fixture 不得直接用生产全量历史数据切片替代。
8. 至少有一组 fixture 必须被明确设计成“低 TP 阈值与高 TP 阈值将走出不同交易路径”，用于证明 TP 参数是真正有效参数，而不是装饰参数。

### Non-Functional Requirements
1. 本次范围必须聚焦在 **execution semantics + minimal E2E fixtures**，不要扩展为完整 validation framework。
2. 回测测试必须可重复、可解释、可在 CI/preflight 中稳定运行。
3. 不允许依赖大而全的生产历史数据来证明订单语义；必须使用小型 deterministic fixture 构造可控场景。
4. 主干 CI / preflight 最终必须恢复全绿。

### Boundaries
- **In Scope**：TP order lifecycle、match/expire timing、rebalance-vs-TP conflict、deterministic fixture datasets、最小 order-semantics E2E tests。
- **Out of Scope**：完整 golden dataset / regression framework（ISSUE-1172）、统一 broker contract 设计（ISSUE-1176）、QMT paper/live 接入。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 先用专有 deterministic scenario fixture datasets 钉死交易语义
本次不应先拿大区间真实历史数据继续调收益，而应先构造 2-10 bar、1-3 个标的的小型**专有 E2E fixture datasets**，显式验证：
- 订单何时生成
- 何时生效
- 何时撮合
- 何时取消
- holdings / cash / avg_price / equity 如何变化

这些 fixture 的目标不是模拟真实市场统计分布，而是精确测试执行语义，因此它们必须：
- 小而稳定
- 可版本化
- 可重复
- 可精确断言预期数值

PRD 需要定义清楚的是：
- 哪些场景必须存在；
- 每个场景必须观察哪些状态与结果；
- 哪些结果要精确断言；
- fixture 不得偷懒直接拿全量历史数据切片替代。

交给 coder 自由发挥的是：
- 具体 CSV 如何构造；
- 每个 fixture 用几个交易日、几个标的；
- 测试文件如何组织；
- 如何把 expected values 固化进测试。

### 3.2 P0 必须把 Issue-1177 和 Issue-1175 绑定执行
执行顺序不是“先建大测试框架再修 bug”，而是：
1. 先写最小 scenario tests，让 bug 被 deterministic 地抓住；
2. 再修 TP 执行语义；
3. 再让这些 tests 转绿；
4. 最后让 CI/preflight 全绿。

### 3.3 关键技术检查点
本次实现必须重点审查以下模块：
- `ams/core/cb_rotation_strategy.py`
  - TP order 生成时机
  - effective_date 的设定
  - rebalance / TP 共存时的优先级
- `ams/core/sim_broker.py`
  - `_expire_old_orders()` 与 `match_orders()` 的调用顺序
  - LIMIT SELL 的撮合条件
  - order status transition
  - holdings/cash/avg_price 的更新时机
- `ams/runners/backtest_runner.py`
  - 每个 bar 内的执行顺序是否符合交易语义
- `tests/fixtures/` 与 `tests/` 相关目录
  - 新增专有 deterministic fixture CSV
  - 新增 order-semantics E2E / scenario tests

### 3.4 设计原则
- 不允许用 mock 掩盖订单语义问题。
- 对收益类结果的断言不是第一优先级，**状态机式断言** 才是第一优先级：
  - order created / pending / filled / canceled
  - holdings / cash / equity before/after
- 对于“next bar high 触发 TP”这类问题，必须能通过 fixture 直接复现并观察到状态迁移。
- 在专有 E2E fixtures 上，优先采用**精确断言**（例如某日成交、某个 limit_price、某个最终 cash/equity），仅在必要时辅以“阈值变化导致结果差异”的弱断言。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Next-bar high 触发 TP 成交**
  - **Given** 一个专有 deterministic E2E fixture，其中 Day 1 建仓，Day 2 的 `high` 明确高于 TP 价格，且该 fixture 预先定义了成交价格、成交数量与成交后的账户状态
  - **When** 运行 backtest
  - **Then** TP LIMIT SELL 必须进入可撮合窗口并被成交，且其 `order status`、成交价格、成交数量、`holdings`、`cash` 与 `equity` 必须精确匹配该 fixture 的预期值

- **Scenario 2: TP 订单不会在有效撮合窗口前被提前取消**
  - **Given** 一个 fixture，其中 Day N 挂出 1-day TP order，Day N+1 才是首个应参与撮合的窗口，且 fixture 已明确定义订单在 Day N、Day N+1 的期望状态
  - **When** 运行 backtest
  - **Then** 订单不得在 Day N+1 撮合前就因过期逻辑被取消，且订单状态迁移必须精确符合 fixture 预期

- **Scenario 3: Weekly rebalance 不得掩盖 mid-week TP**
  - **Given** weekly rebalance 模式下，一个专有 fixture 在周中价格路径触发 TP，并预先定义周中 TP 生效后的仓位与周末 rebalance 的后续动作
  - **When** backtest 运行到周中并继续推进到周末 rebalance
  - **Then** TP 必须先按定义生效，周末 rebalance 必须基于 TP 生效后的仓位状态继续执行，且相关仓位/现金结果必须精确匹配预期值

- **Scenario 4: 改变 TP 阈值必须改变结果**
  - **Given** 相同 deterministic fixture、相同非 TP 参数，并且 fixture 被设计成对低阈值 TP 与高阈值 TP 具有不同交易路径
  - **When** 分别使用低阈值 TP 与高阈值 TP 运行回测
  - **Then** 至少一项可观测结果必须不同，包括卖出时点、trade path、`final_equity` 或 `weekly_performance`，且在 fixture 已定义精确期望值的情况下应优先断言精确值

- **Scenario 5: 不允许重复卖出同一仓位**
  - **Given** 同一持仓同时可能受到 TP 与 rebalance 卖出影响，且 fixture 已定义允许的唯一正确状态迁移
  - **When** 回测推进到冲突窗口
  - **Then** 不得出现 double-sell、负持仓或超过持仓数量的卖出行为，且最终 order book / holdings / cash 必须精确符合预期

- **Scenario 6: 主干质量门禁恢复全绿**
  - **Given** 已新增专有 deterministic E2E fixtures 与 order-semantics scenario tests
  - **When** TP 执行语义修复完成
  - **Then** 新增测试、既有测试以及 preflight 必须全部通过

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
当前最大的质量风险不是“代码崩溃”，而是 **参数存在但行为无效**。如果订单语义没有被 deterministic 场景测试钉死，系统会继续出现“CLI 接受参数、结果却不受影响”的假象，导致研究结论不可信。

### Verification Strategy
1. **Dedicated Deterministic E2E Fixture Datasets（必须）**
   - 用 2-10 bar 的小型专有 CSV 数据集构造价格路径
   - 每个 fixture 只服务一个清晰语义点
   - fixture 必须可版本化、可重复，并带有明确的预期结果说明

2. **Precise Order State Assertions（必须）**
   - 不只断言“结果不同”
   - 优先断言精确预期：
     - order type / direction / limit_price / effective_date
     - order status transition
     - holdings / cash / equity 的精确数值
     - 关键 bar 的订单与账户状态

3. **Threshold Sensitivity Regression（必须）**
   - 在至少一个 fixture 中，低 TP 阈值和高 TP 阈值必须产生不同结果
   - 若 fixture 已明确预期结果，则优先断言精确值，而不是仅断言“不同”

4. **Fixture Ownership Rule**
   - PM/PRD 负责定义场景、验证目标、断言等级与边界条件
   - Coder 负责把这些要求落成具体 fixture CSV 与测试代码
   - Reviewer 必须审查 fixture 是否真的服务于 PRD 场景，而不是为了让测试通过而构造无意义路径

5. **Mocking Policy**
   - 对订单语义测试，禁止 mock 核心执行主路径（Strategy / Broker / Runner 的核心行为）
   - 可以 mock 不相关的外部依赖，但本 PRD 核心不需要外部依赖

### Quality Goal
让 TP 参数从“看起来存在”变成“真实驱动订单与权益变化”，并建立第一批能够长期保护 AMS 执行语义的专有 deterministic E2E fixture tests，使关键订单语义可以被精确断言，且 Auditor 能基于 PRD 清楚理解为什么这些 fixture 必须存在、它们应该证明什么。

## 6. Framework Modifications (框架防篡改声明)
- None

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 将 P0 定义为绑定执行的 `ISSUE-1175 + ISSUE-1177`，先用最小 deterministic E2E fixtures 钉死 TP 语义 bug，再修复执行链路。
- **v1.1**: 将测试策略从“结果必须有变化”升级为“在专有 E2E fixture dataset 上优先做精确断言”，明确该类测试数据集应为小型、稳定、专门设计的订单语义黄金场景。
- **Audit Rejection (v1.1)**: Pending
- **v2.0 Revision Rationale**: Pending

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements
- **`canonical_code_root`**:
```text
/root/projects/AMS
```

- **`runtime_cb_dataset`**:
```text
/root/.openclaw/workspace/data/cb_history_factors.csv
```

- **`e2e_fixture_directory`**:
```text
tests/fixtures/
```

- **`fixture_design_principle`**:
```text
Dedicated deterministic E2E fixture datasets must be small, versioned, reproducible, and precise enough to support exact assertions for order lifecycle, holdings, cash, and equity.
```

- **`tp_mode_both_error`**:
```text
ERROR: --tp-mode '{tp_mode}' requires both --tp-pos and --tp-intra to be set.
```

- **`scenario_test_example_name_1`**:
```text
test_tp_limit_order_triggers_on_next_bar_high
```

- **`scenario_test_example_name_2`**:
```text
test_tp_limit_order_expires_only_after_valid_match_window
```

- **`scenario_test_example_name_3`**:
```text
test_weekly_rebalance_does_not_mask_midweek_take_profit
```

- **`scenario_test_example_name_4`**:
```text
test_daily_tp_threshold_changes_affect_outcome
```

- **`scenario_test_example_name_5`**:
```text
test_weekly_tp_threshold_changes_affect_outcome
```

- **`scenario_test_example_name_6`**:
```text
test_tp_and_rebalance_do_not_double_sell_position
```
