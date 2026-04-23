---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Validation_Framework_MVP

## 1. Context & Problem (业务背景与核心痛点)
AMS 已经跨过了“回测能不能跑”的初级阶段，当前真正的风险不再是程序直接报错，而是 **系统可以继续输出回测结果，但这些结果是否仍然可信、是否会在未来代码演进中发生 silent drift，我们还没有正式的验证闭环来证明。**

过去一轮工作的价值，不只是修复了 Take-Profit / Stop-Loss 执行语义，而是已经通过人工 sweep 验证：关键参数现在会真实影响回测结果。例如在同一时间窗、同一本金、同一双低轮动条件下，改变 `sl` / `tp_pos` / `tp_intra`，`final_equity`、`total_return`、`max_drawdown`、`calmar_ratio` 都会变化。这说明执行语义修复已经开始生效，也说明 AMS 已经具备了建立第一版 validation baseline 的现实基础。

但当前结论仍然停留在“人工回测 + 人工比对”的阶段，没有被固化为：
- 可自动运行的 smoke suite
- 有唯一输入、唯一输出契约的 golden regression baseline
- 能发现“参数失效但系统不崩”的 sensitivity sanity gate
- 能阻止默认路径与 canonical path 行为分叉的 consistency gate

如果不补上这套 Validation Framework，AMS 将长期暴露在以下风险中：
1. **Silent Drift 风险**
   - 代码改了，回测还能跑，但 bar-level execution semantics、撮合顺序、参数映射、报告口径可能已经悄悄变化；
   - 这种漂移不会像语法错误一样炸掉，而会污染研究结论。
2. **参数失效风险**
   - 参数存在，但已经不再影响结果；
   - 没有 sensitivity sanity gate 时，这类 bug 只能靠偶然 sweep 才发现。
3. **Baseline 污染风险**
   - 如果 golden baseline 直接绑定到一个仍在继续演进的“日常数据文件”，未来数据更新会让 baseline 自己漂移；
   - 结果就会变成“测试在比较两个都在变化的东西”，无法裁决 drift 到底来自代码还是来自输入数据变化。
4. **研究与实盘脱节风险**
   - 在没有 smoke / golden / sanity / consistency gate 的情况下，后续接 QMT 模拟盘或实盘，只会把“能跑但未被验证”的逻辑推进到更高风险环境。

Boss 已明确接受以下组织方式：
- 每个 bug fix PR 内必须有真实 smoke test，作为关闭条件；
- 完整的 golden dataset / regression / walk-forward 体系作为独立后续工作推进，不混进单个 execution semantics bugfix；
- AMS 当前处于 `Phase 1.5: Backtest Reliability Hardening`，进入 Phase 2（Live QMT Integration）之前，必须完成 unified CLI 可执行、smoke test、以及第一版 validation baseline。

因此，ISSUE-1172 的目标不是做一个“大而全”的研究平台，而是建立 **Validation Framework MVP**，把“人工排雷发现 bug”和“人工验证修复生效”的经验，升级为可以持续运行、持续裁决 drift 的正式质量门。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. AMS 必须建立 **Validation Framework MVP**，至少包含 4 层能力：
   - smoke
   - golden_regression
   - sensitivity_sanity
   - canonical_path_consistency
2. Validation Framework MVP 必须服务于当前真实 CLI 主路径，而不是建立平行 mock 框架。
3. `main_runner.py` 必须被纳入真实 smoke suite，且 smoke case 必须通过无 mock 的 JSON 输出主路径运行。
4. 本次必须冻结 **唯一的 baseline case contract**，至少包含 3 组 golden cases：
   - `CASE_WEEKLY_BEST`
   - `CASE_WEEKLY_CONSERVATIVE`
   - `CASE_DAILY_COMPARATOR`
5. 每个 golden case 必须被唯一化，不能只写“最优 weekly 组合”这种模糊描述，而必须冻结：
   - strategy
   - start_date
   - end_date
   - capital
   - top_n
   - rebalance
   - tp_mode
   - tp_pos
   - tp_intra
   - sl
   - data source snapshot identity
6. 每个 golden case 必须冻结并比较以下 summary 字段：
   - `final_equity`
   - `total_return`
   - `max_drawdown`
   - `calmar_ratio`
