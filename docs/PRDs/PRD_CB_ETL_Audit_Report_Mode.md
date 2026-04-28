---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: CB ETL Audit Report Mode

## 1. Context & Problem (业务背景与核心痛点)

AMS 当前的可转债 ETL 主入口 `etl/jqdata_sync_cb.py::sync_cb_data()` 以**单体 fail-fast promotion path**的方式组织：
- source 拉取、supportability 分类、premium join、`is_st` join、redemption 语义推导、validator、promotion 都耦合在同一个强顺序路径里；
- 一旦某一层出现 fatal，整条链路立即终止；
- 这种设计保护了 canonical dataset，但让架构诊断效率极低。

最近的 live debugging 已经证明这个结构性问题：
1. 第一层表面 blocker 是 `125302` / supportability / `underlying_ticker` 问题；
2. 修通 supportability 层后，真实 full-window rerun 才进一步暴露出新的 blocker：`CONBOND_DAILY_CONVERT` premium source query 被截断，导致 `premium_rate` 大面积缺失；
3. 当前生产路径一次只能输出第一个 fatal，因此 Manager/Boss 无法在一次运行中看到整个 ETL 各阶段的问题分布，只能串行剥洋葱。

这说明 AMS 缺的不是“再包一层 wrapper”，而是**共享 staged pipeline 抽象**：
- 生产 promotion 与 audit diagnosis 必须共享同一套阶段骨架；
- promotion runner 继续 fail-fast；
- audit runner 在不 promotion 的前提下收集所有按阶段可观测的问题；
- 两者不能各写一套 ETL，也不能把现有主入口污染成一个 mode-flag 泥球。

核心问题定义：
> AMS 缺少一个 production / audit 共享的 staged CB ETL pipeline 抽象，导致当前系统只能串行暴露第一个 fatal 问题，无法在不污染 promotion contract 的前提下输出完整的诊断报告。

## 2. Requirements & User Stories (需求定义)

### Functional Requirements
1. AMS 必须把当前 CB ETL 拆解为一套**共享 staged pipeline abstraction**，供以下两个 runner 复用：
   - `promote runner`
   - `audit runner`
2. `promote runner` 必须保持现有生产语义：
   - fail-fast
   - canonical dataset promotion
   - 不改变现有 `sync_cb_data()` 的默认外部 contract
3. `audit runner` 必须：
   - 不覆盖 `data/cb_history_factors.csv`
   - 不覆盖 `data/cb_history_factors.metrics.json`
   - 不进行 canonical promotion
   - 不在第一处 join / validator 问题就退出，除非 Stage A source acquisition 本身不可用
4. `audit runner` 必须在一次运行中输出按阶段组织的 deterministic JSON 报告。
5. 报告至少必须覆盖：
   - Stage A: source acquisition coverage / failure result
   - Stage B: supportability / exclusion / regression bucket summary
   - Stage C: premium join coverage / failure result
   - Stage D: `is_st` join coverage / failure result
   - Stage E: redemption / delist coverage / failure result
   - Stage F: validator structured result
   - final root blockers
   - final secondary findings
6. audit runner 必须支持任意给定窗口执行，例如：
   - `start_date="2025-01-18"`
   - `end_date="2026-01-25"`
7. 报告最终状态必须严格属于以下三值之一：
   - `PASS`
   - `FAIL_ROOT_BLOCKER`
   - `FAIL_SECONDARY_ONLY`
8. 报告必须明确声明：该运行只用于诊断，不能代表 canonical dataset 已可晋升。

### Non-Functional Requirements
1. v1 不得复制 ETL 核心阶段逻辑。生产与审计必须共享同一套 stage 行为 contract，而不是“逻辑相似但各自维护”。
2. v1 不得修改 validator 内部规则；如需结构化 validator 结果，只能在 audit runner 侧捕获并映射。
3. v1 不得通过 mode flag 直接污染现有单体主入口，让 production path 语义变得模糊不清。
4. 报告中的 root blocker 与 secondary finding 判定必须是**数值化/算法化/黑盒可测试**的，不能依赖模糊语义词。
5. v1 必须先冻结 side-effect boundary、source failure contract、NOT_RUN 规则、rollback/isolation 规则，再允许落地到核心 ETL 主链。
6. v1 只要求 JSON 报告；markdown summary 不在范围内。

