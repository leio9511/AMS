---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix_Take_Profit_Execution_Semantics_and_Order_E2E_Scenarios

## 1. Context & Problem (业务背景与核心痛点)
AMS 当前已经具备可运行的可转债双低轮动回测能力，`HistoryDataFeed`、`CBRotationStrategy`、`SimBroker`、`BacktestRunner` 均已存在，`main_runner.py` 统一 CLI 主路径也已打通，能够在指定数据路径下执行真实回测。这意味着系统现在的主要矛盾不再是“回测跑不起来”，而是“回测结果是否可信、是否真实反映交易执行语义”。

当前暴露出的核心问题集中在 Take-Profit（TP）和 Stop-Loss（SL）执行语义上：CLI 参数虽然能够被系统接收，但 TP 与 SL 在真实回测结果中的影响要么缺失，要么不可信。此前已现场复现实验表明，在 daily rebalance 与 weekly rebalance 下，改变 `tp_pos/tp_intra` 时，结果曾经完全不敏感；修复后 TP 已恢复敏感性，但 stop-loss 在多组 sweep 中仍未表现出参数敏感性。这说明问题不是参数没有传入，而是 **订单虽然被配置和创建，却没有被放进一个可被审计、可被验证的 bar-level execution contract 里**。

根据当前排查，最可疑的根因不是单一公式错误，而是核心执行语义存在 contract hole：
- bar 内各阶段顺序没有被唯一冻结；
- TP / stop-loss / rebalance 的冲突优先级没有被完全写死；
- TP/SL 单的 activation、matching、expiration 规则仍可能被实现层自由解释；
- stop-loss 与 rebalance 的成交价规则如果不明确冻结，则 cash/equity 的精确断言会失去基础。

这类问题的危险性很高，因为它不会像语法错误那样直接崩溃，而是会制造一种“系统正常工作”的错觉，最终污染策略研究结论。Boss 当前关心的不是某一组参数收益高低，而是：**回测、后续 miniQMT 模拟盘、以及未来实盘，是否都基于可信的一致交易语义。** 如果在回测层就允许出现“参数存在但行为失效”或“时间语义随实现漂移”的情况，那么后续整个执行体系都会失去可信性。

因此，这个工作不是单纯的“调一个参数 bug”，而是要同时解决两件绑定的事情：
1. **修复 TP / stop-loss 执行语义问题（当前 blocker 以 ISSUE-1175 为锚点）**，让参数变化能够真实影响回测结果；
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
2. 改变 `stop-loss` 阈值必须改变至少一项可观测回测结果，例如：
   - 卖出时点
   - trade path
   - `final_equity`
   - `weekly_performance`
3. Take-Profit 订单必须具备可信的生命周期：
   - 被真实创建
   - 在正确的 bar 窗口中可参与撮合
   - 若价格触发则成交
   - 若未触发则按明确定义过期或保留
4. Stop-loss 属于风险退出，不是普通调仓信号。只要 stop-loss 条件在周中触发，就必须立即生效，不能等待下一个 rebalance day。
5. Weekly rebalance 与 mid-week TP / SL 必须具备明确优先级和一致语义，不能相互吞掉或导致重复卖出。
6. 同一持仓上的 TP / rebalance / stop-loss 行为必须具有一致的 order state transition 语义，不允许出现“表面挂单但对 holdings/cash/equity 无影响”或 double-sell。
7. 必须建立一批 **专有 deterministic E2E fixture datasets**，用于验证订单语义，而不仅仅是最终收益。
8. 在这些专有 E2E fixtures 上，测试断言应尽量精确到预期值，而不是只要求“结果要有变化”。
9. 这批 fixture 的设计与实现由 coder 完成，但 PRD 必须先定义清楚：
   - 必测场景有哪些；
   - 每个场景必须验证哪些外部可观察结果；
   - 哪些结果必须精确断言；
   - fixture 不得直接用生产全量历史数据切片替代。
