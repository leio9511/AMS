---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Field Governed CB ETL Refactor

## 1. Context & Problem (业务背景与核心痛点)
AMS 当前的可转债 ETL / audit 管道存在两个已经被真实审计暴露的问题，但它们并不是两个彼此孤立的 bug，而是同一个架构问题的不同症状。

### 1.1 已确认问题 A：JQData 路径的本地处理逻辑污染了 audit 结论
- `get_price()` 会返回“全量 ticker × 日期面板”，即使某只债在窗口内没有有效交易，也会返回带有 `ticker/date` 但 OHLCV 全为空的行。
- 当前 pipeline 没有在进入 supportability / validator / coverage 统计前先剔除这些无效价格空行。
- 导致：
  - `close` 非空 schema 校验失败；
  - `premium_rate` coverage 分母被放大；
  - `redemption` coverage 分母被放大；
  - audit 把本地处理口径问题误报为 source gap。

### 1.2 已确认问题 B：TuShare 的 premium 慢字段阻塞了主 ETL
- `cb_basic` / `cb_daily` / ST 主路径可用。
- 真正卡住的是 `cb_price_chg`：它是慢字段、限流字段、权限敏感字段。
- 当前实现把它以内联方式绑进主链路，并逐债调用，现有权限下会立刻触发严重限流。
- 同时 TuShare 不直接给成品 `premium_rate`，还需要依赖转股价历史和正股价格计算，并处理 stub / 空值 fallback。

### 1.3 真正的根因
这两个问题表面上来自不同 provider，本质上都说明：

> **当前 CB ETL 没有做到 field-governed architecture（按字段分层治理）。**

更具体地说，目前系统缺少：
- 明确的 core field / enrichment field 边界；
- 明确的 active-universe contract；
- 明确的 provider adapter / orchestration / validator / promotion 分层；
- 明确且可机器判别的 audit schema；
- 对慢字段的独立编排、缓存、续跑、互斥治理。

### 1.4 本 PRD 的目标
本 PRD 不是写一个“更复杂的 provider”，而是要把 CB ETL 改造成：
- **主字段快路径（core path）稳定、可审计、可 promotion 判断**；
- **增强字段慢路径（enrichment path）可降级、可缓存、可续跑、可单独统计**；
- **audit 能明确区分：source gap、logic bug、rate limit、permission degradation、promotion blocked**；
- **为后续路线图（ISSUE-1212）保留扩展点，但不在本次 scope 内实现双源自动补洞 / 智能路由 / 全历史平台 / 通用 feature store。**

---

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements

#### FR-1: 建立字段分层治理（Field Registry Semantics）
系统必须把 CB 字段分成两层：

**Core Fields（主字段 / 快路径）**
- `ticker`
- `date`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `underlying_ticker`
- `is_st`
- `is_redeemed`

**Enrichment Fields（增强字段 / 慢路径）**
- `premium_rate`
- `double_low`
- `convert_price` / conversion-price provenance

并要求这些字段的：
- 主源 / 备源语义
- validator 语义
- promotion gate 语义
- degraded 语义
都在硬契约中可表达。

#### FR-2: JQData 路径必须先收缩有效交易 universe
- 在进入 supportability / premium / redemption / validator 前，必须先过滤窗口内 OHLCV 全空行。
- 后续所有 coverage / validator / blocker 统计必须基于有效交易 universe，而不是 provider 返回的原始全量面板。

#### FR-3: JQData premium 必须优先复用 provider 已提供的日级结果
- 若 `CONBOND_DAILY_CONVERT` 已提供 `convert_price` 与 `convert_premium_rate`，则必须优先直接使用。
- 不允许为了“统一 provider 算法”而放弃 provider 已给出的日级 premium 结果。

#### FR-4: TuShare premium 慢字段必须移出 provider，进入独立 orchestration 层
- `cb_price_chg` 相关的 rate-limit / batching / retry / cache / resume / lock / fallback，不得再压进 provider adapter 本身。
- TuShare provider 只能做 source adapter，不得演化成 God Object。