### User Stories
- 作为 Boss，我希望一次运行就能看到 AMS 当前 CB ETL 在各阶段的主要裂缝，而不是修一层才看到下一层。
- 作为 Manager，我希望 production promotion 继续严格 fail-fast，但同时拥有一个只做诊断的 audit runner，用来做架构 triage。
- 作为 Reviewer/Auditor，我希望 root blocker 判定、source failure 收敛、NOT_RUN 传播和 side-effect boundary 都是合同化的，而不是工程师自由补洞。

### Boundaries
- **In Scope**:
  - 共享 staged pipeline abstraction
  - 独立 audit runner
  - deterministic JSON report
  - 固定 root/secondary 归类规则
  - side-effect boundary contract
  - source failure contract
  - validator structured mapping contract
- **Out of Scope**:
  - 修复具体 source bug（例如 premium query pagination）
  - 修改 vendor 权限问题
  - 修改 strategy/backtest 业务逻辑
  - 修改 validator 内部阈值与规则
  - markdown 运营摘要

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Target Architecture
必须把当前单体 ETL 抽象成共享阶段骨架：

```text
shared staged pipeline
  ├─ Stage A: source acquisition
  ├─ Stage B: supportability classification
  ├─ Stage C: premium join stage
  ├─ Stage D: is_st join stage
  ├─ Stage E: redemption/delist stage
  ├─ Stage F: validator stage
  ├─ promote runner (fail-fast + promotion)
  └─ audit runner (collect + report, no promotion)
```

### 3.2 Side-Effect Boundary Contract
必须把**纯 stage 逻辑**与**promotion side effects**严格切开。

#### Pure stage logic (shared)
以下逻辑属于 shared staged pipeline，可被 promote runner 与 audit runner 共同复用：
- source acquisition
- supportability classification
- premium join attempt
- `is_st` join attempt
- redemption / delist derivation attempt
- candidate summary metrics computation
- validator invocation and structured capture

#### Promotion side effects (promote runner only)
以下行为只允许出现在 promote runner：
- 写入 `data/cb_history_factors.csv.tmp`
- 原子替换 `data/cb_history_factors.csv`
- 写入 `data/cb_history_factors.metrics.json.tmp`
- 原子替换 `data/cb_history_factors.metrics.json`
- `.bak` / rollback 文件替换与恢复
- canonical promotion success/failure side effects

#### Audit side effects (audit runner only)
以下行为只允许出现在 audit runner：
- 写入 `reports/cb_etl_audit_<start>_<end>.json`
- 不得写 canonical CSV
- 不得写 canonical metrics
- 不得创建/覆盖 `.bak` promotion rollback artifacts

### 3.3 Stage Output Contracts

#### Stage A — Source acquisition
输出必须包含：
- `status`: `PASS|FAIL|NOT_RUN`
- `failure_type`: `NONE|SOURCE_AUTH_FAILURE|PRICE_SOURCE_UNREADABLE`
- `basic_info_row_count`
- `all_bond_security_count`
- `price_row_count`
- `price_unique_bond_count`
- `premium_source_row_count`
- `premium_source_unique_bond_count`
- `is_st_source_row_count`
- `is_st_source_unique_underlying_count`
- `redemption_source_row_count`
- `redemption_source_unique_bond_count`
- `message`

#### Stage B — Supportability classification
输出必须包含：
- `status`: `PASS|FAIL|NOT_RUN`
- `failure_type`: `NONE|SUPPORTABILITY_REGRESSION`
- `supportable_row_count`
- `supportable_unique_bond_count`
- `outside_basic_info_row_count`
- `outside_basic_info_unique_bond_count`
- `missing_company_code_legacy_row_count`
- `missing_company_code_legacy_unique_bond_count`
- `unexpected_contract_regression_row_count`
- `unexpected_contract_regression_unique_bond_count`
- `missing_underlying_row_count`
- `missing_underlying_unique_bond_count`
- `message`