10. 至少有一组 fixture 必须被明确设计成“低 TP 阈值与高 TP 阈值将走出不同交易路径”，用于证明 TP 参数是真正有效参数，而不是装饰参数。
11. 至少有一组 fixture 必须被明确设计成“紧 stop-loss（如 -1%）与宽 stop-loss（如 -5%）将走出不同交易路径”，用于证明 stop-loss 参数同样是真正有效参数。
12. 本次修改触及 `Strategy` / `Broker` / `Runner` 的核心执行语义，因此必须同时定义 rollback / containment 策略，防止修复失败时把混合语义留在主干。

### Non-Functional Requirements
1. 本次范围必须聚焦在 **execution semantics + minimal E2E fixtures**，不要扩展为完整 validation framework。
2. 回测测试必须可重复、可解释、可在 CI/preflight 中稳定运行。
3. 不允许依赖大而全的生产历史数据来证明订单语义；必须使用小型 deterministic fixture 构造可控场景。
4. 主干 CI / preflight 最终必须恢复全绿。

### Boundaries
- **In Scope**：TP / stop-loss order lifecycle、match/expire timing、rebalance-vs-TP-vs-SL conflict、deterministic fixture datasets、最小 order-semantics E2E tests、rollback/containment strategy。
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

### 3.2 P0 必须把 Issue-1177 和当前执行语义 bug 绑定执行
执行顺序不是“先建大测试框架再修 bug”，而是：
1. 先写最小 scenario tests，让 bug 被 deterministic 地抓住；
2. 再修 TP / stop-loss 执行语义；
3. 再让这些 tests 转绿；
4. 最后让 CI/preflight 全绿。

### 3.3 关键技术检查点
本次实现必须重点审查以下模块：
- `ams/core/cb_rotation_strategy.py`
  - TP order 生成时机
  - stop-loss 触发时机
  - effective_date 的设定
  - rebalance / TP / SL 共存时的优先级
- `ams/core/sim_broker.py`
  - `_expire_old_orders()` 与 `match_orders()` 的调用顺序
  - LIMIT SELL 的撮合条件
  - market sell 的成交价规则
  - rebalance buy/sell 的成交价规则
  - order status transition
  - holdings/cash/avg_price 的更新时机
- `ams/runners/backtest_runner.py`
  - 每个 bar 内的执行顺序是否符合交易语义
- `tests/fixtures/` 与 `tests/` 相关目录
  - 新增专有 deterministic fixture CSV
  - 新增 order-semantics E2E / scenario tests

### 3.4 Rollback / Containment Strategy
本次修改触及 `Strategy` / `Broker` / `Runner` 的核心执行语义，属于高风险底层行为变更。除了测试隔离之外，必须具备明确的运行时回滚与隔离策略：

1. **Baseline Reference**
   - 本 PRD 的 baseline 行为以当前进入开发前的主干语义为准，若修复后的实现破坏既有主路径或导致关键 scenario fixtures / preflight 失败，必须能够回退到 baseline commit 的行为。
2. **Guarded Replacement Principle**
   - 本次修改只能替换与 `TP / stop-loss / bar-level order lifecycle` 直接相关的最小代码路径，不允许在同一 PR 中顺手重写无关执行语义。
3. **Failure Containment Rule**
   - 如果新的执行语义在 deterministic fixtures、主路径 smoke test 或 preflight 中失败，则必须停止继续扩散修改；不得在主干中保留“部分新语义 + 部分旧语义混合”的半完成状态。
4. **Reviewer Auditability**
   - Reviewer 必须能明确判断：当新语义失败时，系统是否还能快速恢复到修复前的稳定行为，而不是继续把语义漂移扩散到 broker 核心。

