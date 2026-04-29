---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: CB Premium Pagination, is_st Query Hardening, and Validator Resilience

## 1. Context & Problem (业务背景与核心痛点)
AMS 当前的可转债 ETL 在真实 full-window 研究窗口下仍然无法稳定完成 canonical source ingestion。最新 E2E audit（`/root/projects/AMS/reports/cb_etl_audit_2025-01-18_2026-01-25.json`）已经证明，旧的 `125302` / underlying mapping blocker 已经被压下去，当前真实 blocker 已切换为 source acquisition 层在真实 JQData 约束下不鲁棒。

本次 audit 的关键证据：
- Stage B（Supportability）已通过：
  - `supportable_row_count = 257316`
  - `supportable_unique_bond_count = 1045`
  - `missing_underlying_row_count = 0`
- Stage C（Premium Join）失败：
  - `premium_source_row_count = 5000`
  - `premium_joined_row_count = 5000`
  - `missing_premium_row_count = 252316`
  - `missing_premium_unique_bond_count = 1031`
  - `missing_premium_ratio = 0.980568639338401`
  - root blocker = `PREMIUM_SOURCE_TRUNCATION`
- Stage D（is_st Join）失败：
  - `is_st_source_row_count = 0`
  - `is_st_joined_row_count = 0`
  - provider message 显示账号只支持 `2025-01-20` 至 `2026-01-27` 的窗口，当前请求 `2025-01-18` 起始时间会触发 source 为空/失败问题。
- Stage F（Validator）失败：
  - 直接报错 `"['is_st'] not in index"`
  - `schema_validator_status = NOT_RUN`
  - `semantic_validator_status = NOT_RUN`

因此，1196 的本质不是“某个字段算错了”，而是：

> AMS 当前的 CB ETL source ingestion 层假设“单次 query 可以拿到完整且可直接验证的数据”，但这个假设在真实 JQData 大窗口场景下是错误的。

具体来说，本 issue 需要解决三个彼此相关但同层的问题：
1. `bond.CONBOND_DAILY_CONVERT` 的 premium source 不能再依赖单次 `run_query`，否则会被 5000 行上限静默截断；
2. `finance/STK is_st` 获取路径必须对 provider 账号可用窗口和 query 行为具备明确、稳定、可测试的处理策略，不能再整段返回 0 行；
3. Validator 不能在上游 stage 缺列时直接 Python-level 崩溃，必须输出结构化结果，以保证 audit 可观测性和 production fail-fast 的边界都清晰。

## 2. Requirements & User Stories (需求定义)

### Functional Requirements
1. AMS 必须把 premium source ingestion 从“单次 full-window query”改为**确定性分页 / 分批拉取**。
2. 对 `bond.CONBOND_DAILY_CONVERT` 的拉取，系统必须：
   - 在 full-window supportable universe 上不再静默卡在 5000 行；
   - 允许按日期窗口和/或 bond code 批次拉取；
   - 在合并后输出完整、可去重、可 join 的 normalized premium dataset。
3. `is_st` source acquisition 必须从“可能整段 0 行”改为**窗口安全 / 权限感知 / 结果可解释**的获取逻辑。
4. 如果 provider 对请求窗口有限制，系统必须：
   - 明确识别该限制；
   - 在可支持窗口内尽可能获取 source；
   - 对不可支持部分给出结构化 stage failure / stage gap，而不是无声返回空 source。
5. Validator 阶段必须在 required canonical columns 因上游 stage failure 而缺失时，输出结构化 `NOT_RUN` / `FAIL` 结果，而不是直接抛出 Python KeyError。
6. Production promote runner (`sync_cb_data`) 必须继续保持**strict fail-fast**：
   - 不允许用默认值伪造 `premium_rate`、`is_st` 或 `is_redeemed`；
   - 不允许为了“让 ETL 过”而静默填补缺失关键字段。
7. Audit runner (`audit_cb_data`) 必须在修复后能够重新对同一窗口输出完整的 structured report，并且不再因为 premium truncation 或 validator missing-column 崩溃而失真。

### Non-Functional Requirements
1. 本 PRD 不得修改 strategy/backtest 业务逻辑。
2. 本 PRD 不得修改 validator 的业务阈值、语义规则或 golden/semantic 判断标准。
3. 本 PRD 不得通过 default-fill / hardcoded fallback 值来“补齐” `premium_rate`、`is_st`、`is_redeemed`。
4. 本 PRD 必须保持 staged pipeline 架构，不得把 audit runner 和 promote runner 分裂成两套不共享逻辑的 ETL。
5. 修复后必须有 regression coverage，证明 full-window premium query path 不会再 silent truncation，且 validator 不会因缺列直接崩溃。