7. 每个 golden case 必须冻结并比较一组唯一 weekly checkpoints，不允许写成“若干周”这种模糊描述。
8. MVP 中，关键 checkpoint comparison 必须使用精确值断言；如果后续因环境抖动要放宽到 tolerance，容差矩阵必须集中定义，而不是测试里自由发挥。
9. Validation Framework 必须引入 **dataset immutability contract**：
   - golden regression 不得直接依赖会持续更新的日常 research data path；
   - 必须使用冻结快照数据集，或等价的版本锁定机制（hash + read-only artifact）。
10. 本次必须引入 **sensitivity sanity checks**，至少覆盖：
    - `sl`
    - `tp_pos`
    - `tp_intra`
11. sensitivity sanity checks 的目标不是证明某个参数更优，而是证明关键参数对结果仍然“活着”：
    - 关键 summary 不得在参数变化后完全一致；
    - 如果完全一致，必须视为可疑失败信号。
12. Validation Framework 必须建立 **canonical path consistency check**：
    - 默认 CLI 数据路径执行与显式 canonical 数据路径执行，不得出现一边有结果、一边空 summary 的分叉。
13. Validation artifacts 必须放在可版本化路径中，不得把 shell 临时输出作为唯一基线来源。
14. 本次要给 walk-forward 留下清晰扩展位，但不要求在 MVP 中一次做完整自动多窗口研究系统。

### Non-Functional Requirements
1. Validation Framework 必须可在 CI / preflight 中稳定运行，不能依赖人工交互。
2. baseline 数据、baseline 参数、baseline 输出、checkpoint 定义，必须都具备唯一性，不能让 Reviewer/CI 去猜。
3. smoke / golden / sanity / consistency 的失败信息必须可解释，方便 Boss 与 Reviewer 直接判断是路径问题、数据问题、还是执行语义漂移。
4. 不允许为了稳定而回避真实主路径，因为 Validation 的价值就是守住真实行为。

### Boundaries
- **In Scope**：真实 smoke suite、唯一化 golden case contract、冻结 baseline dataset/snapshot、summary/weekly checkpoint comparison、sensitivity sanity checks、canonical path consistency check、walk-forward skeleton/documented extension point。
- **Out of Scope**：完整自动化参数寻优平台、大规模热力图/网格搜索系统、QMT live integration、完整研究报告系统。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 先冻结“唯一可裁决”的 baseline contract，再谈 regression
本次最大的设计原则不是“多做测试”，而是 **先把裁判标准钉死**。如果没有唯一化的 baseline case contract，所谓 golden regression 只会变成一套看起来像测试、实际上无法稳定裁决 drift 的脆弱框架。

因此，本次必须先冻结：
- 唯一 baseline cases
- 唯一输入数据快照
- 唯一 summary keys
- 唯一 checkpoint 周列表
- 唯一比对规则

### 3.2 三个唯一化 Golden Cases（Hard Freeze）
本次 MVP 直接冻结以下 3 组 golden cases，后续实现不得改名、不得替换参数语义：

#### CASE_WEEKLY_BEST
- strategy: `cb_rotation`
- start_date: `2025-01-06`
- end_date: `2026-01-06`
- capital: `4000000`
- top_n: `20`
- rebalance: `weekly`
- tp_mode: `both`
- tp_pos: `0.15`
- tp_intra: `0.12`
- sl: `-0.10`
- baseline summary:
  - `final_equity = 5160304.10`
  - `total_return = 0.290076025`
  - `max_drawdown = -0.03358338309209775`
  - `calmar_ratio = 8.637486705985126892185289367`
- frozen weekly checkpoints:
  - `2025-01-10`
  - `2025-06-27`
  - `2025-09-26`
  - `2025-12-26`
  - `2026-01-09`

#### CASE_WEEKLY_CONSERVATIVE
- strategy: `cb_rotation`
- start_date: `2025-01-06`
- end_date: `2026-01-06`
- capital: `4000000`
- top_n: `20`
- rebalance: `weekly`
- tp_mode: `both`
- tp_pos: `0.15`
- tp_intra: `0.08`
- sl: `-0.05`
- baseline summary:
  - `final_equity = 5050087.49`
  - `total_return = 0.2625218725`
  - `max_drawdown = -0.03355454394686775`
  - `calmar_ratio = 7.823735375920848870044859569`