#### FR-5: Audit 报告必须 machine-readable 且 schema-deterministic
- audit 顶层结构、各 summary 对象、blocker/finding 对象、枚举值、诊断语义必须全部写死。
- 不允许 coder 自由发挥命名、字段、异常分类。

#### FR-6: Audit 与 Promotion 的 gate 必须语义分离
- audit 可以接受 core success + enrichment degraded 的诊断结果；
- promotion 是否允许继续，必须由显式规则控制；
- 不允许把 enrichment 缺失一律表述为“主链路失败”。

#### FR-7: TuShare enrichment 必须具备 deterministic 的续跑与互斥规则
- 同一窗口 / 同一 provider 的 enrichment 运行必须有锁；
- run-state 必须可恢复；
- 并发启动必须有明确 fail-fast 规则；
- stale lock 必须有明确判定与恢复规则。

### 2.2 Non-Functional Requirements
- 相同 provider、相同日期窗口、多次运行的 coverage 口径必须一致。
- 失败语义必须可审计，不允许靠日志文案推理真实状态。
- provider adapter 层必须保持薄，不允许承担 workflow orchestration 的职责。
- 设计必须为后续路线图（ISSUE-1212）留好扩展边界，但不得把那些平台化能力提前硬塞进本次实现。

### 2.3 User Stories
- 作为 Boss，我希望 audit 能直接告诉我 blocker 是数据源问题、权限问题、限流问题，还是我方逻辑问题。
- 作为研究/回测使用者，我希望主行情数据先可靠，再单独看 premium 字段是否降级。
- 作为维护者，我希望慢字段的治理是独立可续跑的，不会拖垮主链路。

---

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 目标架构：六层分离
本 PRD 采用轻量版业界最佳实践，模块职责必须分成以下六层：

1. **Security Master / Instrument Master**
   - 负责 canonical ticker、provider ticker mapping、underlying mapping、基础日期语义。
2. **Source Adapters（薄适配层）**
   - `JQDataAdapter`
   - `TuShareAdapter`
   - 只负责 provider 调用 + 最基础 normalize。
3. **Core Pipeline**
   - 构建有效交易 universe、supportability、ST、redemption 主路径。
4. **Enrichment Orchestrator**
   - 负责 premium / convert-price 慢字段编排、限流、缓存、续跑、互斥。
5. **Canonical Transform / Field Registry**
   - 负责统一字段契约、coverage 分母、derived field 计算。
6. **Audit / Promotion Gate**
   - 负责 machine-readable audit、validator 分层、promotion decision。

### 3.2 Adapter 与 Orchestrator 的硬边界

#### 3.2.1 Source Adapter 允许做的事
Adapter 只允许做：
- provider API 调用；
- provider 原始字段 rename / normalize；
- provider 原始异常翻译为统一 provider error。

#### 3.2.2 Source Adapter 禁止做的事
Adapter 禁止做：
- 调度；
- 长流程重试编排；
- run-state 持久化；
- 锁；
- cache manager；
- promotion 决策；
- 跨 provider source precedence 决策。

#### 3.2.3 Enrichment Orchestrator 负责的事
独立 orchestration 层负责：
- premium enrichment batching
- deterministic retry/backoff
- cache read/write
- run-state 管理
- lock / reentry control
- resume
- fallback sequencing
- degraded / blocked / failed 语义分类

### 3.3 Universe Contract（核心宇宙定义）

#### 3.3.1 Active Price Row
当且仅当以下 5 个字段全部非空，该行定义为 **Active Price Row**：
- `open`
- `high`
- `low`
- `close`
- `volume`

#### 3.3.2 Core Universe
Core Universe = 窗口内所有 Active Price Row 的集合。

#### 3.3.3 Active Bond Universe
Active Bond Universe = 在 Core Universe 中至少拥有 1 行 Active Price Row 的债券集合。