#### Stage C — Premium join stage
输出必须包含：
- `status`: `PASS|FAIL|NOT_RUN`
- `failure_type`: `NONE|PREMIUM_SOURCE_TRUNCATION|PREMIUM_RATE_MISSING_BROAD_COVERAGE`
- `premium_joined_row_count`
- `premium_joined_unique_bond_count`
- `missing_premium_row_count`
- `missing_premium_unique_bond_count`
- `missing_premium_ratio`
- `message`

#### Stage D — `is_st` join stage
输出必须包含：
- `status`: `PASS|FAIL|NOT_RUN`
- `failure_type`: `NONE|IS_ST_SOURCE_GAP`
- `is_st_joined_row_count`
- `is_st_joined_unique_bond_count`
- `missing_is_st_row_count`
- `missing_is_st_unique_bond_count`
- `missing_is_st_ratio`
- `message`

#### Stage E — Redemption / delist stage
输出必须包含：
- `status`: `PASS|FAIL|NOT_RUN`
- `failure_type`: `NONE|REDEMPTION_SOURCE_GAP`
- `redemption_joined_row_count`
- `redemption_joined_unique_bond_count`
- `missing_redemption_row_count`
- `missing_redemption_unique_bond_count`
- `missing_redemption_ratio`
- `message`

#### Stage F — Validator stage
输出必须包含：
- `status`: `PASS|FAIL|NOT_RUN`
- `failure_type`: `NONE|VALIDATOR_SCHEMA_FAILURE|VALIDATOR_SEMANTIC_FAILURE|VALIDATOR_DRIFT_FAILURE`
- `schema_validator_status`
- `semantic_validator_status`
- `drift_validator_status`
- `schema_validator_message`
- `semantic_validator_message`
- `drift_validator_message`
- `message`

### 3.4 Source Failure Contract and NOT_RUN Propagation
以下规则必须写死：

1. 若 Stage A `status == FAIL`：
   - Stage B~F 全部必须标记 `status = NOT_RUN`
   - `failure_type = NONE`
   - `message = "Skipped because Stage A failed."`

2. 若 Stage B `failure_type == SUPPORTABILITY_REGRESSION`：
   - Stage C~F 允许继续执行 audit collection
   - 但 `root_blockers` 中必须加入 `SUPPORTABILITY_REGRESSION`

3. 若 Stage C `failure_type == PREMIUM_SOURCE_TRUNCATION` 或 `PREMIUM_RATE_MISSING_BROAD_COVERAGE`：
   - Stage D~F 仍允许继续执行 audit collection
   - downstream missing premium symptoms 只进入 `secondary_findings`

4. 若 Stage D `failure_type == IS_ST_SOURCE_GAP`：
   - Stage E~F 仍允许继续执行 audit collection
   - downstream missing `is_st` symptoms 只进入 `secondary_findings`

5. 若 Stage E `failure_type == REDEMPTION_SOURCE_GAP`：
   - Stage F 仍允许继续执行 audit collection
   - downstream redemption symptoms 只进入 `secondary_findings`

6. exclusion-only window：
   - Stage B `status = PASS`
   - Stage C~E `status = NOT_RUN`
   - `secondary_findings` 必须加入 `EXCLUSION_ONLY_WINDOW`
   - 不得自动判为 root blocker

### 3.5 Exact Root Blocker Formulas
以下条件必须**严格**判为 root blocker：

1. **`SOURCE_AUTH_FAILURE`**
   - 条件：Stage A `failure_type == SOURCE_AUTH_FAILURE`

2. **`PRICE_SOURCE_UNREADABLE`**
   - 条件：Stage A `failure_type == PRICE_SOURCE_UNREADABLE`

3. **`SUPPORTABILITY_REGRESSION`**
   - 条件：Stage B `unexpected_contract_regression_row_count > 0`

4. **`PREMIUM_SOURCE_TRUNCATION`**
   - 条件同时满足：
     - `supportable_row_count >= 50000`
     - `premium_source_row_count == 5000`
     - `missing_premium_ratio >= 0.80`