- frozen weekly checkpoints:
  - `2025-01-10`
  - `2025-06-27`
  - `2025-09-26`
  - `2025-12-26`
  - `2026-01-09`

#### CASE_DAILY_COMPARATOR
- strategy: `cb_rotation`
- start_date: `2025-01-06`
- end_date: `2026-01-06`
- capital: `4000000`
- top_n: `20`
- rebalance: `daily`
- tp_mode: `both`
- tp_pos: `0.15`
- tp_intra: `0.12`
- sl: `-0.10`
- baseline summary:
  - `final_equity = 5098851.19`
  - `total_return = 0.2747127975`
  - `max_drawdown = -0.035826958475947926`
  - `calmar_ratio = 7.667767770027860942187573457`
- frozen weekly checkpoints:
  - `2025-01-10`
  - `2025-06-27`
  - `2025-09-26`
  - `2025-12-26`
  - `2026-01-09`

### 3.3 Dataset Immutability Contract
Auditor 指出的核心风险是对的：不能把 regression baseline 直接绑在一个会继续演进的日常数据文件上。

因此，本 PRD 强制要求：
1. `golden_regression` 不得直接使用当前 CLI 默认数据路径，也不得直接使用 `/root/projects/AMS/data/cb_history_factors.csv` 作为 mutable baseline source。
2. 必须建立一份 **冻结快照数据集**，放在受控测试路径中，例如：
   - `tests/golden/data/cb_history_factors_golden_2025_2026.csv`
3. 这份 golden snapshot 必须伴随以下不可歧义元数据：
   - SHA256
   - row count
   - file size
   - source lineage note（说明来自哪份研究数据、何时冻结）
4. Golden baseline cases 只对这份冻结 snapshot 负责；日常研究数据继续演进，不得自动污染 golden baseline。
5. 若未来需要更新 golden snapshot，必须视为显式 baseline refresh 行为，而不是普通代码改动。

### 3.4 四层 Validation Model
#### Layer 1: Smoke
目标：证明真实 CLI 主路径可运行。
- 使用固定 smoke 参数与固定数据输入；
- 执行真实 `main_runner.py --format json`；
- 要求 summary 非空且关键字段齐全。

#### Layer 2: Golden Regression
目标：对冻结 snapshot + 唯一化 baseline cases 执行可裁决对比。
- 比较 summary 四元组；
- 比较 5 个固定 weekly checkpoints；
- 初版按精确字符串/数值断言实现。

#### Layer 3: Sensitivity Sanity
目标：防参数失效。
- 固定其他参数，只改变 `sl` / `tp_pos` / `tp_intra`；
- summary 关键四元组不得全部完全相同。

#### Layer 4: Canonical Path Consistency
目标：发现默认路径与 canonical path 的行为分叉。
- 同一 smoke case 同时走默认路径与显式 canonical path；
- 两者都必须返回非空 summary；
- 若一边为空，一边非空，立即失败。

### 3.5 Artifact Layout
建议受控路径：
- `tests/golden/data/`：冻结 golden snapshot 数据文件
- `tests/golden/baselines/`：golden case baseline JSON / checkpoint artifacts
- `tests/validation/`：smoke / regression / sanity / consistency suites

硬规则：
- 不允许在项目根目录新建零散 Python 工具文件；
- 必须遵守 AMS 目录纪律；
- baseline artifacts 必须可版本化、可审计。

### 3.6 Walk-Forward 只留 Skeleton
walk-forward 是正确方向，但本次 MVP 不做完整自动多窗口研究平台。
本次只要求：
- 文档中明确其存在；
- 在 artifact / suite 结构上留扩展位；
- 不要求第一版就跑全自动 walk-forward。

### 3.7 建议的低爆炸半径切分
1. **Golden artifact scaffold + frozen dataset contract**
2. **Smoke + three frozen golden cases**
3. **Sensitivity sanity suite**
4. **Canonical path consistency gate + walk-forward skeleton doc hook**

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Unified CLI smoke path is truly executable**
  - **Given** 一个固定 smoke case 使用真实 `main_runner.py` 主路径
  - **When** 以 `--format json` 运行回测
  - **Then** 命令必须成功返回
  - **And** `summary` 不能为空
  - **And** `weekly_performance` 不能为空
  - **And** summary 必须包含 `final_equity`、`total_return`、`max_drawdown`、`calmar_ratio`