### User Stories
- 作为 Boss，我希望在真实可转债 full-window 上，premium source 不会只返回 5000 行而导致整条 ETL 失真。
- 作为 Manager，我希望 `is_st` source 对 provider 限制有清晰处理，不再出现“Stage D 0 行、Stage F 直接崩”的链式假象。
- 作为 Reviewer/Auditor，我希望 audit 结果能真实反映 source coverage 与 validator state，而不是被 Python-level missing-column 异常掩盖。

### Boundaries
**In Scope**
- `CONBOND_DAILY_CONVERT` 分页 / 分批查询
- premium source 合并后的去重与 coverage 校验
- `is_st` query/window hardening
- validator 缺列前置检查与结构化结果映射
- 对应测试与 audit regression coverage

**Out of Scope**
- Redemption gap 的业务分析和修复（另行 issue）
- `main_runner.py` 统一 CLI 回测入口
- Live QMT integration
- 修改 validator 业务规则 / 语义门槛
- 修改 canonical research dataset governance（`ISSUE-1142`）

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Target Files
本 PRD 允许修改的 AMS 文件应以以下路径为主：
- `/root/projects/AMS/etl/cb_etl_pipeline.py`
- `/root/projects/AMS/etl/jqdata_sync_cb.py`
- `/root/projects/AMS/tests/test_jqdata_sync_cb_audit_report.py`
- `/root/projects/AMS/tests/test_jqdata_sync_cb_logic.py`
- `/root/projects/AMS/tests/test_jqdata_sync_cb.py`
- 如确有必要，可新增面向 staged ETL 的测试文件，但必须限制在 `tests/` 下的 ETL 相关测试，不得扩散到无关模块。

### 3.2 Premium Source Fix Strategy
当前 Stage C 的关键缺陷在于：
- 代码对所有 supportable bond raw codes 做一次 `bond.CONBOND_DAILY_CONVERT` query；
- 在真实窗口中，该 query 只回 5000 行；
- 系统把这个结果当作“完整 source”，导致后续出现 `missing_premium_ratio ~= 98%`。

修复策略必须满足：
1. 把 premium source acquisition 抽象成**deterministic batched fetch**；
2. 批次划分优先采用**日期窗口切片**（例如按月或按更细粒度窗口），必要时允许与 code batching 组合；
3. 每个 batch 的结果合并后，必须做以下校验：
   - key normalization（`date + bond_code_raw + bond_exchange_code`）一致；
   - duplicate-key 行为可预期（必须显式去重或 fail）；
   - source total row count 不再固定卡在 5000 这一 JQData 单次上限特征值；
4. 如果 batched fetch 仍不足以覆盖 supportable universe，必须显式输出 source acquisition failure / coverage failure，不得 silent degrade。

### 3.3 is_st Query Hardening Strategy
当前 Stage D 的失败不是业务 join 逻辑本身错误，而是 source 获取策略不鲁棒：
- full requested window 触发 provider 可用范围边界；
- 结果表现成整段空 source；
- downstream 无法区分“真实无 ST”与“source 根本没拿到”。

修复策略必须满足：
1. 把 `is_st` source 获取实现为**窗口安全**的流程；
2. 当 provider 对请求日期范围有限制时，代码必须：
   - 明确识别这类 provider/permission exception；
   - 使用 provider 支持的有效子窗口重试，或在无法安全重试时返回结构化失败；
   - 不允许把“请求失败导致的空结果”误判成“source 中本来就没有 ST 数据”；
3. Stage D 的 `failure_type`、`message` 和 source coverage 统计必须与真实 source 状态一致。

### 3.4 Validator Resilience Strategy
当前 Stage F 直接对 `df_work[CANONICAL_CB_COLUMNS]` 做索引，导致上游缺列时直接报 `['is_st'] not in index`。

修复策略必须满足：
1. 在 validator 执行前，先检查 required canonical columns 是否齐全；
2. 如果缺列是由上游 stage failure 导致，则：
   - validator 不得再抛 Python KeyError；
   - 必须输出结构化 `NOT_RUN` / `FAIL` 映射；
   - message 中明确指出缺失列与对应上游 stage 问题；
3. 这一步只是**前置条件硬化**，不是修改 validator 规则本身。

### 3.5 Production vs Audit Contract
- **Production runner (`sync_cb_data`)**：仍然必须严格 fail-fast；关键字段缺失时必须阻止 promotion。
- **Audit runner (`audit_cb_data`)**：必须尽可能完成所有 stage 观测，并输出完整 report，不得因单个缺列异常使整个 audit 失真。