5. **`PREMIUM_RATE_MISSING_BROAD_COVERAGE`**
   - 条件同时满足：
     - `supportable_row_count > 0`
     - `missing_premium_ratio >= 0.20`
     - 且未命中 `PREMIUM_SOURCE_TRUNCATION`

6. **`IS_ST_SOURCE_GAP`**
   - 条件同时满足：
     - `supportable_row_count > 0`
     - `missing_is_st_ratio >= 0.20`

7. **`REDEMPTION_SOURCE_GAP`**
   - 条件同时满足：
     - `supportable_row_count > 0`
     - `missing_redemption_ratio >= 0.20`

8. **`VALIDATOR_SCHEMA_FAILURE`**
   - 条件：Stage F `schema_validator_status == "FAIL"`

9. **`VALIDATOR_SEMANTIC_FAILURE`**
   - 条件：Stage F `semantic_validator_status == "FAIL"`

10. **`VALIDATOR_DRIFT_FAILURE`**
   - 条件：Stage F `drift_validator_status == "FAIL"`

### 3.6 Exact Secondary Finding Rules
以下情况必须**严格**归类为 secondary findings，而不是 root blocker：

1. **`MISSING_UNDERLYING_TICKER_ROWS`**
   - 条件：`missing_underlying_row_count > 0`

2. **`MISSING_PREMIUM_RATE_ROWS`**
   - 条件：`missing_premium_row_count > 0`

3. **`MISSING_IS_ST_ROWS`**
   - 条件：`missing_is_st_row_count > 0`

4. **`MISSING_REDEMPTION_ROWS`**
   - 条件：`missing_redemption_row_count > 0`

5. **`EXCLUSION_ONLY_WINDOW`**
   - 条件：`supportable_row_count == 0` 且所有 surviving rows 都属于 allowed exclusion buckets

6. **`SEMANTIC_THRESHOLD_BREACH`**
   - 条件：Stage F `status == PASS` 但存在仅供诊断输出的语义阈值异常

### 3.7 Validator Mapping Contract
v1 不允许复制 validator 规则。

唯一允许的映射方式：
- 调用现有 validator
- 捕获其返回值 / 异常 / message
- 映射到结构化字段：
  - `schema_validator_status`
  - `semantic_validator_status`
  - `drift_validator_status`
  - 对应 message

若某一路 validator 在当前实现中根本不存在独立执行入口，则：
- 该路必须输出 `NOT_RUN`
- message 必须写明：`"No dedicated validator path exists in v1 runtime."`

### 3.8 Final Status Rule
最终状态必须按以下固定规则计算：

1. 若 `root_blockers.length > 0` → `FAIL_ROOT_BLOCKER`
2. 否则若 `secondary_findings.length > 0` → `FAIL_SECONDARY_ONLY`
3. 否则 → `PASS`

### 3.9 Report Contract
必须输出 deterministic JSON，且顶层字段必须固定为：
- `execution_mode`
- `start_date`
- `end_date`
- `final_status`
- `non_promotion_disclaimer`
- `source_coverage`
- `supportability_summary`
- `premium_join_summary`
- `is_st_join_summary`
- `redemption_summary`
- `validator_summary`
- `root_blockers`
- `secondary_findings`

### 3.10 Output Path Strategy and Rollback/Isolation Contract
1. audit runner 报告默认写入：
   - `/root/projects/AMS/reports/cb_etl_audit_<start>_<end>.json`
2. audit runner 不得创建/覆盖以下文件：
   - `data/cb_history_factors.csv`
   - `data/cb_history_factors.csv.tmp`
   - `data/cb_history_factors.csv.bak`
   - `data/cb_history_factors.metrics.json`
   - `data/cb_history_factors.metrics.json.tmp`
   - `data/cb_history_factors.metrics.json.bak`