- **Scenario 2: CASE_WEEKLY_BEST is reproducible against frozen snapshot**
  - **Given** `CASE_WEEKLY_BEST` 的固定参数、固定 snapshot 数据与固定 checkpoint 列表
  - **When** 运行 golden regression
  - **Then** `final_equity`、`total_return`、`max_drawdown`、`calmar_ratio` 必须与冻结 baseline 精确一致
  - **And** 5 个 frozen weekly checkpoints 必须与 baseline 精确一致

- **Scenario 3: CASE_WEEKLY_CONSERVATIVE is reproducible against frozen snapshot**
  - **Given** `CASE_WEEKLY_CONSERVATIVE` 的固定参数、固定 snapshot 数据与固定 checkpoint 列表
  - **When** 运行 golden regression
  - **Then** summary 四元组必须与冻结 baseline 精确一致
  - **And** 5 个 frozen weekly checkpoints 必须与 baseline 精确一致

- **Scenario 4: CASE_DAILY_COMPARATOR is reproducible against frozen snapshot**
  - **Given** `CASE_DAILY_COMPARATOR` 的固定参数、固定 snapshot 数据与固定 checkpoint 列表
  - **When** 运行 golden regression
  - **Then** summary 四元组必须与冻结 baseline 精确一致
  - **And** 5 个 frozen weekly checkpoints 必须与 baseline 精确一致

- **Scenario 5: Stop-loss sensitivity sanity remains alive**
  - **Given** 相同策略与其他固定参数，仅改变 `sl`
  - **When** 执行 sensitivity sanity case
  - **Then** `final_equity`、`total_return`、`max_drawdown`、`calmar_ratio` 不得全部完全一致

- **Scenario 6: Take-profit position threshold sensitivity remains alive**
  - **Given** 相同策略与其他固定参数，仅改变 `tp_pos`
  - **When** 执行 sensitivity sanity case
  - **Then** `final_equity`、`total_return`、`max_drawdown`、`calmar_ratio` 不得全部完全一致

- **Scenario 7: Take-profit intraday threshold sensitivity remains alive**
  - **Given** 相同策略与其他固定参数，仅改变 `tp_intra`
  - **When** 执行 sensitivity sanity case
  - **Then** `final_equity`、`total_return`、`max_drawdown`、`calmar_ratio` 不得全部完全一致

- **Scenario 8: Default path and canonical path both produce non-empty summary**
  - **Given** 同一 smoke case
  - **When** 一次使用默认 CLI 数据路径执行，另一次显式传 canonical 数据路径执行
  - **Then** 两次都必须返回非空 `summary`
  - **And** 不允许出现一边为空、一边非空的分叉

- **Scenario 9: Golden dataset is frozen and auditable**
  - **Given** Validation Framework 使用的 golden snapshot 数据文件
  - **When** Reviewer 检查 baseline artifacts
  - **Then** 必须能看到对应 snapshot 的 SHA256、file size、row count 与 source lineage note
  - **And** regression suite 不得直接读取 mutable research dataset 作为 golden baseline source

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risks
- 执行语义再次 silent drift，而 CI 仍然通过
- 参数再次失效，但系统不崩，导致 bug 只能靠人工 sweep 偶然发现
- baseline case 描述不唯一，测试看起来很多，实际上没人知道 drift 应该怎么判
- golden regression 直接踩在会继续更新的数据文件上，导致 baseline 自己漂移
- 默认路径与 canonical path 行为不一致，研究环境和验证环境分叉

### Verification Strategy
1. **No-Mock CLI Smoke**
   - 必须通过真实 `main_runner.py` 路径执行，不允许 mock 主运行链路。
2. **Frozen Golden Regression**
   - 必须基于冻结 snapshot 数据集；
   - 必须对 3 组唯一化 golden cases 做 summary + checkpoint 精确对比。
3. **Sensitivity Sanity Verification**
   - 不是证明谁更优，而是证明关键参数仍然活着；
   - 完全不变即视为异常。
