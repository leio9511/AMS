---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix JQData Premium Live Join Contract and Validator Dtype Normalization

## 1. Context & Problem (业务背景与核心痛点)
AMS 已完成一轮较大的可转债 ETL field-governed refactor。该轮工作的目标是把 CB ETL 从“字段语义混乱、慢字段拖垮主链路、失败原因说不清”的状态，升级成“core/enrichment 分层、audit 可机器判定、失败可恢复”的系统。

该大方向已经落地并通过了 SDLC/UAT，但 2025-11-01 ~ 2025-11-30 的 live JQData audit 仍暴露出两个窄而明确的剩余 correctness blocker。相关实测命令如下：

```bash
JQDATA_USER=... JQDATA_PWD=... PYTHONPATH=/root/projects/AMS \
python3 -m etl.cb_etl_runner --data-source jqdata --start 2025-11-01 --end 2025-11-30 --audit
```

对应 audit artifact：
- `/root/projects/AMS/reports/cb_etl_audit_2025-11-01_2025-11-30.json`

### 1.1 已确认问题 A：JQData premium source rows 存在，但 Stage-C canonical join 为 0
live audit 证据：
- `premium_source_row_count = 7621`
- `premium_source_unique_bond_count = 385`
- `supportable_row_count = 7989`
- `supportable_unique_bond_count = 405`
- `premium_joined_row_count = 0`
- `missing_premium_ratio_against_active_universe = 1.0`

进一步法证确认：
- 按 `(date, bond_code_raw)` 统计，premium source 与 active universe 的 key overlap 存在。
- 按 `(date, bond_code_raw, bond_exchange_code)` 统计，key overlap 为 0。
- live JQData `CONBOND_DAILY_CONVERT` 返回的是裸 `code`（如 `110062`），没有 suffix，也没有 `exchange_code` 列。
- `_normalize_premium_source()` 因此产出 `bond_exchange_code = None`。
- 但 canonical active universe 的 bond key 使用 `XSHG` / `XSHE`，Stage-C merge keyed on `['date', 'bond_code_raw', 'bond_exchange_code']`，导致所有 premium rows miss。

结论：
> 这不是“JQData 没有 premium source 数据”的问题，而是 JQData premium live join contract 在 exchange-code 维度上断裂。

### 1.2 已确认问题 B：Stage-F validator 在 live path 上仍有 dtype normalization 缺口
同一份 live audit 还报告：
- `VALIDATOR_SCHEMA_FAILURE`
- `expected series 'ticker' to have type string[pyarrow], got object`

当前 `run_stage_f_validator()` 会显式规范：
- `close` -> numeric
- `is_st` / `is_redeemed` -> bool

但没有显式规范：
- `ticker` -> validator contract 所期望的 string dtype

结论：
> 这是独立于 premium join 的 canonical dtype-normalization bug，会制造 schema 假失败并掩盖真实业务结论。

### 1.3 本 PRD 的边界
本 PRD 是 `ISSUE-1218` 的执行级修复 brief，目标很窄：
- 修复 JQData premium live join contract
- 修复 live validator dtype normalization

**本 PRD 明确不处理以下内容：**
- JQData 5000 行上限的完整 anti-truncation / recursive batching 方案（由 `ISSUE-1196` 继续独立跟踪）
- TuShare premium 慢字段限流与替代源策略
- dual-source gap filling / provider routing / full-history rebuild 平台化能力
- live rerun 后 newly discovered 的其它独立问题；这些问题的分析、归因、是否立项、是否扩展需求，均不属于本 PRD 当前 coder scope，必须由 Manager/Boss 在本 PRD 之外单独处理

本 PRD 的目标不是把 JQData premium 路径一次性做成全窗口最终版，而是把当前已证实的 live correctness bug 修平，让 2025-11 audit 先从“本地 join/dtype bug 导致的假失败”变成“可信的真实 coverage 结果”。

### 1.4 外部前置假设（External Preconditions / Launch Notes）
本 PRD 的 supporting evidence 依赖真实 JQData live rerun。该依赖属于 **SDLC 启动前的外部前置条件**，是给决定是否启动 SDLC 的 Manager / Launcher 看的，不属于 coder、reviewer、planner、verifier 或 UAT 的执行职责。

**当前人工前置假设：**
- `JQDATA_USER` 环境变量存在且非空
- `JQDATA_PWD` 环境变量存在且非空
- 以下真实 supporting-evidence 命令具备最小可执行条件：

```bash
JQDATA_USER=... JQDATA_PWD=... PYTHONPATH=/root/projects/AMS \
python3 -m etl.cb_etl_runner --data-source jqdata --start 2025-11-01 --end 2025-11-30 --audit
```