### 3.5 必须冻结的执行语义契约
为防止 coder 在时间语义上自由发挥，本 PRD 直接冻结以下原则：
1. **统一状态机原则**：daily 与 weekly 模式共享同一套执行状态机与 bar-level contract；两者唯一差异在于“目标仓位/调仓信号何时产生”，而不是订单创建、激活、撮合、过期、账户更新的底层语义不同。
2. **日线保守语义原则**：在仅有日线 OHLC 数据的回测中，系统不得推断同一 bar 内 high 与 low 的先后顺序，也不得假设 same-bar TP/SL 谁先成交。所有交易信号都在 signal bar 形成，而成交发生在后续合法撮合窗口。
3. **Stop-loss 优先级**：stop-loss 是风险退出，只要在周中 signal bar 触发，就必须获得高于 TP 与 rebalance 的执行优先级，不能等待下一个 weekly rebalance day。
4. **Weekly rebalance 边界**：weekly rebalance 只决定周期性调仓节奏，不得屏蔽 mid-week 的风险退出（stop-loss）或 mid-week 的止盈意图。weekly 模式下，真正改变的是信号产生频率，而不是底层撮合语义。
5. **唯一卖出路径**：同一持仓在同一个 signal bar 内，如果 TP / rebalance / stop-loss 同时具备潜在卖出条件，系统必须在进入下一合法撮合窗口之前选出唯一卖出路径，禁止重复卖出与负持仓。
6. **场景级精确断言**：至少在专有 fixture 上，必须精确断言 order status transition、signal bar、activation bar、fill bar、holdings、cash、equity，而不能只断言“结果有变化”。

### 3.6 Canonical Bar-Level Timeline（冻结版）
对于单个交易日 bar，回测引擎必须遵守以下唯一顺序，不允许 coder 自由改写语义：

1. **Bar Input Ready**
   - 读取当日 OHLCV / premium / flags 等数据切片。
2. **Activation Phase**
   - 所有在前一 signal bar 已提交、且根据本 PRD 语义应在当前 bar 生效的订单，进入可参与当前 bar 撮合的状态。
3. **Matching Phase**
   - 先处理所有可在当前 bar 成交的既有订单（包括来自前一 signal bar 已经获得执行权的 TP / stop-loss / rebalance 相关订单）。
4. **Expiration Phase**
   - 只有在当前 bar 的全部合法撮合机会已经结束后，才允许把本 bar 内未成交且应过期的 day-order 标记为 `CANCELED`。
5. **Portfolio Snapshot Phase**
   - 基于当前 bar 撮合后的 holdings / cash / prices 更新 equity snapshot。
6. **Signal Evaluation Phase**
   - Strategy 在当前 bar 末尾基于最新上下文评估新的目标仓位、TP / stop-loss / rebalance 意图；这个 bar 被称为 signal bar。
7. **Execution Arbitration Phase**
   - 如果同一持仓在同一个 signal bar 内同时出现 TP / stop-loss / rebalance 卖出意图，必须在当前 bar 末尾按优先级矩阵选出唯一卖出路径，并把它转换为将在下一合法撮合窗口执行的订单。
8. **Order Creation / Update Phase**
   - Strategy / Broker 生成新的 order objects，并将它们登记到 order book，供下一次合法撮合窗口使用。

**硬规则：**
- 当前 bar 新创建的订单，不得回头参与同一 bar 的撮合，本 PRD 不授权 same-bar execution。
- 订单的过期判断不得发生在其首个合法撮合窗口之前。
- 同一 signal bar 内的冲突解决发生在 bar 末尾，成交发生在下一个合法撮合窗口；不允许混用 same-bar 与 next-bar 两套语义。

### 3.7 Stop-Loss Trigger / Fill Contract
本 PRD 冻结 stop-loss 的时间语义如下：

1. **Trigger Bar**
   - stop-loss 条件在 Strategy 的 signal evaluation 中根据当前 bar 可见数据进行判断；该 bar 被定义为 stop-loss 的 signal bar。
2. **Fill Bar**
   - stop-loss 触发于 signal bar N 时，卖出订单的首次合法撮合窗口是 **bar N+1**，而不是 bar N 当下回填成交。
3. **Fill Price Rule**
   - stop-loss 卖出订单一旦在 signal bar N 触发，其成交价必须被固定为 **bar N+1 的 open price**。
   - 在本 PRD 所覆盖的 deterministic E2E fixtures 中，不允许把 stop-loss market sell 的成交价写成“沿用 broker 既有规则”或其他隐式规则。
   - 若后续系统仍保留 slippage 语义，则该 slippage 必须作为单独显式规则重新定义；本 PRD 当前的 canonical stop-loss 成交价规则就是 `next bar open`。
4. **Immediate Effect in Weekly Mode**
   - “立即生效”的含义在本 PRD 中被定义为：一旦周中 signal bar 触发 stop-loss，该持仓必须在下一个合法撮合窗口优先退出，不允许继续等到周末 rebalance 才处理。
