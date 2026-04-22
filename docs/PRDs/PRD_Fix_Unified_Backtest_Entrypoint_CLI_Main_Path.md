---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix_Unified_Backtest_Entrypoint_CLI_Main_Path

## 1. Context & Problem (业务背景与核心痛点)
AMS 2.0 已经具备核心回测引擎能力，`HistoryDataFeed`、`CBRotationStrategy`、`SimBroker`、`BacktestRunner` 均可在正确数据与路径下运行。但当前对外宣称的统一入口 `main_runner.py` 仍然存在主执行链路缺陷，导致它“看起来像可用 CLI”，实际上无法直接运行真实回测。

现场复现表明，执行正式命令时：

```text
python3 main_runner.py --strategy cb_rotation --start-date 2025-01-06 --end-date 2026-01-06 --capital 4000000 --top-n 10 --rebalance daily --tp-mode both --tp-pos 0.20 --tp-intra 0.08 --sl -0.08 --format json
```

会触发：

```text
TypeError: CBRotationStrategy.__init__() got an unexpected keyword argument 'start_date'
```

根因不是回测引擎失效，而是 `main_runner.py` 将 CLI 参数整包错误透传给 `CBRotationStrategy.__init__()`，没有根据职责将参数分发给 Strategy / Broker / Runner / Config 层。结果是：
- CLI 帮助文案存在；
- JSON 输出工具存在；
- 但主路径并未真正打通；
- 当前测试与验收未命中该真实主路径，形成“伪打通”。

本 PRD 的目标不是建设完整的 Validation Framework（那是后续独立工作），而是把 `main_runner.py` 的真实 CLI 主路径修通，并补上一条最小但真实的 smoke test，作为该 bug 的关闭条件。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. `main_runner.py` 必须能够作为 AMS 2.0 的统一回测入口，直接执行真实回测。
2. CLI 参数必须按职责正确路由：
   - `start_date` / `end_date` 交给 `BacktestRunner.run(...)`
   - `capital` 交给 `SimBroker(initial_cash=...)`
   - `rebalance` 映射为策略的 `rebalance_period`
   - `sl` 映射为策略的 `stop_loss_threshold`
   - `tp_pos` / `tp_intra` 组装为 `TakeProfitConfig`
   - 仅策略真正接受的参数传给 `CBRotationStrategy`
3. `main_runner.py` 必须使用 AMS canonical path：
   - Code root: `/root/projects/AMS`
   - Historical CB dataset: `/root/projects/AMS/data/cb_history_factors.csv`
4. `--format json` 仍需输出符合现有 PRD 约束的 JSON 结果。
5. `--help`、参数校验错误、策略不存在错误等既有契约不能被破坏。

### Non-Functional Requirements
1. 修复范围必须聚焦于统一入口真实主路径，不引入与本 bug 无关的验证框架扩张。
2. 不得通过 mock 主路径来伪造“修复完成”。
3. 必须保留 AMS 2.0 当前分层架构（DataFeed / Strategy / Broker / Runner），不能为了修 bug 把职责重新耦合回单脚本。

### Boundaries
- **In Scope**：`main_runner.py` 参数路由、必要的策略工厂/注册微调、真实 smoke test。
- **Out of Scope**：完整 golden dataset / regression framework、walk-forward 体系、Phase 2 Live QMT 接管。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本次修复必须遵守 AMS 的“CD Player Pattern”与分层职责。

### 3.1 正确的参数分层
`main_runner.py` 不得再把整包 CLI 参数直接塞给 `StrategyFactory.create_strategy(...)`。正确架构应为：

1. **CLI Layer** (`main_runner.py`)
   - 解析 11 个 CLI 参数
   - 做参数合法性校验
   - 构造 DataFeed、Broker、Strategy、Runner

2. **Data Layer**
   - 使用 `HistoryDataFeed` 读取 `/root/projects/AMS/data/cb_history_factors.csv`

3. **Broker Layer**
   - 使用 `SimBroker(initial_cash=args.capital)`

4. **Strategy Layer**
   - 只向 `CBRotationStrategy` 传递其实际接受的参数
   - `rebalance` -> `rebalance_period`
   - `sl` -> `stop_loss_threshold`
   - `tp_mode` 直接映射
   - `tp_pos` / `tp_intra` 通过 `TakeProfitConfig` 注入，而不是伪造构造器参数

