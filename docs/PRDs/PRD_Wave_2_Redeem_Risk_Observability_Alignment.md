---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Wave 2 Redeem Risk Observability Alignment

## 1. Context & Problem (业务背景与核心痛点)
Wave 1（#14）已经完成 redemption semantic split：
- `redeem_risk` = 交易风险态（trading-risk window）
- `is_redeemed` = 终态 / 退市态（terminal/delist state）

并且策略过滤已经从“仅依赖 `is_redeemed`”切换为：
```python
exclude_if = is_st or redeem_risk or is_redeemed
```

但当前 AMS 仍有一个明显收尾缺口：**代码语义已经拆开，observability / validator / metrics / audit 语义还没有完全拆开。**

当前主要问题不是字段不存在，也不是策略没切过去，而是：
1. metrics 虽然已经暴露 `redeem_risk_true_count` 与 `is_redeemed_true_count`，但还没有形成完整的 Wave 2 观测 contract；
2. audit / report 仍主要围绕 `missing_redemption_row_count` 等 terminal-source 语义组织，容易让人误把 `is_redeemed` 相关计数读成 redemption risk 覆盖质量；
3. Wave 1 允许 `redeem_risk` 在上游先采用 controlled placeholder / fixture / transitional default，这在工程上是合理的，但当前 artifacts 还没有足够明确地把“已知安全”和“当前未知/默认/过渡态”区分出来；
4. validator 当前更偏 schema / core contract guard，尚未把“不可误读的 redemption observability”变成受保护 contract。

如果 Wave 2 不补齐，AMS 会继续暴露在一种更隐蔽但同样危险的状态：
- 系统内部语义看起来正确；
- 但 metrics / audit 仍可能制造假安全感；
- reviewer / auditor 会继续把 terminal-state 输出误读成 announcement-risk coverage；
- 后续 Wave 3 即使接入 event ledger，也缺少统一的验收观测面。

因此，本问题应被定义为 **Phase 1.5 收尾阶段的 observability / validation semantic correction**：
- 不重做 Wave 1 contract split；
- 不提前做 Wave 3 event ledger；
- 只把 Wave 1 已拆开的 redemption semantics，在 metrics / audit / validator / docs 层补成一个可审计、可解释、不可误读的执行闭环。

本 PRD 只覆盖 Wave 2：**validator、metrics、audit surfaces 与 redeem_risk semantics 对齐**。

## 2. Requirements & User Stories (需求定义)
### 2.1 Functional Requirements
1. AMS 必须在 ETL metrics artifact 中，把 `redeem_risk` 相关观测指标与 `is_redeemed` 终态指标明确拆开，不得只靠 `is_redeemed_true_count` 代表 redemption semantics 完整性。
2. AMS 必须在 audit report / structured summary 中明确区分：
   - `redeem_risk` = trading-risk semantics
   - `is_redeemed` = terminal/delist semantics
3. AMS 必须显式暴露 split-state observability，至少能反映：
   - `redeem_risk=True`
   - `is_redeemed=False`
   的样本数量或可审计证据。
4. AMS 必须把“missing / incomplete redemption evidence”保留为可见信号，而不是让其静默折叠成“`redeem_risk=False` 因而安全”的含义。
5. AMS 的 validator / audit message contract 必须避免暗示：terminal-state 计数可以证明 announcement-risk coverage 已正确完成。
6. 现有 Wave 1 contract（双字段存在、策略消费路径、history datafeed 兼容路径）必须保持不变；本波不得倒退为重新定义 `is_redeemed`。
7. metrics artifact、audit report、golden / witness metadata 如需新增字段，必须保持 deterministic、machine-readable、可测试断言。

### 2.2 Non-Functional Requirements
1. 本波改动必须局限在 observability / validator / audit / docs 语义对齐层，不得扩散成 event sourcing 平台重写。
2. 本波必须保持 staged ETL / audit 架构，不得为了补观测语义而分裂 promote runner 与 audit runner 的共享主链路。
3. 本波新增字段/文案必须精确定义，避免 coder 自行脑补“更好看的”解释文案。
4. 本波必须为 Wave 3 保留清晰接口：
   - Wave 2 负责让“risk-state / terminal-state / missing-evidence”都可观测；
   - Wave 3 再接真实 redemption event ledger 与 live/backtest shared-state。