5. **No Same-Bar Priority Fiction**
   - 在当前日线 OHLC 模型下，不允许声明“同一 bar 中 stop-loss 压过已经进入合法撮合窗口并成交的 TP”。若 stop-loss 想在同一 signal bar 中赢过 TP，它必须通过 next-window 优先级仲裁获得下一撮合窗口的唯一执行权，而不是伪造 same-bar intrabar path。

### 3.8 TP / Stop-Loss / Rebalance Priority Matrix
当同一持仓在同一个 signal bar 内同时满足多个卖出条件时，必须遵守以下唯一优先级：

1. **Stop-Loss**（最高优先级，风险退出）
2. **Take-Profit**
3. **Rebalance Sell**（最低优先级，周期性仓位调整）

解释：
- 这里的“优先级”指的是 **谁获得下一个合法撮合窗口的唯一执行权**，而不是 same-bar intrabar path 的虚构先后顺序。
- 如果 stop-loss 与 TP 在同一个 signal bar 都被判定为可触发，则 stop-loss 获胜，TP 不得再获得下一撮合窗口的独立执行权。
- 如果持仓已因 stop-loss 或 TP 退出，则该持仓对应的 rebalance 卖出意图不得再重复卖出。
- 如果 rebalance 已经把仓位降为 0，则与该仓位绑定的 TP 挂单不得继续保留为有效卖单。

### 3.9 Rebalance Order Activation / Fill Contract
本 PRD 也必须冻结 rebalance buy/sell 的执行语义，否则 cash/equity 的精确断言会失去基础：

1. **Rebalance Signal Bar**
   - rebalance 的买卖意图在当前 bar 的 signal evaluation 阶段形成。
2. **Rebalance Fill Bar**
   - rebalance 相关 market buy / market sell 订单的首个合法撮合窗口是 **signal bar 的下一个交易日 bar**。
3. **Rebalance Fill Price Rule**
   - 在本 PRD 覆盖的 deterministic E2E fixtures 中，rebalance market buy 与 market sell 的成交价必须显式采用 **next bar open price** 规则。
   - 不允许对 rebalance buy/sell 的成交价使用隐式“沿用 broker 既有规则”的模糊表述。
4. **Consistency Requirement**
   - stop-loss、TP（若为 market-equivalent exit path）、rebalance sell 的 next-window 语义必须共享同一 bar-level execution model；不得为不同卖出路径混用不同的默认成交窗口。

### 3.10 Existing TP Order Handling Rules
当已有 TP 挂单存在，而后续又发生 stop-loss 或 rebalance 卖出时，必须遵守以下规则：

1. **TP vs Stop-Loss**
   - 若 stop-loss 成为最终获胜卖出路径，则所有针对同一仓位的 TP 挂单必须在成交后被取消或失效，不能继续保留为可成交订单。
2. **TP vs Rebalance**
   - 若 rebalance 卖出路径减少或清空了该持仓，则不允许保留一个会导致超卖的旧 TP 挂单。
3. **禁止双卖**
   - 系统必须保证任意时点的累计可卖数量不超过当前持仓数量。
4. **Reviewer 可审计性**
   - 对上述规则，fixture 必须能观察到至少一种显式状态结果：`FILLED`、`CANCELED`、`REJECTED` 或持仓数量变化后的 order invalidation。

### 3.11 设计原则
- 不允许用 mock 掩盖订单语义问题。
- 对收益类结果的断言不是第一优先级，**状态机式断言** 才是第一优先级：
  - order created / pending / filled / canceled
  - holdings / cash / equity before/after
- 对于“next bar high 触发 TP”以及“周中 stop-loss 立即退出”这类问题，必须能通过 fixture 直接复现并观察到状态迁移。
- 在专有 E2E fixtures 上，优先采用**精确断言**（例如某日成交、某个 limit_price、某个最终 cash/equity），仅在必要时辅以“阈值变化导致结果差异”的弱断言。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Next-bar high 触发 TP 成交**
  - **Given** 一个专有 deterministic E2E fixture，其中 Day 1 建仓，Day 2 的 `high` 明确高于 TP 价格，且该 fixture 预先定义了成交价格、成交数量与成交后的账户状态
  - **When** 运行 backtest
  - **Then** TP LIMIT SELL 必须在其首个合法撮合窗口被成交，且其 `order status`、成交价格、成交数量、`holdings`、`cash` 与 `equity` 必须精确匹配该 fixture 的预期值