**责任边界说明：**
- 这些前置条件由启动 SDLC 流程的人在流程外部手动确认。
- 若未来要自动化，应由 SDLC 启动器/编排层增加自动检测，而不是把该检查动作下放给 coder 或其它 SDLC 内部执行角色。
- 如果这些外部前置条件不成立，正确动作是“不启动本 PRD 的 SDLC execution”，而不是在 SDLC 内部创建额外修复任务。

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements

#### FR-1: JQData premium live rows 必须恢复 canonical join 所需的 exchange contract
- 当 `fetch_cb_price_changes()` 的请求入参是带 suffix 的 bond tickers（如 `110062.XSHG`）时，provider 必须基于请求集恢复 `raw_code -> exchange suffix` 映射。
- 当 live `CONBOND_DAILY_CONVERT` 返回裸 `code` 且无 `exchange_code` 列时，provider 必须在返回上游之前补齐 deterministic `exchange_code`。
- `_normalize_premium_source()` 之后，JQData premium rows 必须产出非空且正确的 `bond_exchange_code`，以满足 Stage-C merge contract。

#### FR-2: Stage-C premium join 不得再出现“source rows > 0 但 joined rows = 0”的本地 contract 失配
- 当 JQData premium source rows 实际存在且与 active universe 在 `(date, raw_code)` 上存在真实 overlap 时，Stage-C merge 必须能够在 `(date, bond_code_raw, bond_exchange_code)` 上把 rows 正确 join 进 canonical active universe。
- 不允许再因本地 exchange-code 丢失导致所有 rows miss。

#### FR-3: Validator 前必须执行 canonical dtype normalization
- 在进入 Stage-F schema validation 前，core validator 输入必须显式规范 canonical core columns 的 dtype。
- 至少必须确保：
  - `ticker` 满足 validator contract 期望的 string dtype
  - 现有的 `close` numeric、`is_st` bool、`is_redeemed` bool 规范逻辑不被破坏
- 该规范化应优先设计为可复用 helper，而不是只在单点 ad-hoc cast。

#### FR-4: 修复后 audit 结果必须把“本地 bug”与“真实 source gap”分开
- 修复后，如果 premium 仍有缺口，audit 必须将其反映为真实 source / query limitation，或真实 coverage gap。
- 不允许再由本地 join contract bug 或 dtype bug 伪造 100% missing premium 结论。
- 本 PRD 对真实 rerun 的要求，仅限于为这两个已知 bug 的修复提供 supporting evidence 或 artifact capture；若 rerun 暴露新的独立问题，其分析与后续处置不属于本 PRD coder scope。

### 2.2 Non-Functional Requirements
- 修复必须保持当前 field-governed 设计边界，不得把 provider 再次写回 God Object。
- 修复不得扩大本 PRD 范围至 `ISSUE-1196` 的完整 anti-truncation 方案。
- 修复必须对 live JQData 返回形态有针对性 regression coverage，而不是仅覆盖“理想化 mock shape”。
- 修复后的 audit 结论必须可重复、可机器判定、可对比前后变化。

### 2.3 User Stories
- 作为 Boss，我希望当 JQData premium source 本身有数据时，系统不要因为本地 join bug 把结果误报为 100% 缺失。
- 作为维护者，我希望 Stage-F validator 不要因为 dtype 噪音把原本可定位的业务问题掩盖掉。
- 作为研究/回测使用者，我希望 2025-11 这类真实窗口的 JQData audit 先变成可信结论，再决定是否继续处理更大窗口的 5000 行限制或 source 边界问题。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本 PRD 采用“窄修复、不越界”的策略。目标不是重做上一轮 field-governed refactor，而是在现有边界内补齐 JQData live correctness。

### 3.1 修复对象与文件边界
本 PRD 允许修改的业务代码主要限于：
- `etl/jqdata_provider.py`
- `etl/cb_etl_pipeline.py`
- `ams/validators/cb_data_validator.py`（仅当需要配合 canonical dtype normalization helper 或 contract 对齐）

测试主要预期新增/修改于：
- `tests/test_jqdata_premium_coverage.py`
- `tests/test_jqdata_sync_cb_hardening.py`
- `tests/test_cb_validator_contract_boundaries.py`
- 以及与 Stage-C / validator live shape 有关的现有测试文件

### 3.2 JQData premium join contract 的修复策略
选定策略：**在 provider 层恢复 exchange-code contract，而不是在 Stage-C merge 后补救。**

原因：
- live provider 返回的 premium rows 缺失 exchange suffix，这是 provider-shape 与 canonical contract 的适配问题。
- 如果在 provider 层就基于请求 tickers 恢复 `raw_code -> exchange suffix`，则 `_normalize_premium_source()` 和后续 pipeline contract 可以保持一致。
- 这样修复 blast radius 更小，也更符合“thin adapter 负责 provider shape normalize”的边界。