#### 3.3.4 Enrichment Target Universe
Enrichment Target Universe = Core Universe 中满足以下条件的行：
- `supportability_bucket == "supportable"`
- `underlying_ticker` 非空
- provider 在该字段语义上允许尝试 enrichment

#### 3.3.5 统计分母硬规则
- `premium_rate` coverage 的分母只能是 Enrichment Target Universe。
- `redemption` coverage 的分母只能是 Core Universe 中需要 redemption 语义的 supportable 行。
- 不允许再使用“原始 provider 面板全量行”或“全历史 supportable universe”作为分母。

### 3.4 JQData 路径策略
1. `get_price()` 返回后，先执行 Active Price Row Filter。
2. 过滤后的数据才允许进入 supportability / validator / coverage 统计。
3. `CONBOND_DAILY_CONVERT` 作为 premium 主源：
   - 直接读取 `convert_price`
   - 直接读取 `convert_premium_rate`
4. `double_low` 基于 canonical `close + premium_rate * 100` 计算。
5. JQData 路径中若仍出现 premium coverage 大面积缺失，应优先判为：
   - universe definition 问题；
   - 统计口径问题；
   - provider source gap；
   不允许默认归因为 source gap。

### 3.5 TuShare 路径策略
1. TuShare Core Path：
   - `cb_basic`
   - `cb_daily`
   - underlying mapping
   - ST
   - redemption/delist
2. TuShare Enrichment Path：
   - `cb_price_chg` 读取
   - conversion price normalization
   - `premium_rate` 计算
   - `double_low` 计算
3. TuShare enrichment orchestration 必须是独立模块，不属于 provider adapter。
4. TuShare fallback 顺序必须固定：
   1. latest non-null `convertprice_aft`
   2. `convert_price_initial`
   3. `cb_basic.conv_price`
   4. mark enrichment missing（不得伪造默认值）

### 3.6 Validator Contract

#### 3.6.1 Core Validator
Core Validator 只在 Core Universe 上执行，检查：
- `ticker` 非空
- `date` 非空
- `close > 0`
- `is_st` 非空
- `is_redeemed` 非空

Core Validator 不得因为窗口外无交易空行失败，因为这些行在 validator 前必须已被移除。

#### 3.6.2 Enrichment Validator
Enrichment Validator 只在 Enrichment Target Universe 上执行，检查：
- `premium_rate` 缺失率
- `double_low` 是否可由 canonical 公式重现
- degradation 分类是否正确

#### 3.6.3 Promotion Gate
对于当前 AMS canonical dataset，promotion 必须在以下任一条件触发时被 BLOCKED：
- `core_path_status != PASS`
- `core_validator_status != PASS`
- `premium_rate` 列缺失
- `double_low` 列缺失
- `premium_missing_ratio_against_active_universe > 0.05`
- `rate_limited_enrichment == true`
- `permission_degraded_enrichment == true`

### 3.7 TuShare Enrichment Concurrency / Reentry Contract

#### 3.7.1 Lock Path
同一 provider + 同一窗口的锁文件路径必须固定为：
`cache/tushare_premium_runs/<start_date>_<end_date>.lock`

#### 3.7.2 Lock Owner Contract
lock file 必须记录：
- `owner_pid`
- `owner_hostname`
- `created_at`
- `run_state_path`

#### 3.7.3 Reentry Rule
- 若同窗口已有 active lock，则第二个 run 必须 **fail fast**，不得并发接管。
- 第二个 run 的精确错误语义必须为：`CONCURRENT_RUN_BLOCKED`

#### 3.7.4 Stale Lock Rule
若 lock file 存在，但满足以下任一条件，则允许视为 stale：
- `owner_pid` 不存在；
- `created_at` 距今超过 6 小时，且 run-state 未在最近 30 分钟内更新。

#### 3.7.5 Crash Recovery Rule
- stale lock 被接管前，必须保留原 run-state 文件；
- 新 run 只能从 `pending_tickers` 继续，不得删除已完成结果；
- 不允许静默从头重跑并覆盖已有 cache。