- **Scenario 2: TP 订单不会在有效撮合窗口前被提前取消**
  - **Given** 一个 fixture，其中 Day N 挂出 1-day TP order，Day N+1 才是首个应参与撮合的窗口，且 fixture 已明确定义订单在 Day N、Day N+1 的期望状态
  - **When** 运行 backtest
  - **Then** 订单不得在 Day N+1 撮合前就因过期逻辑被取消，且订单状态迁移必须精确符合 fixture 预期

- **Scenario 3: Weekly rebalance 不得掩盖 mid-week TP**
  - **Given** weekly rebalance 模式下，一个专有 fixture 在周中价格路径触发 TP，并预先定义周中 TP 生效后的仓位与周末 rebalance 的后续动作
  - **When** backtest 运行到周中并继续推进到周末 rebalance
  - **Then** TP 必须先按定义生效，周末 rebalance 必须基于 TP 生效后的仓位状态继续执行，且相关仓位/现金结果必须精确匹配预期值

- **Scenario 4: Weekly rebalance 不得掩盖 mid-week stop-loss**
  - **Given** weekly rebalance 模式下，一个专有 fixture 在周中价格路径触发 stop-loss，并预先定义 stop-loss 生效后的仓位与周末 rebalance 的后续动作
  - **When** backtest 运行到周中并继续推进到周末 rebalance
  - **Then** stop-loss 必须在其首个合法撮合窗口立即生效，不能等到周末 rebalance 才退出，且相关 order status、holdings、cash、equity 必须精确匹配预期值

- **Scenario 5: TP 与 stop-loss 同一 signal bar 同时满足时的唯一优先级**
  - **Given** 一个专有 fixture，使同一持仓在同一个 signal bar 内同时满足 TP 与 stop-loss 条件
  - **When** 运行 backtest
  - **Then** 必须严格按本 PRD 定义的 next-window 优先级矩阵选出唯一卖出路径，另一条路径不得再获得独立执行权，且相关 order status / holdings / cash 必须精确符合预期

- **Scenario 6: 改变 TP 阈值必须改变结果**
  - **Given** 相同 deterministic fixture、相同非 TP 参数，并且 fixture 被设计成对低阈值 TP 与高阈值 TP 具有不同交易路径
  - **When** 分别使用低阈值 TP 与高阈值 TP 运行回测
  - **Then** 至少一项可观测结果必须不同，包括卖出时点、trade path、`final_equity` 或 `weekly_performance`，且在 fixture 已定义精确期望值的情况下应优先断言精确值

- **Scenario 7: 改变 stop-loss 阈值必须改变结果**
  - **Given** 相同 deterministic fixture、相同非 stop-loss 参数，并且 fixture 被设计成对紧 stop-loss（如 `-1%`）与宽 stop-loss（如 `-5%`）具有不同交易路径
  - **When** 分别使用紧 stop-loss 与宽 stop-loss 运行回测
  - **Then** 至少一项可观测结果必须不同，包括卖出时点、trade path、`final_equity` 或 `weekly_performance`，且在 fixture 已定义精确期望值的情况下应优先断言精确值

- **Scenario 8: 不允许重复卖出同一仓位**
  - **Given** 同一持仓同时可能受到 TP 与 rebalance 卖出影响，且 fixture 已定义允许的唯一正确状态迁移
  - **When** 回测推进到冲突窗口
  - **Then** 不得出现 double-sell、负持仓或超过持仓数量的卖出行为，且最终 order book / holdings / cash 必须精确符合预期

- **Scenario 9: 回滚与隔离策略必须可执行**
  - **Given** 本次修复触及 `Strategy` / `Broker` / `Runner` 的核心执行语义
  - **When** 新执行语义导致 deterministic fixtures、主路径 smoke test 或 preflight 失败
  - **Then** 必须能够通过既定 rollback / containment strategy 阻止语义漂移继续扩散，并恢复到 baseline 行为，而不能把半完成的混合语义留在主干