3. 若 audit 报告写入失败：
   - canonical artifacts 必须保持完全不变
   - 本次运行不得执行任何 promotion rollback 逻辑，因为本就没有 promotion

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Audit runner produces a deterministic JSON report with the required nested contract**
  - **Given** AMS CB ETL 以 audit runner 执行
  - **When** 运行完成
  - **Then** 输出必须是一个 JSON 文件
  - **And** 该 JSON 必须包含本 PRD 规定的全部顶层字段、stage summary 字段、finding item 字段和枚举值

- **Scenario 2: Audit runner does not promote canonical artifacts**
  - **Given** AMS CB ETL 以 audit runner 执行
  - **When** 运行完成，无论发现多少诊断问题
  - **Then** `data/cb_history_factors.csv` 不得被覆盖
  - **And** `data/cb_history_factors.metrics.json` 不得被覆盖
  - **And** 不得生成任何 promotion tmp/bak 文件
  - **And** 报告必须明确声明本次运行未进行 canonical promotion

- **Scenario 3: Source failures converge with fixed NOT_RUN propagation**
  - **Given** 某个 source stage 失败
  - **When** audit runner 生成报告
  - **Then** 报告必须按本 PRD 的固定 NOT_RUN 传播规则标记后续 stage
  - **And** 不得由实现者自由决定跳过或继续的语义

- **Scenario 4: Root blockers are computed by exact formulas**
  - **Given** 某次运行命中 premium broad truncation 或 supportability regression
  - **When** 报告生成
  - **Then** 必须按本 PRD 数值/算法规则进入 `root_blockers`
  - **And** 不得依赖“明显”“广泛”“严重”等自由语义词

- **Scenario 5: Secondary findings are symptom-level only**
  - **Given** 某次运行已命中 premium source root blocker
  - **When** 报告生成
  - **Then** downstream `missing_premium_rate_rows` 只能作为 secondary finding 输出
  - **And** 不得与 root blocker 等权平铺

- **Scenario 6: Validator mapping remains non-duplicative**
  - **Given** audit runner 需要输出 schema/semantic/drift 三路结果
  - **When** 报告生成
  - **Then** 这些字段必须来自对现有 validator 的调用与结构化映射
  - **And** 不得要求复制 validator 规则到 audit runner 中

- **Scenario 7: Production promote behavior remains unchanged**
  - **Given** 现有 `sync_cb_data()` 默认 production promotion 路径
  - **When** 不显式调用 audit runner
  - **Then** 仍然保持当前 fail-fast + promotion 语义
  - **And** 现有外部调用行为不得被悄悄改变

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core Quality Risk
最大的风险不是报告生成不了，而是：
1. 生产与审计逻辑分叉，导致 audit report 与真实 ETL 不一致；
2. 审计模式污染生产路径；
3. root blocker 判定不够硬，导致不同实现者输出不同诊断结论；
4. source failure / NOT_RUN / side-effect 边界不硬，导致 exception laundering 和 hidden side effects。

### Testing Strategy
1. **Deterministic stage tests**
   - mock source 层并构造 supportability / premium / is_st / validator 多层问题
   - 验证报告在一次运行中输出多类 findings
2. **Source failure propagation tests**
   - 构造 Stage A 失败
   - 验证 Stage B~F 全部变成固定 `NOT_RUN`
3. **Exact formula tests**
   - 构造 premium truncation 场景：
     - `supportable_row_count >= 50000`
     - `premium_source_row_count == 5000`
     - `missing_premium_ratio >= 0.80`
   - 验证命中 `PREMIUM_SOURCE_TRUNCATION`
4. **Schema contract tests**
   - 验证顶层 JSON 字段、stage summary 字段、finding item 字段与枚举值完全符合 PRD
5. **Non-promotion safety tests**
   - 验证 audit runner 不写 canonical CSV / metrics / tmp / bak
   - 验证 production runner 保持原行为
6. **Live smoke / probe validation**
   - 对 JQData 当前允许窗口跑一次 audit runner
   - 确认能产出真实 JSON 报告

### Mocking Guidance
必须 mock 的主要依赖：
- `jqdatasdk.auth`
- `bond.CONBOND_BASIC_INFO`
- `get_all_securities`
- `get_price`
- premium source query
- `get_extras("is_st")`