### 3.8 TuShare Enrichment State Model
允许的 run-state 仅有：
- `PENDING`
- `RUNNING`
- `RATE_LIMITED`
- `PARTIAL_SUCCESS`
- `COMPLETED`
- `FAILED`

允许的状态转移仅有：
- `PENDING -> RUNNING`
- `RUNNING -> COMPLETED`
- `RUNNING -> PARTIAL_SUCCESS`
- `RUNNING -> RATE_LIMITED`
- `RUNNING -> FAILED`
- `RATE_LIMITED -> RUNNING`
- `PARTIAL_SUCCESS -> RUNNING`

不允许跳过这些状态，也不允许用异常吞掉状态更新。

### 3.9 Rollback / Recovery Contract
- 本 PRD 不授权通过手工删除 canonical 数据集来回滚。
- enrichment run-state / cache 写入失败，不得污染 canonical dataset。
- promotion 仍必须保留现有 `.tmp` / `.bak` / rollback 保护语义。
- audit schema 构建失败时，canonical dataset 保持不变，audit 以 `FAILED` 退出。

### 3.10 Scope Boundary
本 PRD 只覆盖：
- field-governed 边界
- JQData active-universe / coverage / validator 修复
- TuShare premium orchestration 解耦
- audit schema determinism
- promotion gate determinism

本 PRD 明确不覆盖（已转 ISSUE-1212）：
- 双源自动补洞
- provider 智能路由
- 全历史重建平台
- 通用 feature store 化

### 3.11 目标模块范围
允许修改：
- `/root/projects/AMS/etl/cb_etl_pipeline.py`
- `/root/projects/AMS/etl/jqdata_provider.py`
- `/root/projects/AMS/etl/tushare_provider.py`
- `/root/projects/AMS/etl/cb_etl_runner.py`
- `/root/projects/AMS/ams/validators/cb_data_validator.py`
- 新增 enrichment orchestration / state-store / audit-schema 相关模块
- 对应 tests / fixtures / audit verification code

---

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: JQData 空价格行不会污染 Core Universe**
  - **Given** 使用 JQData 跑 2025-11-01 ~ 2025-11-30 的 CB audit
  - **When** pipeline 构建 Core Universe
  - **Then** OHLCV 全空行不得进入 Core Universe
  - **And** Core Validator 不得因这些行触发 `close` 非空失败

- **Scenario 2: JQData premium coverage 使用正确分母**
  - **Given** JQData `CONBOND_DAILY_CONVERT` 对窗口内活跃债提供 premium 数据
  - **When** audit 计算 premium coverage
  - **Then** `premium_missing_ratio_against_active_universe` 的分母必须是 Enrichment Target Universe
  - **And** audit 不得把历史无交易债误算为 premium 缺失

- **Scenario 3: TuShare 主链路不会被 `cb_price_chg` 内联拖死**
  - **Given** 使用 TuShare 跑 CB audit
  - **When** 主 daily/basic/ST path 成功但 premium enrichment 遇到 rate-limit
  - **Then** audit 必须报告 enrichment degradation
  - **And** 不得把它表述为主采集失败

- **Scenario 4: TuShare enrichment 具备确定性的续跑行为**
  - **Given** `cb_price_chg` 接口触发限流
  - **When** enrichment run 被中断并稍后恢复
  - **Then** 已完成 ticker 结果必须被复用
  - **And** 未完成 ticker 必须保留在 `pending_tickers`
  - **And** run-state 必须按契约进入 `RATE_LIMITED` 或 `PARTIAL_SUCCESS`

- **Scenario 5: 并发运行被明确阻止**
  - **Given** 同一 provider + 同一窗口已有 active enrichment lock
  - **When** 第二个 run 被启动
  - **Then** 第二个 run 必须 fail fast
  - **And** 失败语义必须是 `CONCURRENT_RUN_BLOCKED`

- **Scenario 6: Audit 与 Promotion 不再混淆**
  - **Given** Core Path 成功但 enrichment 不满足 canonical promotion gate
  - **When** 运行 audit 与 promotion
  - **Then** audit 可以报告 enrichment degradation
  - **And** promotion 必须被 BLOCKED
  - **And** 不允许将该情况错误表述为主采集失败

