---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix is_st nullable boolean validator rejection in Stage-F

## 1. Context & Problem (业务背景与核心痛点)
AMS 的 CB ETL pipeline 在 full-window JQData audit（2025-01-24 ~ 2026-01-31）中通过全部前置 stage，最终在 Stage-F validator 被拦下。

对应 issue 背景应为 **ISSUE-1223**（不是 ISSUE-1123）：
- `is_st_join_summary.status = PASS`（is_st join 本身成功，覆盖 109,325 行）
- 但有 **503 行（0.46%）的 `is_st` 值为 NA**（实时数据源 coverage gap）
- `_normalize_contract_bool_series()` 当前对“存在 NA 的布尔列”统一返回 **nullable boolean**（保留 NA）
- `CBDataValidator` 的 schema 同时声明 `"is_st": pa.Column(bool, nullable=False)`
- 因此 `validate_dataframe()` 在 Stage-F 报出 `VALIDATOR_SCHEMA_FAILURE`

当前失败签名来自真实 audit artifact：
- `/root/projects/AMS/reports/cb_etl_audit_2025-01-24_2026-01-31.json`
- `validator_summary.core_validator_message` 精确包含：

```text
non-nullable series 'is_st' contains null values:
```

这不是前置 join 失败，也不是业务逻辑崩坏，而是 **Stage-F core-validator normalization contract 与 schema contract 对 `is_st` 的语义不一致**。

### 1.1 必须看清的背景约束
根据 `ISSUE-1223` 与现有实现，当前系统同时存在以下事实：
1. `is_st` 与 `is_redeemed` 都会经过共享 helper `_normalize_contract_bool_series()`。
2. `is_st` 的业务语义是“长期持续的 ST 状态标记”。在 real-time source 有少量 coverage gap 时，**缺失默认填 `False`** 在当前业务上下文中是可接受且更安全的。
3. `is_redeemed` 不属于本次问题来源，且 **不得因为修 `is_st` 而顺手改变 `is_redeemed` 的现有语义**。
4. `missing_is_st_row_count` / `missing_is_st_ratio` 已在 Stage-D audit summary 中存在，且必须继续保留，用于暴露 future source coverage regression。

### 1.2 上一版 PRD 的致命矛盾
上一版 PRD 把修复落点写成“只改共享 helper `_normalize_contract_bool_series()`，同时保证 `is_redeemed` 行为不变”。

这在架构上是自相矛盾的：
- 共享 helper 同时服务 `is_st` 与 `is_redeemed`
- 若直接把该 helper 改成“遇到 NA 一律填 `False`”，会把 field-specific 语义偷偷扩散到 `is_redeemed`
- 这违反本项目现有 field-governed discipline，也违反本 PRD 自己声称的 minimal blast radius

**因此，本 PRD 必须明确改写为：修复不是改“通用 bool helper 的全局语义”，而是引入 `is_st` 的显式 field-specific normalization contract。**

### 1.3 本 PRD 的目标
本 PRD 的目标很窄，只做一件事：

> **让 Stage-F 不再因为 `is_st` 的少量 NA 而拒绝整条 pipeline，同时保持 `is_st` coverage gap 继续可观测，且不改变 `is_redeemed` 的现有行为。**

本 PRD **不** 处理：
- validator schema 的整体重构
- `is_redeemed` 语义重定义
- 上游 is_st source gap 的补洞
- 其它 bool 列的一般化默认值框架

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements

#### FR-1: is_st 的少量 NA 不得再导致 Stage-F validator 失败
- 当 `is_st_join_summary.status = PASS` 但 `is_st` 列存在少量 NA 时，Stage-F 必须能够正常通过 core schema validation
- 不得因为 503 行（0.46%）的 `is_st` 缺口而阻塞整条 ETL pipeline

#### FR-2: is_st 的默认填充值必须是 field-specific 的显式语义，而不是共享 helper 的隐式副作用
- `is_st` 的 NA 必须在 **明确的 field-specific normalization 路径** 中被填充为 `False`
- 不允许通过改写共享 `_normalize_contract_bool_series()` 的通用语义来“顺手”实现
- 设计必须让 reviewer 能从代码结构上直接看出：`is_st` 的 fill-`False` 是特例契约，不是全局 bool 列规则

#### FR-3: is_redeemed 行为必须保持不变
- `is_redeemed` 不受本 PRD 影响
- 如果 `is_redeemed` 当前对 NA 保持 nullable boolean / 继续由 validator 拦截，则该行为必须保持原样
- 本 PRD 不得把 `is_redeemed` 的缺失值静默填成 `False`