5. **Runner Layer**
   - 使用 `BacktestRunner.run(args.start_date, args.end_date)` 负责真实执行区间

### 3.2 测试策略上的最小补口
本 bug 的关闭条件必须包含一条真实 smoke test：
- 不允许 mock `StrategyFactory.create_strategy`
- 不允许 mock `CBRotationStrategy`
- 不允许 mock `BacktestRunner`
- 必须真实执行 `python3 main_runner.py ... --format json`
- 使用小型 fixture 数据集，以避免依赖完整生产数据集导致测试过重

### 3.3 文件边界
优先修改以下现有文件：
- `main_runner.py`
- `tests/test_main_runner.py`
- `ams/core/factory.py`（仅在注册/创建逻辑确有必要时）

如需要新增 fixture，必须把它视为测试资产，不得污染生产数据目录。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 统一 CLI 主路径可执行**
  - **Given** `/root/projects/AMS` 下存在可用的可转债历史测试数据集
  - **When** 执行统一入口命令并传入 `cb_rotation`、日期区间、资金、调仓、止盈止损参数
  - **Then** 命令必须退出码为 0，且不得出现 `TypeError`、参数错位或构造器参数不匹配错误

- **Scenario 2: JSON 输出链路真实打通**
  - **Given** 以 `--format json` 运行 `main_runner.py`
  - **When** 回测成功执行完成
  - **Then** 输出必须是合法 JSON，且包含 `summary` 与 `weekly_performance` 结构

- **Scenario 3: CLI 参数被正确分发到各层**
  - **Given** `start-date/end-date/capital/rebalance/sl/tp-pos/tp-intra` 等参数被提供
  - **When** `main_runner.py` 构造回测对象
  - **Then** 这些参数必须分别路由到 Runner / Broker / Strategy / Config 的正确层级，而不是整包透传给策略构造器

- **Scenario 4: 既有契约不被破坏**
  - **Given** 用户执行 `python3 main_runner.py --help` 或输入非法参数
  - **When** CLI 解析与校验发生
  - **Then** 既有帮助文案、参数校验错误信息与策略不存在错误信息仍保持兼容

- **Scenario 5: Canonical Path 固化**
  - **Given** AMS 的正式代码目录与数据文件已标准化
  - **When** 执行统一回测入口
  - **Then** 默认正式运行路径必须以 `/root/projects/AMS` 与 `/root/projects/AMS/data/cb_history_factors.csv` 为准

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
核心风险不是“代码跑不起来就报错”，而是“CLI 看起来实现了，但真实主路径没有被执行测试命中”，从而造成伪验收通过。

### Verification Strategy
1. **保留现有轻量测试**
   - `--help`
   - 参数校验错误
   - JSON 结构/格式基础测试

2. **新增真实 smoke test（必须）**
   - 使用小型 fixture CSV
   - 真执行 `python3 main_runner.py ... --format json`
   - 不 mock 主路径核心对象
   - 断言 exit code、JSON 结构、关键字段存在

3. **Fixture 设计原则**
   - 小数据集，但必须足以让 `cb_rotation` 跑完最小区间
   - 不依赖完整生产数据，确保 CI/preflight 可快速稳定执行

### Quality Goal
修复完成后的目标不是“测试过了”，而是“统一回测入口真实可执行，并且今后再出现主路径打不通时，smoke test 能第一时间拦住”。

## 6. Framework Modifications (框架防篡改声明)
- None

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 将统一回测入口 bug 定义为“参数错位透传”，并收敛范围为修复真实主路径 + 增加最小 smoke test。
- **Audit Rejection (v1.0)**: Pending
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

- **`canonical_cb_dataset`**:
```text
/root/projects/AMS/data/cb_history_factors.csv
```

- **`cli_smoke_test_command_example`**:
```text
python3 main_runner.py --strategy cb_rotation --start-date 2025-01-06 --end-date 2025-01-10 --capital 4000000 --top-n 10 --rebalance daily --tp-mode both --tp-pos 0.20 --tp-intra 0.08 --sl -0.08 --format json
```

- **`tp_mode_validation_error`**:
```text
ERROR: --tp-mode '{tp_mode}' requires both --tp-pos and --tp-intra to be set.
```

- **`strategy_not_found_error`**:
```text
ERROR: Strategy '{strategy_id}' not found in registry.
```