---

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 Core Quality Risk
最大风险不是单个 API 调不通，而是：
- 错误的 universe 定义污染整份 audit；
- provider adapter 被写成 God Object；
- audit schema 不够硬，导致 coder 脑补诊断语义；
- 并发 / 续跑规则不清，导致状态文件互相踩踏。

### 5.2 Testing Strategy
1. **Adapter unit tests**
   - 验证 adapter 只做 source normalize，不承担 orchestration 逻辑。
2. **Core pipeline tests**
   - 验证 all-null OHLCV row 过滤
   - 验证 Core Universe / Enrichment Target Universe 分母构建
3. **Enrichment orchestration tests**
   - 验证 batching / retry / backoff / resume / stale lock / fail-fast reentry
4. **Audit schema regression tests**
   - 验证所有 summary / blockers / findings 的 exact keys / exact enums
5. **Live smoke tests**
   - 小窗口真实 JQData / TuShare smoke
   - Nov 2025 audit before/after 对比

### 5.3 Mocking Guidance
必须 mock / fixture 的依赖：
- JQData `get_price` 全量面板 + NaN 行
- JQData `CONBOND_DAILY_CONVERT` 日级 premium 数据
- TuShare `cb_price_chg` rate-limit 响应
- TuShare stub rows / partial cache / resume-state / stale lock

### 5.4 Quality Goal
修复完成后，AMS 必须得到：
- 可信的 active-universe 定义；
- 可信的 premium coverage 统计；
- 独立的 TuShare premium orchestration；
- 机器可判别的 audit / promotion 语义；
- coder 没有空间在关键诊断 contract 上自由发挥。

---

## 6. Framework Modifications (框架防篡改声明)
- 本 PRD 不授权修改 OpenClaw / leio-sdlc 核心框架。
- 仅授权修改 AMS 项目内与 CB ETL / audit 直接相关的 adapter、pipeline、orchestrator、validator、tests。

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]**
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 首版把 JQData universe 问题与 TuShare premium 慢字段问题合并为 field-governed ETL 方向，但 contract 不够硬。
- **v2.0 Rejection**: 补了一部分 hardcoded schema，但把 rate-limit/cache/resume/state-machine 责任错误地压进 provider，且 schema 仍未完整冻结。
- **v3.0 Revision Rationale**:
  - 改为薄 adapter + 独立 enrichment orchestration；
  - 全量冻结 audit / findings / summary / enum contract；
  - 补并发 / stale lock / reentry / rollback 规则；
  - 明确把平台化路线挪到 ISSUE-1212，避免 scope 污染当前纠偏 sprint。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 凡是本需求涉及需要精确输出的字符串、schema key、enum、状态名、错误语义、路径契约，必须且只能从本章节复制，禁止改写。

### 7.1 Exact Enum Values
```text
PASS
FAIL
NOT_RUN
DEGRADED
PENDING
RUNNING
RATE_LIMITED
PARTIAL_SUCCESS
COMPLETED
FAILED
FAIL_ROOT_BLOCKER
FAIL_SECONDARY_ONLY
CONCURRENT_RUN_BLOCKED
SOURCE_AUTH_FAILURE
PRICE_SOURCE_UNREADABLE
SUPPORTABILITY_REGRESSION
PREMIUM_SOURCE_TRUNCATION
PREMIUM_RATE_MISSING_BROAD_COVERAGE
RATE_LIMITED_ENRICHMENT
PERMISSION_DEGRADED_ENRICHMENT
IS_ST_SOURCE_GAP
REDEMPTION_SOURCE_GAP
VALIDATOR_SCHEMA_FAILURE
VALIDATOR_SEMANTIC_FAILURE
MISSING_PREMIUM_RATE_ROWS
MISSING_REDEMPTION_ROWS
MISSING_IS_ST_ROWS
MISSING_UNDERLYING_TICKER_ROWS
EXCLUSION_ONLY_WINDOW
```