#### FR-4: is_st coverage 问题必须继续可观测
- `missing_is_st_row_count`、`missing_is_st_ratio` 必须继续出现在 audit 报告中
- `is_st` 的 fill-`False` 仅用于满足 Stage-F core validator contract，不得抹掉 Stage-D 对 source coverage gap 的观测能力
- 如果未来 is_st source coverage 大幅下降，必须仍能从 audit artifact 中看出

#### FR-5: 修复的 blast radius 必须受限在 core-validator normalization 层
- 修复应落在 `ams/validators/cb_data_validator.py` 的 **core-validator normalization contract** 范围内
- 不得扩展到 ETL 上游 join 逻辑、audit summary 生成逻辑或 validator schema 全量重构

### 2.2 Non-Functional Requirements
- 修复必须符合 field-governed architecture：field-specific 语义必须显式表达
- 不得把 `is_st` 业务语义藏进共享 helper 的全局副作用
- 必须最小化 blast radius，并让 reviewer 能快速验证 `is_st` 与 `is_redeemed` 已被正确分流
- 必须保留 `missing_is_st_row_count` / `missing_is_st_ratio` 作为 coverage witness

### 2.3 User Stories
- 作为 Boss，我不希望 pipeline 因为 0.46% 的 `is_st` 缺口被整条卡死
- 作为 Boss，我也不接受为了放行 pipeline 而偷偷把所有 bool 缺失都默默填默认值
- 作为维护者，我希望 `is_st` 这个特例语义在代码结构上是显式的，而不是埋在通用 helper 里制造隐式副作用

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 选定修复策略
**在 `normalize_core_validator_frame()` / core-validator normalization 层引入 `is_st` 的 field-specific normalization contract，而不是修改共享 `_normalize_contract_bool_series()` 的通用语义。**

### 3.2 为什么必须这样改
原因如下：
1. **共享 helper 当前服务多个字段。** Auditor 已明确指出：若只改共享 helper，就无法同时保证 `is_redeemed` 不受影响。
2. **本次问题是字段特例，不是全局 bool contract 改写。** 真正需要 fill-`False` 的是 `is_st`，不是所有 nullable bool 列。
3. **这才符合 minimal blast radius。** 将特殊语义限定在 `is_st` 的 normalization path，比修改通用 helper 更安全、可审计、可 review。
4. **这与现有 field-governed 架构方向一致。** 字段特定的业务语义应在字段边界被显式声明，而不是由抽象 helper 隐式吞掉。

### 3.3 修复对象与文件边界
本 PRD 允许修改的业务代码主要限于：
- `ams/validators/cb_data_validator.py`

测试主要预期新增/修改于：
- `tests/test_cb_validator_contract_boundaries.py`
- `tests/test_cb_data_validator.py`

### 3.4 预期实现策略
允许的实现方向可以有不同代码形态，但**架构语义必须等价**。可接受方向包括：
1. 保留 `_normalize_contract_bool_series()` 作为通用 helper，不修改其全局语义；
2. 在 `normalize_core_validator_frame()` 中对 `is_st` 增加显式 field-specific 分支；
3. 或新增一个专用 helper（例如 `normalize_is_st_for_core_validator()`），仅由 `is_st` 调用；
4. 然后将处理后的 `is_st` 产出为 non-null `bool`，以满足 `CBDataValidator` schema；
5. `is_redeemed` 继续沿用当前路径与当前语义，不得被顺带改写。

### 3.5 明确禁止的实现方式
以下方式在本 PRD 中 **禁止**：
- 直接把 `_normalize_contract_bool_series()` 改成“只要有 NA 就统一 fill `False`”
- 把 `CBDataValidator` schema 改成 `nullable=True`
- 在 audit summary 生成阶段删掉或篡改 `missing_is_st_row_count` / `missing_is_st_ratio`
- 扩大到 `is_redeemed` 或其它字段的一般化默认值框架改造

### 3.6 Out-of-scope
- 不修上游 JQData is_st source coverage gap
- 不改 redemption 语义
- 不重做 bool normalization framework
- 不扩展为“所有 field 都带 policy 配置”的通用平台化工程

## 4. Acceptance Criteria (BDD 黑盒验收标准)

### 4.1 Acceptance Semantics（验收语义总则）
本 PRD 的验收对象是：

> **Stage-F validator 不再因为 `is_st` 的少量 NA 而失败；同时，`is_st` coverage gap 仍然在 audit 中可观测；且 `is_redeemed` 的既有行为不被顺手改变。**

旧失败签名（本 PRD 必须消除）：
```text
non-nullable series 'is_st' contains null values:
```