5. 文档必须同步更新，使 ROADMAP / ARCHITECTURE 与当前 redemption semantics 一致。

### 2.3 User Stories
- 作为 Auditor，我希望 audit report 能明确告诉我：哪些输出代表 terminal-state，哪些输出代表 trading-risk，哪些地方仍是过渡态或证据缺口。
- 作为量化研究者，我希望 metrics 不会因为 `is_redeemed` 计数存在就误导我以为 announcement-risk coverage 已经完整。
- 作为架构维护者，我希望在不提前实现 Wave 3 event ledger 的前提下，先把 Wave 2 的 observability contract 固定下来，避免后续验证口径继续漂移。
- 作为 Reviewer，我希望 regression tests 能证明“未知/缺证据”在 artifacts 中仍然可见，而不是被默默吞掉。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Core Design Decision
本波采用 **observability semantic split completion**，而不是继续扩大业务逻辑改写范围。

换句话说：
- Wave 1 解决“系统能否表达并消费双字段语义”；
- Wave 2 解决“系统能否把双字段语义正确解释并暴露出来”。

因此本波的核心目标不是新增更多业务状态，而是把以下三类状态区分清楚：
1. `redeem_risk` = trading-risk window
2. `is_redeemed` = terminal/delist state
3. missing / transitional redemption evidence = 当前不能被误读为“已知安全”

### 3.2 Executable Checklist (可执行清单)
下列清单是本 PRD 的执行主轴。Planner / Coder / Reviewer / UAT 必须围绕该清单推进，不得自行改写目标问题。

#### A. Metrics Contract Alignment
1. 审查并补齐 `etl/cb_etl_runner.py` 输出的 metrics artifact，确保至少包含以下精确字段：
   - `redeem_risk_true_count`
   - `is_redeemed_true_count`
   - `redeem_split_state_row_count`
   - `redeem_terminal_only_row_count`
   - `missing_redemption_row_count`
   - `missing_redemption_ratio`
2. 如果当前 metrics 中仅有 terminal-source 缺口指标，必须补充 `redeem_split_state_row_count` 与 `redeem_terminal_only_row_count`，不得再以模糊或替代字段表达相同语义。
3. 若当前 Wave 1 transitional default 仍可能让 `redeem_risk=False` 同时代表“已知无风险”和“当前未覆盖”，则必须新增以下精确字段：
   - `redeem_risk_observability_mode`
   - `redeem_risk_unknown_interpretation`
   以防止 silent false safety。

#### B. Audit Report Semantic Alignment
4. 审查 `etl/cb_audit_contract.py`、`etl/cb_etl_pipeline.py`、`etl/cb_etl_runner.py` 生成的 audit report schema 与 message contract。
5. 在 `redemption_summary` 中新增/补强以下精确字段，使 audit report 能明确表达：
   - `redeem_risk_true_row_count`
   - `is_redeemed_true_row_count`
   - `redeem_split_state_row_count`
   - `redeem_terminal_only_row_count`
   - `missing_redemption_row_count`
   - `missing_redemption_ratio`
   - `redeem_risk_observability_mode`
   - `redeem_risk_unknown_interpretation`
6. audit report 文案不得再把 terminal-state 计数或 `delist_Date` 覆盖情况表述为 announcement-risk correctness proxy。
7. 如新增字段需要进入 root blockers / secondary findings，必须使用本 PRD Section 7 中定义的精确 type 枚举与 trigger 文案。

#### C. Validator Semantic Guard Alignment
8. 审查 `ams/validators/cb_data_validator.py` 与 Stage-F validator 汇总语义，清理仍以 `is_redeemed` 作为 redemption quality proxy 的旧阈值或旧叙事。
9. 如旧版 `DatasetSemanticValidator` / baseline threshold 仍保留 `is_redeemed_true_count_min` 这类历史 guard，必须明确处理：
   - 要么降级为 legacy direct-caller only 且在 Wave 2 contract 中显式排除；
   - 要么新增与 `redeem_risk` 拆分兼容的观测阈值；
   - 但不得让 downstream 审计继续把 terminal count 当作 risk correctness 证据。