预期策略：
1. 在 `fetch_cb_price_changes()` 中，根据请求入参 tickers 构建 deterministic raw-code/exchange 映射。
2. 对 live `run_query` 返回结果补 `exchange_code` 列。
3. 继续走现有 `_normalize_premium_source()`，但确保最终 `bond_exchange_code` 非空且与 canonical key contract 一致。
4. 保持 JQData provenance 逻辑不被破坏。

### 3.3 Validator dtype normalization 的修复策略
选定策略：**在 Stage-F schema validation 前增加可复用的 canonical dtype normalization 步骤。**

原因：
- `ticker` dtype 问题不是 provider 特定逻辑，而是 canonical core-validator 输入的规范化缺口。
- 与其把它藏在 validator 内部或临时写一个 `astype(str)`，更稳妥的方式是显式定义“进入 validator 前，哪些 core columns 必须是什么 dtype”。
- 这也更符合 field-governed 设计下“canonical contract 明确可执行”的方向。

预期策略：
1. 在 Stage-F 前，规范 core validator 输入 DataFrame 的 dtype。
2. 至少保证 `ticker` 满足 schema contract。
3. 不破坏当前 `close` / bool 字段的 existing normalization。
4. 若已有合适 helper，可以复用；若无，则新增小而明确的 helper，避免散落 cast。

### 3.4 明确 out-of-scope 的技术决策
以下内容在本 PRD 中**不得顺手扩展实现**：
- 命中 5000 行上限后的 recursive/date-window/code-window 持续细分查询
- JQData full-window anti-truncation 方案
- JQData/TuShare dual-source gap filling
- TuShare premium 限流治理增强

这些内容要继续留在各自 issue 中，尤其是 `ISSUE-1196`。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

### 4.1 Acceptance Semantics (验收语义总则)
本 PRD 的验收对象不是“整份 live audit 必须全绿”，而是“本 PRD 明确承诺修复的两个已知本地 bug 是否被消除”。

**因此，验收必须分成三层：**
1. **Implementation Proof**：代码修改落地到允许的文件边界，且 targeted regression tests 通过。
2. **Bug-Specific Regression Proof**：受控测试场景下，两个已知 bug 的旧错误签名都被消除。
3. **Live Witness / Artifact Capture**：真实 JQData rerun 只用于确认这两个旧错误签名在真实环境下不再出现，并保留客观 artifact；它不是“所有下游问题必须同时清零”的总闸门。

**以下两类旧错误签名，才是本 PRD 的精确验收对象：**
- **旧签名 A（premium live join contract bug）**
  - 在 2025-11-01 ~ 2025-11-30 这个固定窗口里，`source_coverage.premium_source_row_count > 0`
  - 且 `premium_join_summary.premium_joined_row_count == 0`
  - 且该结果源于 live premium rows 缺失 `exchange_code` 导致 canonical key contract 断裂
- **旧签名 B（Stage-F ticker dtype bug）**
  - `validator_summary.core_validator_message` 包含以下精确文本：

```text
expected series 'ticker' to have type string[pyarrow], got object
```

**只要本 PRD rerun 后旧签名 A/B 均消失，就说明本 PRD 承诺修复的问题已经被验证修复。**
任何新暴露出来的、与旧签名 A/B 无关的问题，都不得反向污染本 PRD 的验收结果。

- **Scenario 1: JQData live premium rows can join into canonical active universe when source data exists**
  - **Given** 2025-11 JQData live premium source rows exist and the provider returns raw `code` values without exchange suffixes
  - **When** the CB ETL audit runs Stage C on the JQData path
  - **Then** the premium source rows are normalized into canonical bond keys with valid exchange codes
  - **And Then** the fixed window live witness must not reproduce old signature A (`premium_source_row_count > 0` together with `premium_joined_row_count == 0` caused by local exchange-code loss)

- **Scenario 2: Live-shape regression is covered explicitly**
  - **Given** a regression test where requested JQData tickers include suffixes but the mocked `CONBOND_DAILY_CONVERT` response contains only raw `code` and no `exchange_code`
  - **When** Stage C normalizes and joins premium data
  - **Then** the premium rows still join correctly into the canonical active universe instead of dropping to zero overlap

- **Scenario 3: Validator no longer fails on ticker dtype mismatch**
  - **Given** a live-path canonical core DataFrame whose `ticker` values are semantically correct
  - **When** Stage F runs schema validation
  - **Then** the audit does not fail with the exact old signature B text:

```text
expected series 'ticker' to have type string[pyarrow], got object
```