测试中要显式覆盖：
- supportability regression
- premium source truncation / broad coverage gap
- is_st source gap
- validator semantic failure
- exclusion-only window
- source failure → NOT_RUN propagation

### Quality Goal
让 AMS 获得一个稳定的 staged diagnostic v1：
- production promotion 继续安全
- diagnosis 一次看清按阶段可观测的问题
- Manager 能更快定位根因、减少串行试错成本

## 6. Framework Modifications (框架防篡改声明)
- `etl/jqdata_sync_cb.py`
- 相关测试文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: AMS 只有 production fail-fast ETL；每次只暴露第一处 fatal。
- **v1.1**: live 调试显示 `125302` 修通后，新的真实 blocker 是 premium source query truncation；说明现有执行方式不适合做全链路 diagnosis。
- **v2.0 Revision Rationale**: 根据 auditor 反馈，补齐 side-effect boundary、source failure contract、validator mapping contract、NOT_RUN 传播和 audit/non-promotion 隔离策略。

---

## 7. Hardcoded Content (硬编码内容)

### stage_status values
```text
PASS
FAIL
NOT_RUN
```

### final_status values
```text
PASS
FAIL_ROOT_BLOCKER
FAIL_SECONDARY_ONLY
```

### validator_status values
```text
PASS
FAIL
NOT_RUN
```

### non_promotion_disclaimer
```text
[AUDIT-ONLY] This run is diagnostic only. No canonical dataset promotion was attempted.
```

### required_top_level_json_fields
```json
{
  "execution_mode": "audit",
  "start_date": "<YYYY-MM-DD>",
  "end_date": "<YYYY-MM-DD>",
  "final_status": "PASS|FAIL_ROOT_BLOCKER|FAIL_SECONDARY_ONLY",
  "non_promotion_disclaimer": "[AUDIT-ONLY] This run is diagnostic only. No canonical dataset promotion was attempted.",
  "source_coverage": {},
  "supportability_summary": {},
  "premium_join_summary": {},
  "is_st_join_summary": {},
  "redemption_summary": {},
  "validator_summary": {},
  "root_blockers": [],
  "secondary_findings": []
}
```

### required_source_coverage_schema
```json
{
  "status": "PASS|FAIL|NOT_RUN",
  "failure_type": "NONE|SOURCE_AUTH_FAILURE|PRICE_SOURCE_UNREADABLE",
  "basic_info_row_count": 0,
  "all_bond_security_count": 0,
  "price_row_count": 0,
  "price_unique_bond_count": 0,
  "premium_source_row_count": 0,
  "premium_source_unique_bond_count": 0,
  "is_st_source_row_count": 0,
  "is_st_source_unique_underlying_count": 0,
  "redemption_source_row_count": 0,
  "redemption_source_unique_bond_count": 0,
  "message": "string"
}
```

### required_supportability_summary_schema
```json
{
  "status": "PASS|FAIL|NOT_RUN",
  "failure_type": "NONE|SUPPORTABILITY_REGRESSION",
  "supportable_row_count": 0,
  "supportable_unique_bond_count": 0,
  "outside_basic_info_row_count": 0,
  "outside_basic_info_unique_bond_count": 0,
  "missing_company_code_legacy_row_count": 0,
  "missing_company_code_legacy_unique_bond_count": 0,
  "unexpected_contract_regression_row_count": 0,
  "unexpected_contract_regression_unique_bond_count": 0,
  "missing_underlying_row_count": 0,
  "missing_underlying_unique_bond_count": 0,
  "message": "string"
}
```

### required_premium_join_summary_schema
```json
{
  "status": "PASS|FAIL|NOT_RUN",
  "failure_type": "NONE|PREMIUM_SOURCE_TRUNCATION|PREMIUM_RATE_MISSING_BROAD_COVERAGE",
  "premium_joined_row_count": 0,
  "premium_joined_unique_bond_count": 0,
  "missing_premium_row_count": 0,
  "missing_premium_unique_bond_count": 0,
  "missing_premium_ratio": 0.0,
  "message": "string"
}
```