10. `validator_summary.failure_type` 的新增精确枚举必须限制为：
   - `VALIDATOR_SCHEMA_FAILURE`
   - `VALIDATOR_SEMANTIC_FAILURE`
   - `OBSERVABILITY_CONTRACT_REGRESSION`
   message / typing 必须保持结构化，不得引入自由发挥的新 failure type。

#### D. Golden / Witness / Test Contract Alignment
11. 审查 `tests/golden/data/metadata.json` 与相关 witness artifacts，必要时新增 Wave 2 级别的 metadata 字段，使 split-state 与 observability semantics 能被 golden tests 断言。
12. 新增/修改 tests，覆盖 metrics artifact、audit report、validator summary、golden integrity 的 Wave 2 contract。
13. 保持 deterministic fixtures；不得引入依赖真实公告源的脆弱测试。

#### E. Documentation Alignment
14. 更新 `docs/architecture/ARCHITECTURE.md`，明确当前 redemption semantics 分层：
   - Wave 1：contract split 已落地
   - Wave 2：observability / validation alignment
   - Wave 3：event ledger / shared-state
15. 更新 `docs/ROADMAP.md`，使 roadmap 描述与 #13 / #15 的阶段定位一致。
16. 必要时补充 ETL metrics / audit schema 的文档注释，避免未来再次误读。