4. **Canonical Path Consistency Verification**
   - 默认路径 vs canonical 显式路径必须被正式对照。
5. **Dataset Immutability Verification**
   - golden snapshot 的 hash / size / row count / lineage 必须可审计。

### Quality Goal
本次完成后，AMS 应具备第一版真正可裁决的 Validation Framework MVP，使系统以后每次修改都能回答：
- 主路径还在不在；
- baseline 有没有漂；
- 参数还活不活；
- 默认路径与 canonical path 是否一致；
- drift 到底来自代码还是来自数据输入变化。

## 6. Framework Modifications (框架防篡改声明)
- `main_runner.py`
- `ams/core/cb_rotation_strategy.py`
- `ams/core/sim_broker.py`
- `ams/runners/backtest_runner.py`
- `ams/utils/reporting.py`（如需要）
- `tests/validation/` 下新增或修改的 suites
- `tests/golden/data/` 下新增的冻结 snapshot 数据
- `tests/golden/baselines/` 下新增的 baseline artifacts
- `tests/fixtures/` 下必要的补充 fixture

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 把 ISSUE-1172 定义为 Validation Framework MVP，但 baseline case 仍然是概念性的“best weekly / conservative weekly / daily comparator”，未冻结唯一参数与 checkpoint。
- **Audit Rejection (v1.0)**: Auditor 否决的核心理由是：baseline case contract 不够硬，dataset immutability 没有被锁死，导致 regression framework 会变成无法稳定裁决 drift 的脆弱框架。
- **v2.0 Revision Rationale**: 本版直接冻结三组唯一 golden cases、五个唯一 checkpoint 周列表、固定 summary contract，并引入 dataset immutability contract，要求 golden regression 使用冻结 snapshot 与可审计元数据，而不是继续踩在 mutable research dataset 上。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact canonical research data path
```text
/root/projects/AMS/data/cb_history_factors.csv
```

### Exact mutable default CLI data path currently exposed by main_runner.py
```text
/root/.openclaw/workspace/data/cb_history_factors.csv
```

### Exact golden snapshot target path
```text
tests/golden/data/cb_history_factors_golden_2025_2026.csv
```

### Exact CLI command skeleton for smoke / golden validation
```text
python3 main_runner.py --strategy cb_rotation --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --capital <FLOAT> --top-n <INT> --rebalance <daily|weekly> --tp-mode <both|position|intraday> --tp-pos <FLOAT> --tp-intra <FLOAT> --sl <FLOAT> --format json
```

### Exact required JSON summary keys
```text
summary
weekly_performance
total_return
max_drawdown
calmar_ratio
final_equity
week_ending
total_assets
weekly_profit_pct
cumulative_pct
```

### Exact tp-mode error string that must remain regression-protected
```text
ERROR: --tp-mode '{tp_mode}' requires both --tp-pos and --tp-intra to be set.
```

### Exact validation principles that must be preserved in test descriptions / baseline docs
```text
smoke
golden_regression
sensitivity_sanity
canonical_path_consistency
walk_forward
```

### Exact rule for canonical path consistency gate
```text
Default CLI data path execution and explicit canonical data path execution must both produce a non-empty summary for the same validation case.
```