- **Scenario 4: Remaining missing premium after the fix is reported as real coverage, not local contract failure**
  - **Given** the Nov 2025 JQData audit is rerun after the fix
  - **When** premium coverage is computed against the active in-window universe
  - **Then** any remaining missing premium rows are reflected as a real source/query limitation or coverage gap rather than a local exchange-code join bug or dtype bug
  - **And Then** any newly exposed blocker outside old signatures A/B must be treated as a separate follow-up issue rather than a failure of this PRD’s acceptance

- **Scenario 5: Scope guard — no accidental expansion into 5000-cap anti-truncation project**
  - **Given** this PRD is executed downstream
  - **When** the implementation is completed
  - **Then** the delivered code fixes the Nov 2025 live join/dtype correctness issues without claiming to solve the separate full-window 5000-row anti-truncation problem tracked under `ISSUE-1196`

### 4.2 Verification Outcome Matrix (验收结果矩阵)
- **PASS-A**
  - targeted code/test gates 全部通过；
  - 真实 rerun 中旧签名 A 消失；
  - 真实 rerun 中旧签名 B 消失；
  - 且未暴露新的独立 blocker。
- **PASS-B**
  - targeted code/test gates 全部通过；
  - 真实 rerun 中旧签名 A 消失；
  - 真实 rerun 中旧签名 B 消失；
  - 但真实 rerun 暴露了新的、与本 PRD 无关的独立问题。
  - **解释**：本 PRD 仍然验收通过，但必须单独记录 follow-up issue。
- **FAIL-A**
  - 真实 rerun 或 targeted regression 仍然复现旧签名 A。
- **FAIL-B**
  - 真实 rerun 或 targeted regression 仍然复现旧签名 B。


## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
核心质量风险不是“代码跑不跑”，而是：
- 测试只覆盖理想化 mock shape，没覆盖 live provider 返回形状
- schema contract 看似严格，但 live canonical 输出在 dtype 上未显式规范
- 修复时把 `ISSUE-1196` 的大范围 batching 问题误混进来，导致 scope 再次膨胀

### 5.1 Test Strategy
- **优先做 targeted regression tests**，覆盖 live-shape 问题：
  - requested tickers 带 suffix
  - returned premium rows 只有 raw code
  - 无 `exchange_code`
  - 断言 Stage-C join 不再为 0
- **保留并复用现有 JQData premium coverage 测试**，确认 provenance、convert_price 等 governed fields 不回退。
- **增加 validator contract test**，明确 `ticker` dtype normalization 在 Stage-F 前发生，而不是依赖隐式 pandas 行为。
- **做一次 real JQData audit recheck**（2025-11-01 ~ 2025-11-30），但该 rerun 的验证职责仅限于：
  - 检查旧签名 A 是否消失；
  - 检查旧签名 B 是否消失；
  - 产出可供 Manager/Boss 后续研判的客观 artifact。
- **明确禁止**把该 real rerun 扩展解释为“所有新暴露问题都必须在本 PRD 内修完”。

### 5.2 Quality Goal
本 PRD 的质量目标不是“让 JQData 在所有窗口都 100% 覆盖 premium”，也不是“让整份 rerun audit 必须整体全绿”，而是：
- 消除已证实的本地 live join bug（旧签名 A）
- 消除已证实的 dtype schema 假失败（旧签名 B）
- 让 2025-11 JQData audit 的结果第一次可以把“本地假失败”与“真实剩余问题”精确区分开

### 5.3 Mocking / Live Balance
- 单元/集成测试中必须 mock JQData provider shape。
- 但最终 closure 应尽量包含一次真实 JQData audit evidence / artifact capture。
- 该真实 rerun 在本 PRD 内的职责，仅限于辅助确认两个已知本地 bug 是否已消除，以及保留可供 Manager/Boss 后续研判的客观 artifact。
- 如果真实 rerun 暴露新的 scope 外问题，应单独记录并单独立项；这不授权 coder 在当前 PRD 内继续自由修复，也不把 audit 深度分析责任下放给 SDLC coder。
- 不允许仅凭 mock tests 通过就宣称 `ISSUE-1218` 关闭。

## 6. Framework Modifications (框架防篡改声明)
- None

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 从 `ISSUE-1211` 的大 corrective architecture 里剥离出 `ISSUE-1218`，聚焦 live JQData correctness 的最后两颗钉子：premium live join contract 与 validator dtype normalization。
- **Scope Decision**: Boss 明确要求不要把不相关内容混在一起，因此本 PRD 明确排除 `ISSUE-1196` 的完整 5000-row anti-truncation 方案。
- **Rationale**: 当前 2025-11 live audit 的直接 root cause 已法证确认，不需要再用平台级议题稀释执行边界。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- None