本 PRD 通过 iff：
1. 上述旧失败签名在 `is_st` 场景下消失；
2. `missing_is_st_row_count` / `missing_is_st_ratio` 仍保留；
3. `is_redeemed` 的 NA 语义未被静默改写为默认 `False`。

- **Scenario 1: is_st NA no longer blocks Stage-F core validation**
  - **Given** 一份 canonical core DataFrame 中 `is_st` 存在少量 NA，且该缺口来自已记录的 source coverage gap
  - **When** pipeline 进入 Stage-F core validator normalization + schema validation
  - **Then** validator 不再报出旧失败签名：

```text
non-nullable series 'is_st' contains null values:
```

- **Scenario 2: is_st coverage witness remains visible after the fix**
  - **Given** 修复后的代码跑完一次 ETL audit
  - **When** audit report 被生成
  - **Then** `missing_is_st_row_count` 和 `missing_is_st_ratio` 仍必须出现在报告中
  - **And Then** 它们必须继续反映真实的 source coverage gap，而不是被 normalization 吞掉

- **Scenario 3: is_redeemed semantics remain unchanged**
  - **Given** 一份 canonical core DataFrame 中 `is_redeemed` 存在 NA
  - **When** Stage-F 执行本 PRD 修复后的 normalization path
  - **Then** 系统不得因为本 PRD 顺手把 `is_redeemed` 的 NA 静默填成 `False`
  - **And Then** `is_redeemed` 的既有 validator-facing 行为必须保持与修复前一致

- **Scenario 4: the fix is structurally field-specific rather than a global bool side effect**
  - **Given** reviewer 检查修复后的代码路径
  - **When** 对比 `is_st` 与 `is_redeemed` 的 normalization 入口
  - **Then** 必须能清楚看出 `is_st` 的 fill-`False` 是显式 field-specific contract
  - **And Then** 不能是修改共享 `_normalize_contract_bool_series()` 全局语义后产生的隐式副作用

### 4.2 Verification Outcome Matrix (验收结果矩阵)
- **PASS**：`is_st` 的旧 schema failure 消失 + `missing_is_st_*` 指标保留 + `is_redeemed` 未被静默 fill `False`
- **FAIL-A**：`is_st` 旧 schema failure 仍在
- **FAIL-B**：`is_st` 旧 schema failure 消失，但 `missing_is_st_*` 指标被移除或失真
- **FAIL-C**：修复虽放行 `is_st`，但同时把 `is_redeemed` 的 NA 也静默默认化了
- **FAIL-D**：代码结构仍依赖修改共享 helper 全局语义，无法证明 blast radius 被限制在 `is_st`

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 核心质量风险
- 以“修复 `is_st`”为名，实际把通用 bool normalization contract 改坏
- `is_st` coverage gap 被 Stage-F 默认化后失去可观测性
- `is_redeemed` 被无意间语义漂移

### 5.2 Test Strategy
- **单元测试**：验证 `is_st` 在 field-specific normalization path 下，NA 会被转成 non-null bool `False`
- **回归测试**：验证 `is_redeemed` 在存在 NA 时，行为与修复前一致，不会被本 PRD 静默默认化
- **集成测试**：构造带 `is_st` NA 的 canonical core DataFrame，经过 Stage-F 后不再触发旧 schema failure
- **Audit witness test**：验证 `missing_is_st_row_count` / `missing_is_st_ratio` 仍存在于 final report / audit artifact 中
- **结构性测试**：优先验证 `normalize_core_validator_frame()` 层面的 field split，而不是只测共享 helper 的全局返回值

### 5.3 Quality Goal
- 消除 `ISSUE-1223` 对应的旧 validator schema failure 签名
- 保持 `is_st` coverage 问题可观测
- 明确把修复限制在 `is_st` 的 field-specific contract
- 不引入 `is_redeemed` 的副作用

## 6. Framework Modifications (框架防篡改声明)
- None

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 初稿把修复落点写成“修改共享 `_normalize_contract_bool_series()`，让 `is_st` NA 填 `False`”
  - 问题：与“`is_redeemed` 行为保持不变”的要求冲突
  - Auditor reject 原因：共享 helper 路径存在 hidden blast radius

- **v2.0**: 按 Auditor reject 理由重写为 field-specific normalization contract
  - 决策：不改共享 helper 的全局语义
  - 决策：把 `is_st` 的 fill-`False` 限定在 `normalize_core_validator_frame()` / dedicated `is_st` normalization path
  - 保留：`missing_is_st_row_count` / `missing_is_st_ratio` 作为 coverage witness
  - 保留：`is_redeemed` 现有语义不变

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **旧 schema failure 签名（本 PRD 必须消除的精确错误文本）**: 
```text
non-nullable series 'is_st' contains null values:
```