### required_is_st_join_summary_schema
```json
{
  "status": "PASS|FAIL|NOT_RUN",
  "failure_type": "NONE|IS_ST_SOURCE_GAP",
  "is_st_joined_row_count": 0,
  "is_st_joined_unique_bond_count": 0,
  "missing_is_st_row_count": 0,
  "missing_is_st_unique_bond_count": 0,
  "missing_is_st_ratio": 0.0,
  "message": "string"
}
```

### required_redemption_summary_schema
```json
{
  "status": "PASS|FAIL|NOT_RUN",
  "failure_type": "NONE|REDEMPTION_SOURCE_GAP",
  "redemption_joined_row_count": 0,
  "redemption_joined_unique_bond_count": 0,
  "missing_redemption_row_count": 0,
  "missing_redemption_unique_bond_count": 0,
  "missing_redemption_ratio": 0.0,
  "message": "string"
}
```

### required_validator_summary_schema
```json
{
  "status": "PASS|FAIL|NOT_RUN",
  "failure_type": "NONE|VALIDATOR_SCHEMA_FAILURE|VALIDATOR_SEMANTIC_FAILURE|VALIDATOR_DRIFT_FAILURE",
  "schema_validator_status": "PASS|FAIL|NOT_RUN",
  "semantic_validator_status": "PASS|FAIL|NOT_RUN",
  "drift_validator_status": "PASS|FAIL|NOT_RUN",
  "schema_validator_message": "string",
  "semantic_validator_message": "string",
  "drift_validator_message": "string",
  "message": "string"
}
```

### required_root_blocker_item_schema
```json
{
  "type": "SOURCE_AUTH_FAILURE|PRICE_SOURCE_UNREADABLE|SUPPORTABILITY_REGRESSION|PREMIUM_SOURCE_TRUNCATION|PREMIUM_RATE_MISSING_BROAD_COVERAGE|IS_ST_SOURCE_GAP|REDEMPTION_SOURCE_GAP|VALIDATOR_SCHEMA_FAILURE|VALIDATOR_SEMANTIC_FAILURE|VALIDATOR_DRIFT_FAILURE",
  "stage": "A|B|C|D|E|F",
  "trigger": "string",
  "evidence": {}
}
```

### required_secondary_finding_item_schema
```json
{
  "type": "MISSING_UNDERLYING_TICKER_ROWS|MISSING_PREMIUM_RATE_ROWS|MISSING_IS_ST_ROWS|MISSING_REDEMPTION_ROWS|EXCLUSION_ONLY_WINDOW|SEMANTIC_THRESHOLD_BREACH",
  "stage": "B|C|D|E|F",
  "trigger": "string",
  "evidence": {}
}
```

### stage_a_failure_not_run_rule
```json
{
  "if_stage_a_status": "FAIL",
  "then_stage_b_to_f_status": "NOT_RUN",
  "then_stage_b_to_f_failure_type": "NONE",
  "then_stage_b_to_f_message": "Skipped because Stage A failed."
}
```

### validator_no_dedicated_path_message
```text
No dedicated validator path exists in v1 runtime.
```

### premium_source_truncation_formula
```json
{
  "supportable_row_count_min": 50000,
  "premium_source_row_count_equals": 5000,
  "missing_premium_ratio_min": 0.80,
  "result": "PREMIUM_SOURCE_TRUNCATION"
}
```

### premium_rate_missing_broad_coverage_formula
```json
{
  "supportable_row_count_gt": 0,
  "missing_premium_ratio_min": 0.20,
  "exclude_if_already": "PREMIUM_SOURCE_TRUNCATION",
  "result": "PREMIUM_RATE_MISSING_BROAD_COVERAGE"
}
```

### is_st_source_gap_formula
```json
{
  "supportable_row_count_gt": 0,
  "missing_is_st_ratio_min": 0.20,
  "result": "IS_ST_SOURCE_GAP"
}
```

### redemption_source_gap_formula
```json
{
  "supportable_row_count_gt": 0,
  "missing_redemption_ratio_min": 0.20,
  "result": "REDEMPTION_SOURCE_GAP"
}
```