- **Scenario 10: 主干质量门禁恢复全绿**
  - **Given** 已新增专有 deterministic E2E fixtures 与 order-semantics scenario tests
  - **When** TP / stop-loss 执行语义修复完成
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
   - 在至少一个 fixture 中，紧 stop-loss 与宽 stop-loss 必须产生不同结果
   - 若 fixture 已明确预期结果，则优先断言精确值，而不是仅断言“不同”

4. **Fixture Ownership Rule**
   - PM/PRD 负责定义场景、验证目标、断言等级与边界条件
   - Coder 负责把这些要求落成具体 fixture CSV 与测试代码
   - Reviewer 必须审查 fixture 是否真的服务于 PRD 场景，而不是为了让测试通过而构造无意义路径

5. **Mocking Policy**
   - 对订单语义测试，禁止 mock 核心执行主路径（Strategy / Broker / Runner 的核心行为）
   - 可以 mock 不相关的外部依赖，但本 PRD 核心不需要外部依赖

### Quality Goal
让 TP / stop-loss 参数从“看起来存在”变成“真实驱动订单与权益变化”，并建立第一批能够长期保护 AMS 执行语义的专有 deterministic E2E fixture tests，使关键订单语义可以被精确断言，且 Auditor 能基于 PRD 清楚理解为什么这些 fixture 必须存在、它们应该证明什么。更进一步，本 PRD 必须把日线回测的 canonical execution model 冻结成唯一解释：signal-on-bar、fill-on-next-bar、明确的 fill price rule、明确的 next-window 冲突优先级，而不是把时间语义留给 coder 或现存 broker 实现自由发挥。

## 6. Framework Modifications (框架防篡改声明)
- None

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 将 P0 定义为绑定执行的 `ISSUE-1175 + ISSUE-1177`，先用最小 deterministic E2E fixtures 钉死 TP 语义 bug，再修复执行链路。
- **v1.1**: 将测试策略从“结果必须有变化”升级为“在专有 E2E fixture dataset 上优先做精确断言”，明确该类测试数据集应为小型、稳定、专门设计的订单语义黄金场景。
- **v1.2**: 冻结 weekly 模式下 stop-loss 的语义，明确其为周中立即生效的风险退出，不得被 weekly rebalance 掩盖。
- **v1.3**: 引入 bar-level timeline、TP/SL/rebalance 优先级矩阵，以及 stop-loss fill price hard rule 与 rollback/containment 方案，回应 Auditor 对时间语义与运行时风险控制的驳回意见。
- **v1.4**: 切换到业界更稳妥的日线保守语义：signal-on-bar、fill-on-next-bar、next-window arbitration，显式禁止从日线 OHLC 推断 same-bar intrabar path。
- **Audit Rejection (v1.4)**: Pending
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

- **`stop_loss_fill_price_rule`**:
```text
A stop-loss triggered on signal bar N must be executed on bar N+1 at the next bar open price.
```

- **`rebalance_fill_price_rule`**:
```text
A rebalance market buy or market sell created on signal bar N must be executed on bar N+1 at the next bar open price.
```

- **`rollback_containment_rule`**:
```text
If the new execution semantics break deterministic fixtures, smoke tests, or preflight, the implementation must be containable and restorable to the baseline behavior instead of leaving a mixed semantic state on the mainline.
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
test_weekly_rebalance_should_not_mask_stop_loss
```

- **`scenario_test_example_name_5`**:
```text
test_daily_tp_threshold_changes_affect_outcome
```

- **`scenario_test_example_name_6`**:
```text
test_weekly_tp_threshold_changes_affect_outcome
```

- **`scenario_test_example_name_7`**:
```text
test_daily_stop_loss_threshold_changes_affect_outcome
```

- **`scenario_test_example_name_8`**:
```text
test_tp_and_stop_loss_same_bar_priority
```

- **`scenario_test_example_name_9`**:
```text
test_tp_and_rebalance_do_not_double_sell_position
```