### 3.3 Scope of Code Changes
本波授权修改的目标区域应限定为：
- `etl/cb_etl_runner.py`
- `etl/cb_etl_pipeline.py`
- `etl/cb_audit_contract.py`
- `ams/validators/cb_data_validator.py`
- `tests/test_jqdata_sync_cb_metrics_artifact.py`
- `tests/test_jqdata_sync_cb_audit_report.py`
- `tests/test_audit_schema_and_promotion.py`
- `tests/validation/test_golden_integrity.py`
- `tests/golden/data/metadata.json`
- `docs/architecture/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- 与上述 observability / audit / validator contract 直接相关的 tests / fixtures / docs

如果实施中发现必须改动额外文件，必须满足两个条件：
1. 该文件与本 PRD 的 observability contract 直接相关；
2. 改动不越界进入 Wave 3 event-ledger / live-state 设计。

### 3.4 Required Semantic Contract
#### `redeem_risk`
- 继续表示 trading-risk semantics；
- 本波不改变其业务定义；
- 本波重点是让其 observability surface 明确、可审计、可区分于 terminal-state。

#### `is_redeemed`
- 继续表示 terminal/delist semantics；
- 本波不得将其重新包装成 announcement-risk completeness proxy；
- 本波允许它继续作为终态计数，但不允许它承担“风险覆盖已正确完成”的证明职责。

#### missing / incomplete redemption evidence
- 本波必须将其视为一类独立 observability concern；
- 它可以暂时不改变 Wave 1 的 placeholder/default 行为；
- 但必须在 metrics / audit / validator surface 中可见，避免被静默解释为“已知安全”。

### 3.5 Risk Boundaries
本波明确 **不做**：
- 不接完整 redemption event ledger
- 不接真实 live/backtest shared-state 引擎
- 不做公告撤回 / revision / 多源 reconciliation
- 不重写策略、Broker、Runner 排名逻辑
- 不要求真实公告源 E2E 才能完成验收

### 3.6 Evolution Intent
本波是 Phase 1.5 收尾中的 observability correction，目标是：
- 让 Wave 1 的 semantic split 不只存在于代码内部；
- 让外部观测面也能正确表达 terminal-state、risk-state、missing-evidence；
- 为 Wave 3 的真实事件驱动实现准备稳定的验收与审计口径。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Metrics artifact exposes split redemption observability**
  - **Given** AMS 完成一次 ETL / promote 运行
  - **When** metrics artifact 被写出并读取
  - **Then** artifact 中必须同时包含 `redeem_risk` 与 `is_redeemed` 的独立观测字段
  - **And** 不得只依赖 terminal-state 计数表达 redemption semantics

- **Scenario 2: Audit report distinguishes trading-risk from terminal-state semantics**
  - **Given** AMS 运行一次 audit-mode ETL
  - **When** 结构化 audit report 被生成
  - **Then** report 必须明确区分 trading-risk observability 与 terminal/delist observability
  - **And** 不得把 `is_redeemed` 或 `delist_Date` 覆盖情况表述为 announcement-risk correctness 的充分证据

- **Scenario 3: Split-state rows remain visible in observability artifacts**
  - **Given** 一个样本窗口中存在 `redeem_risk=True && is_redeemed=False` 的记录
  - **When** metrics artifact、audit report 或 golden witness 被读取
  - **Then** 系统必须提供可审计证据表明 split-state 真实存在

- **Scenario 4: Missing redemption evidence remains observable rather than silently safe**
  - **Given** 一个窗口中 redemption evidence 不完整、缺失或仍处于 Wave 1 过渡态
  - **When** AMS 输出 metrics 或 audit artifacts
  - **Then** 这些缺口必须可见
  - **And** 不得被静默折叠成纯粹的 `redeem_risk=False` 安全解读

- **Scenario 5: Validator surfaces remain meaningful under the split contract**
  - **Given** Wave 2 dual-field redemption semantics 已启用
  - **When** validators 与 validator summary 运行
  - **Then** 它们必须继续阻止 schema / observability regression
  - **And** 不得继续依赖把 `is_redeemed` 当作 risk correctness proxy 的歧义语义

- **Scenario 6: Documentation reflects the upgraded redemption observability contract**
  - **Given** Wave 2 改动完成
  - **When** 检查 `docs/architecture/ARCHITECTURE.md` 与 `docs/ROADMAP.md`
  - **Then** 文档必须明确说明 Wave 1、Wave 2、Wave 3 的分工与当前 redemption semantics

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### 5.1 Core Quality Risk
本波的核心风险不是实现报错，而是：
- 表面上“字段已经拆开”，但 artifacts 仍然误导人；
- terminal-state 指标继续冒充 risk-state quality；
- missing evidence 被默认值掩盖；
- Wave 3 还没开始，Wave 2 就已经把验收口径做歪了。

### 5.2 Recommended Test Layers
1. **Metrics artifact tests**
   - 验证新增/调整后的 metrics 字段真实落盘；
   - 验证 `redeem_risk`、`is_redeemed`、split-state、missing-evidence 相关字段可被读取并断言。
2. **Audit report schema / semantics tests**
   - 验证 `redemption_summary` / `validator_summary` 新字段与 message contract；
   - 验证 audit report 文案不会把 terminal-state 当成 risk-state 充分证据。
3. **Validator regression tests**
   - 验证 Wave 2 之后，schema regression 仍 fail closed；
   - 验证 `OBSERVABILITY_CONTRACT_REGRESSION` 能被发现；
   - 验证 legacy terminal-count 语义不会重新渗回主路径。
4. **Golden / witness integrity tests**
   - 验证 golden metadata 与 witness artifact 能表达 split-state / observability contract；
   - 保持 deterministic、repo-owned、可重复。
5. **Documentation contract tests / direct inspection**
   - 对必要文档做 path contract 或内容断言；
   - 确保 ROADMAP / ARCHITECTURE 同步。

### 5.3 Mocking Guidance
- 允许继续使用 deterministic fixture DataFrame、golden metadata、witness artifact；
- 不要求接真实公告源；
- 不得用 mock 掩盖“unknown / missing evidence”本应暴露的事实；
- 对 audit / metrics contract 的验证优先用 machine-readable artifact 断言，而不是只靠字符串人工阅读。

### 5.4 Quality Goal
Wave 2 完成后，AMS 必须达到：
- redemption semantics 不仅在代码内拆开，也在 metrics / audit / validator / docs 层拆开；
- `is_redeemed` 不再承担 risk correctness proxy 职责；
- missing / incomplete evidence 有清晰 observability；
- Wave 3 可以在不重写审计口径的前提下接入真实 event-driven state。

## 6. Framework Modifications (框架防篡改声明)
- 无。
- 本 PRD 不授权修改 SDLC framework 脚本。

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial execution brief created from Issue #15 after Wave 1 (#14) completed. The key conclusion is that Wave 2 should not add new business-state complexity; it should make the already-split redemption semantics observable, auditable, and non-misleading.
- **Audit Rejection (v1.0)**: Pending.
- **v2.0 Revision Rationale**: Pending.

---

## 7. Hardcoded Content (硬编码内容)
### `phase_positioning_statement`
```text
This change is a Phase 1.5 closeout observability correction, not a Wave 3 event-ledger implementation.
```

### `required_semantic_split_statement`
```text
redeem_risk = trading-risk window; is_redeemed = terminal/delist state.
```

### `forbidden_semantic_drift_statement`
```text
Terminal-state counts must not be treated as a proxy for announcement-risk correctness.
```

### `required_split_state_example`
```python
redeem_risk == True and is_redeemed == False
```

### `recommended_filter_shape_reference`
```python
exclude_if = is_st or redeem_risk or is_redeemed
```

### `required_metrics_artifact_keys`
```json
[
  "redeem_risk_true_count",
  "is_redeemed_true_count",
  "redeem_split_state_row_count",
  "redeem_terminal_only_row_count",
  "missing_redemption_row_count",
  "missing_redemption_ratio",
  "redeem_risk_observability_mode",
  "redeem_risk_unknown_interpretation"
]
```

### `required_redemption_summary_schema_wave2_additions`
```json
{
  "redeem_risk_true_row_count": 0,
  "is_redeemed_true_row_count": 0,
  "redeem_split_state_row_count": 0,
  "redeem_terminal_only_row_count": 0,
  "missing_redemption_row_count": 0,
  "missing_redemption_ratio": 0.0,
  "redeem_risk_observability_mode": "TRANSITIONAL_PLACEHOLDER",
  "redeem_risk_unknown_interpretation": "UNKNOWN_IS_NOT_SAFE"
}
```

### `required_validator_summary_failure_types`
```json
[
  "NONE",
  "VALIDATOR_SCHEMA_FAILURE",
  "VALIDATOR_SEMANTIC_FAILURE",
  "OBSERVABILITY_CONTRACT_REGRESSION"
]
```

### `required_root_blocker_types_wave2`
```json
[
  "REDEMPTION_SOURCE_GAP",
  "VALIDATOR_SCHEMA_FAILURE",
  "VALIDATOR_SEMANTIC_FAILURE",
  "OBSERVABILITY_CONTRACT_REGRESSION"
]
```

### `required_secondary_finding_types_wave2`
```json
[
  "MISSING_REDEMPTION_ROWS",
  "REDEEM_RISK_UNKNOWN_ROWS_PRESENT",
  "REDEEM_SPLIT_STATE_ROWS_PRESENT"
]
```

### `required_redeem_risk_observability_mode_enum`
```json
[
  "TRANSITIONAL_PLACEHOLDER",
  "EVENT_BACKED"
]
```

### `required_redeem_risk_unknown_interpretation_enum`
```json
[
  "UNKNOWN_IS_NOT_SAFE",
  "UNKNOWN_REQUIRES_EXPLICIT_AUDIT_VISIBILITY"
]
```

### `required_audit_message_lines`
```json
[
  "redeem_risk is the trading-risk window signal.",
  "is_redeemed is the terminal/delist signal.",
  "Terminal-state counts must not be treated as a proxy for announcement-risk correctness.",
  "Unknown or transitional redeem-risk evidence must remain audit-visible."
]
```

### `required_observability_regression_message`
```text
Observability contract regression: redeem-risk semantics are no longer explicitly distinguishable from terminal-state semantics in machine-readable artifacts.
```

### `required_executable_checklist_items`
```text
A. Metrics Contract Alignment
B. Audit Report Semantic Alignment
C. Validator Semantic Guard Alignment
D. Golden / Witness / Test Contract Alignment
E. Documentation Alignment
```