### Exact frozen golden cases
```json
{
  "CASE_WEEKLY_BEST": {
    "strategy": "cb_rotation",
    "start_date": "2025-01-06",
    "end_date": "2026-01-06",
    "capital": 4000000,
    "top_n": 20,
    "rebalance": "weekly",
    "tp_mode": "both",
    "tp_pos": 0.15,
    "tp_intra": 0.12,
    "sl": -0.10,
    "summary": {
      "total_return": "0.290076025",
      "max_drawdown": "-0.03358338309209775",
      "calmar_ratio": "8.637486705985126892185289367",
      "final_equity": "5160304.1"
    },
    "checkpoints": [
      {
        "week_ending": "2025-01-10",
        "total_assets": "4040845.67",
        "weekly_profit_pct": "0.0102114175",
        "cumulative_pct": "0.0102114175"
      },
      {
        "week_ending": "2025-06-27",
        "total_assets": "4748711.54",
        "weekly_profit_pct": "0.02439646887186567439094501388",
        "cumulative_pct": "0.187177885"
      },
      {
        "week_ending": "2025-09-26",
        "total_assets": "5080587.05",
        "weekly_profit_pct": "0.0004180614502896322623096148242",
        "cumulative_pct": "0.2701467625"
      },
      {
        "week_ending": "2025-12-26",
        "total_assets": "5144148.32",
        "weekly_profit_pct": "-0.0002848794999049870470273500100",
        "cumulative_pct": "0.28603708"
      },
      {
        "week_ending": "2026-01-09",
        "total_assets": "5160304.1",
        "weekly_profit_pct": "0.003642927442067289856927306685",
        "cumulative_pct": "0.290076025"
      }
    ]
  },
  "CASE_WEEKLY_CONSERVATIVE": {
    "strategy": "cb_rotation",
    "start_date": "2025-01-06",
    "end_date": "2026-01-06",
    "capital": 4000000,
    "top_n": 20,
    "rebalance": "weekly",
    "tp_mode": "both",
    "tp_pos": 0.15,
    "tp_intra": 0.08,
    "sl": -0.05,
    "summary": {
      "total_return": "0.2625218725",
      "max_drawdown": "-0.03355454394686775",
      "calmar_ratio": "7.823735375920848870044859569",
      "final_equity": "5050087.49"
    },
    "checkpoints": [
      {
        "week_ending": "2025-01-10",
        "total_assets": "4040845.67",
        "weekly_profit_pct": "0.0102114175",
        "cumulative_pct": "0.0102114175"
      },
      {
        "week_ending": "2025-06-27",
        "total_assets": "4692004.43",
        "weekly_profit_pct": "0.02528044857279632247546484570",
        "cumulative_pct": "0.1730011075"
      },
      {
        "week_ending": "2025-09-26",
        "total_assets": "5003488.64",
        "weekly_profit_pct": "0.0003941243895537606664978885548",
        "cumulative_pct": "0.25087216"
      },
      {
        "week_ending": "2025-12-26",
        "total_assets": "5029993.34",
        "weekly_profit_pct": "-0.0002881499316950445917291145384",
        "cumulative_pct": "0.257498335"
      },
      {
        "week_ending": "2026-01-09",
        "total_assets": "5050087.49",
        "weekly_profit_pct": "0.004793962041813957375790810631",
        "cumulative_pct": "0.2625218725"
      }
    ]
  },
  "CASE_DAILY_COMPARATOR": {
    "strategy": "cb_rotation",
    "start_date": "2025-01-06",
    "end_date": "2026-01-06",
    "capital": 4000000,
    "top_n": 20,
    "rebalance": "daily",
    "tp_mode": "both",
    "tp_pos": 0.15,
    "tp_intra": 0.12,
    "sl": -0.10,
    "summary": {
      "total_return": "0.2747127975",
      "max_drawdown": "-0.035826958475947926",
      "calmar_ratio": "7.667767770027860942187573457",
      "final_equity": "5098851.19"
    },
    "checkpoints": [
      {
        "week_ending": "2025-01-10",
        "total_assets": "4046818.71",
        "weekly_profit_pct": "0.0117046775",
        "cumulative_pct": "0.0117046775"
      },
      {
        "week_ending": "2025-06-27",
        "total_assets": "4645631.69",
        "weekly_profit_pct": "0.02405289326728325401882193998",
        "cumulative_pct": "0.1614079225"
      },
      {
        "week_ending": "2025-09-26",
        "total_assets": "5033104.27",
        "weekly_profit_pct": "0.0009253266489319949286731783031",
        "cumulative_pct": "0.2582760675"
      },
      {
        "week_ending": "2025-12-26",
        "total_assets": "5074015.73",
        "weekly_profit_pct": "0.002024818490056641735922794152",
        "cumulative_pct": "0.2685039325"
      },
      {
        "week_ending": "2026-01-09",
        "total_assets": "5098851.19",
        "weekly_profit_pct": "0.004861981046311276164229250476",
        "cumulative_pct": "0.2747127975"
      }
    ]
  }
}
```

### Exact required metadata keys for frozen golden snapshot
```text
sha256
file_size_bytes
row_count
source_lineage
```