### 3.6 Explicit Non-Solution Guardrails
以下做法在本 PRD 中明确禁止：
- 用 `0.0`、`False`、空字符串等默认值伪造 `premium_rate` / `is_st` / `is_redeemed`
- 为了“凑过 validator”而放宽 schema/semantic 规则
- 仅修改 audit runner 而不修共享 staged pipeline
- 顺手混入 redemption gap 业务推断或 dataset governance 改造

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Full-window premium source no longer silently truncates**
  - **Given** JQData credentials are configured and AMS runs `audit_cb_data("2025-01-18", "2026-01-25")`
  - **When** Stage C fetches premium data for the full supportable universe
  - **Then** the audit report must not classify Stage C as `PREMIUM_SOURCE_TRUNCATION`
  - **And** the premium source acquisition path must no longer present the characteristic single-call 5000-row truncation behavior as the final merged source result

- **Scenario 2: is_st source failure is no longer misrepresented as an empty successful fetch**
  - **Given** the same audit window and provider account constraints
  - **When** Stage D fetches `is_st` source data
  - **Then** the stage must either produce non-empty source coverage within the provider-supported effective window or return an explicit structured failure/gap classification
  - **And** it must not silently collapse into an unexplained all-empty `is_st` join result

- **Scenario 3: Validator no longer crashes on upstream missing columns**
  - **Given** an audit or promote flow where an upstream stage fails to populate a required canonical column
  - **When** Stage F runs
  - **Then** the system must emit structured validator status and message fields
  - **And** it must not raise a raw `['is_st'] not in index` style KeyError to the outer caller

- **Scenario 4: Production promote semantics remain strict**
  - **Given** the production runner `sync_cb_data(...)`
  - **When** any supportable record still lacks a required critical field after source acquisition and joins
  - **Then** canonical promotion must remain blocked
  - **And** the system must fail explicitly rather than default-filling missing values

- **Scenario 5: The original blocker is replaced by accurate observability rather than silence**
  - **Given** the repaired Stage C/D/F logic
  - **When** the audit runner is executed again on `2025-01-18` to `2026-01-25`
  - **Then** the resulting JSON report must provide a complete, structured outcome for Stages C, D, and F
  - **And** any remaining blocker must reflect the real remaining data problem rather than a tool-level truncation or missing-column crash

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
核心质量风险不是“代码语法错”，而是**真实 source acquisition 在 provider 约束下 silently degrade**，导致 downstream 看起来像业务数据问题，实则是拉取策略问题。

测试策略要求：
1. **Mocked unit/integration tests** 覆盖：
   - premium batched fetch 的分片与合并逻辑；
   - duplicate key / normalized join key 的处理；
   - `is_st` provider 异常或窗口限制下的 structured fallback / structured failure 行为；
   - validator 在缺列时的结构化状态映射；
2. **Audit regression tests** 必须证明：
   - 不再把 5000 行单次返回当成完整 premium source；
   - 不再出现 raw KeyError `['is_st'] not in index`；
3. **Live validation**：修复后必须使用真实窗口 `2025-01-18` ~ `2026-01-25` 重新跑一次 audit runner，作为最终验证信号；
4. 若 production runner 行为受影响，必须补足对 `sync_cb_data(...)` strict fail-fast contract 的回归验证，确保没有被默认值污染绕过。

质量目标：
- Stage C 的“5000 行静默截断”问题被消除；
- Stage D 的 source 行为与 provider 限制之间的关系变得可解释、可测试；
- Stage F 只输出结构化结果，不再因缺列产生原始 Python 崩溃；
- 修复后剩余问题若仍存在，应是真实数据问题，而不是 acquisition/observability 假象。

## 6. Framework Modifications (框架防篡改声明)
- None

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 将 ISSUE-1196 从“只修 premium 5000 行截断”扩展为同层 source-ingestion hardening：P1 premium batching + P2 is_st query hardening + P4 validator resilience。
- **Audit Rejection (v1.0)**: None yet.
- **v2.0 Revision Rationale**: None yet.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`validator_missing_columns_prefix`**
```text
Validator skipped because required canonical columns are missing after upstream stage failures:
```

- **`premium_truncation_guard_message`**
```text
Premium source query returned the provider single-call cap characteristic and must be retried with deterministic batching.
```

- **`is_st_window_guard_message`**
```text
is_st source query exceeded the provider-supported date window; effective-window handling or structured gap classification is required.
```