### 7.2 Exact Top-Level Audit Schema
```json
{
  "execution_mode": "audit",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "final_status": "PASS|FAIL_ROOT_BLOCKER|FAIL_SECONDARY_ONLY",
  "core_path_status": "PASS|FAIL|NOT_RUN",
  "enrichment_path_status": "PASS|FAIL|NOT_RUN|DEGRADED",
  "non_promotion_disclaimer": "[AUDIT-ONLY] This run is diagnostic only. No canonical dataset promotion was attempted.",
  "active_universe_summary": {},
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

### 7.3 Exact `active_universe_summary` Schema
```json
{
  "core_price_row_count_before_filter": 0,
  "core_price_row_count_after_filter": 0,
  "all_null_ohlcv_row_count_filtered": 0,
  "core_universe_row_count": 0,
  "core_universe_unique_bond_count": 0,
  "active_bond_universe_count": 0,
  "enrichment_target_row_count": 0,
  "enrichment_target_unique_bond_count": 0
}
```

### 7.4 Exact `source_coverage` Schema
```json
{
  "status": "PASS|FAIL|NOT_RUN",
  "failure_type": "NONE|SOURCE_AUTH_FAILURE|PRICE_SOURCE_UNREADABLE",
  "message": "",
  "basic_info_row_count": 0,
  "all_bond_security_count": 0,
  "price_row_count": 0,
  "price_unique_bond_count": 0,
  "premium_source_row_count": 0,
  "premium_source_unique_bond_count": 0,
  "is_st_source_row_count": 0,
  "is_st_source_unique_underlying_count": 0,
  "redemption_source_row_count": 0,
  "redemption_source_unique_bond_count": 0
}
```

### 7.5 Exact `supportability_summary` Schema
```json
{
  "status": "PASS|FAIL|NOT_RUN",
  "failure_type": "NONE|SUPPORTABILITY_REGRESSION",
  "message": "",
  "supportable_row_count": 0,
  "supportable_unique_bond_count": 0,
  "outside_basic_info_row_count": 0,
  "outside_basic_info_unique_bond_count": 0,
  "missing_company_code_legacy_row_count": 0,
  "missing_company_code_legacy_unique_bond_count": 0,
  "unexpected_contract_regression_row_count": 0,
  "unexpected_contract_regression_unique_bond_count": 0,
  "missing_underlying_row_count": 0,
  "missing_underlying_unique_bond_count": 0
}
```

### 7.6 Exact `premium_join_summary` Schema
```json
{
  "status": "PASS|FAIL|NOT_RUN|DEGRADED",
  "failure_type": "NONE|PREMIUM_SOURCE_TRUNCATION|PREMIUM_RATE_MISSING_BROAD_COVERAGE|RATE_LIMITED_ENRICHMENT|PERMISSION_DEGRADED_ENRICHMENT",
  "message": "",
  "premium_joined_row_count": 0,
  "premium_joined_unique_bond_count": 0,
  "missing_premium_row_count": 0,
  "missing_premium_unique_bond_count": 0,
  "missing_premium_ratio": 0.0,
  "premium_missing_ratio_against_active_universe": 0.0,
  "rate_limited_enrichment": false,
  "permission_degraded_enrichment": false
}
```

### 7.7 Exact `is_st_join_summary` Schema
```json
{
  "status": "PASS|FAIL|NOT_RUN|DEGRADED",
  "failure_type": "NONE|IS_ST_SOURCE_GAP|PERMISSION_DEGRADED_ENRICHMENT",
  "message": "",
  "is_st_joined_row_count": 0,
  "is_st_joined_unique_bond_count": 0,
  "missing_is_st_row_count": 0,
  "missing_is_st_unique_bond_count": 0,
  "missing_is_st_ratio": 0.0
}
```

### 7.8 Exact `redemption_summary` Schema
```json
{
  "status": "PASS|FAIL|NOT_RUN|DEGRADED",
  "failure_type": "NONE|REDEMPTION_SOURCE_GAP|PERMISSION_DEGRADED_ENRICHMENT",
  "message": "",
  "redemption_joined_row_count": 0,
  "redemption_joined_unique_bond_count": 0,
  "missing_redemption_row_count": 0,
  "missing_redemption_unique_bond_count": 0,
  "missing_redemption_ratio": 0.0
}
```

### 7.9 Exact `validator_summary` Schema
```json
{
  "status": "PASS|FAIL|NOT_RUN|DEGRADED",
  "failure_type": "NONE|VALIDATOR_SCHEMA_FAILURE|VALIDATOR_SEMANTIC_FAILURE",
  "message": "",
  "core_validator_status": "PASS|FAIL|NOT_RUN",
  "core_validator_message": "",
  "enrichment_validator_status": "PASS|FAIL|NOT_RUN|DEGRADED",
  "enrichment_validator_message": "",
  "promotion_gate_status": "PASS|BLOCKED|NOT_RUN",
  "promotion_gate_message": ""
}
```

### 7.10 Exact `root_blockers[]` Item Schema
```json
{
  "type": "SOURCE_AUTH_FAILURE|PRICE_SOURCE_UNREADABLE|SUPPORTABILITY_REGRESSION|PREMIUM_SOURCE_TRUNCATION|PREMIUM_RATE_MISSING_BROAD_COVERAGE|RATE_LIMITED_ENRICHMENT|PERMISSION_DEGRADED_ENRICHMENT|IS_ST_SOURCE_GAP|REDEMPTION_SOURCE_GAP|VALIDATOR_SCHEMA_FAILURE|VALIDATOR_SEMANTIC_FAILURE|CONCURRENT_RUN_BLOCKED",
  "stage": "A|B|C|D|E|F|ORCH",
  "trigger": "",
  "evidence": {}
}
```

### 7.11 Exact `secondary_findings[]` Item Schema
```json
{
  "type": "MISSING_PREMIUM_RATE_ROWS|MISSING_REDEMPTION_ROWS|MISSING_IS_ST_ROWS|MISSING_UNDERLYING_TICKER_ROWS|EXCLUSION_ONLY_WINDOW",
  "stage": "B|C|D|E",
  "trigger": "",
  "evidence": {}
}
```

### 7.12 Exact TuShare Run-State Schema
```json
{
  "run_status": "PENDING|RUNNING|RATE_LIMITED|PARTIAL_SUCCESS|COMPLETED|FAILED",
  "provider": "tushare",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "sorted_tickers": [],
  "completed_tickers": [],
  "pending_tickers": [],
  "failed_tickers": [],
  "last_processed_ticker": "",
  "sleep_seconds_between_calls": 15,
  "last_attempt_at": "ISO8601",
  "next_eligible_at": "ISO8601"
}
```

### 7.13 Exact Lock File Schema
```json
{
  "owner_pid": 0,
  "owner_hostname": "",
  "created_at": "ISO8601",
  "run_state_path": ""
}
```

### 7.14 Exact Cache / State / Lock Paths
```text
cache/tushare_cb_price_chg/<full_ticker>.json
cache/tushare_premium_runs/<start_date>_<end_date>.json
cache/tushare_premium_runs/<start_date>_<end_date>.lock
```

### 7.15 Exact TuShare Fallback Order
```text
1. latest non-null convertprice_aft
2. convert_price_initial
3. cb_basic.conv_price
4. mark enrichment missing (do not synthesize default premium_rate)
```

### 7.16 Exact Promotion Gate Rule
```text
Promotion MUST be BLOCKED if any of the following is true:
- core_path_status != PASS
- core_validator_status != PASS
- premium_rate column is missing
- double_low column is missing
- enrichment_target_row_count > 0 AND premium_missing_ratio_against_active_universe > 0.05
- rate_limited_enrichment == true
- permission_degraded_enrichment == true
```

### 7.17 Exact Concurrency Error Semantic
```text
CONCURRENT_RUN_BLOCKED
```
