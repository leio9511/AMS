---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Wave 3 Redemption Event Ledger and Shared Derivation

## 1. Context & Problem (业务背景与核心痛点)
Wave 1（#14）已经完成 redemption semantic split：
- `redeem_risk` = trading-risk window
- `is_redeemed` = terminal/delist state

Wave 2（#15）已经完成 observability / validation alignment：
- metrics / audit / validator 已能明确区分 risk-state 与 terminal-state
- `is_redeemed` 不再冒充 announcement-risk correctness proxy
- split-state、missing evidence、transitional placeholder 已经可观测

但 AMS 还没有真正完成 redeem 问题的“事实层闭环”。当前系统最大的缺口不是字段语义，也不是观测语义，而是：
1. redemption facts 的 authoritative ingress contract 还没有被冻结；
2. post-ingestion 之后谁是唯一事实源（single source of truth）还没有被彻底钉死；
3. stable event identity / revision semantics 还没有被定义成 deterministic contract；
4. daily canonical redemption state 还没有被正式定义成 repo-owned contract；
5. downstream consumers（回测 / 模拟盘 / 未来实盘）还没有一个统一且明确的上游状态合同可以依赖。

如果继续在“provider repeated snapshot / transitional placeholder / ad hoc field propagation”的模式上演化，就会持续暴露在这些风险下：
- provider 不重复发 daily redeem bit 时，状态回退或失真；
- import facts 与 persisted ledger 同时被当成 truth source，形成 split-brain；
- future revision / cancellation / correction 到来时，没有稳定事件身份可以承接；
- canonical projection 在多事件/多 revision 命中同一 bond/date 时没有 deterministic contract；
- updater / consumer integration 只能建立在不稳定的事实上游合同之上。

因此，本问题应被定义为 **Phase 1.5 收尾阶段的 event-ledger completion**：
- 不重写 Wave 1 / Wave 2 已完成的 semantic split 与 observability contract；
- 不一次性做成 fully generalized bitemporal platform；
- 不把 updater orchestration 或 consumer rollout 膨胀进同一个 wave；
- 只做一件事：把 redemption facts 的 authoritative ingress、sole persisted ledger truth、stable event identity、shared derivation、traceability 与 canonical state contract 一次性钉死。

本 PRD 只覆盖 Wave 3：
**authoritative import artifact → sole persisted ledger truth → shared derivation → canonical redemption state contract**。

与本波相邻但不在本波内完成的后续工作：
- Wave 4（#17）：bootstrap / backfill 初始历史 redemption facts
- Wave 5（#18）：canonical state updater / refresh orchestration
- Wave 6（#19）：backtest / sim / future live consumer integration

## 2. Requirements & User Stories (需求定义)
### 2.1 Functional Requirements
1. AMS 必须引入一个 **project-governed redemption fact import artifact**，作为 redemption facts 进入系统的唯一 ingress contract。
2. AMS 必须冻结 `announcement_date` 与 `delisting_date` 的 authoritative ingress contract，明确：
   - authoritative ingress artifact 是什么；
   - fallback 是否允许；
   - 缺失值与无效值如何处理；
   - provenance 如何记录。
3. authoritative ingress artifact 的逻辑默认路径固定为：`data/redemption_event_facts_import.csv`。
4. import artifact 在 ingestion 之后必须失去 truth-source 身份。**导入完成后，downstream derivation 不得再从 import artifact 直接推 daily state；唯一 post-ingestion truth source 必须是 persisted ledger。**
5. AMS 必须引入一个 persisted redemption event ledger，作为唯一 post-ingestion truth source。
6. persisted ledger 必须至少持久化以下精确字段：
   - `event_id`
   - `revision`
   - `is_active_revision`
   - `source_native_event_id`
   - `bond_code`
   - `announcement_date`
   - `delisting_date`
   - `source`
   - `updated_at`
7. AMS 必须定义 stable event identity contract：
   - `event_id` 必须是稳定事件身份；
   - `event_id` 必须在同一现实世界 redemption event 的后续修订中保持不变；
   - `event_id` 的 authority / allocation / validation algorithm 必须由 PRD 明确定义；
   - ingress artifact 只提供 `source_native_event_id` 与原始业务事实，不得直接提供 ledger-owned 的 `event_id` / `revision`。
8. AMS 必须冻结 event identity authority rule：
   - authoritative ingress artifact 必须提供 `source_native_event_id`
   - 对任一 ingress row，`event_id = source + ":" + source_native_event_id`
   - 若 `source_native_event_id` 缺失、为空、或在同一 source 下不稳定，则该 row 不得进入 persisted ledger，且必须进入 trace artifact 的 rejected facts bucket
   - 同一 `source + source_native_event_id` 必须始终映射为同一个 `event_id`
9. AMS 必须冻结 same-event / distinct-event classification rule：
   - 两条 ingress rows 若 `source` 与 `source_native_event_id` 相同，则它们属于同一现实世界事件的不同 revision
   - 两条 ingress rows 若 `source + source_native_event_id` 不同，则它们属于 distinct events，即使 `bond_code`、`announcement_date`、`delisting_date` 恰好相同
10. AMS 必须冻结 revision contract：
   - `revision` 必须是同一 `event_id` 下从 `0` 开始单调递增的整数；
   - 对任一 `event_id`，恰好只能有一个 `is_active_revision=true` 的 revision；
   - canonical state 只能由 active revision 参与投影；
   - 同一 `(event_id, revision)` 不得重复；
   - duplicate / update / correction / revision 的判定规则必须冻结为 deterministic contract。
11. AMS 必须冻结 duplicate / update / correction classification rule：
   - 若 ingress row 经 authority mapping 后，对应的 `(event_id, revision candidate)` 与已存在 active revision 业务字段完全一致，则视为 duplicate，不新增行；
   - 若 `event_id` 相同但业务字段变化，则必须写入新的 `revision = previous_max_revision + 1`，并将旧 active revision 置为 `is_active_revision=false`；
   - 不允许在不升 revision 的情况下覆盖旧 revision 内容；
   - cancellation / correction 若出现，也必须以新 revision 表达，不允许直接删除旧 revision。
12. AMS 必须定义 canonical projection contract：
   - canonical state 的唯一键必须固定；
   - 对每个 `date + bond_code`，行级基数必须固定；
   - 必须定义多 event / 多 revision 命中同一 `date + bond_code` 时的 representative event selection rule；
   - 必须区分“可共存多事件”与“互斥冲突事件”；
   - 对互斥冲突事件，不得静默选择，必须显式记录到 trace / audit surface。
13. AMS 必须定义 coexistence taxonomy：
   - `COEXIST_SAME_RISK_WINDOW`: 多个 distinct active events 对同一 `date + bond_code` 都导出 `redeem_risk=true`，且不存在互斥业务结论；允许共存，但 canonical row 只能保留一个 representative event，trace 必须保留全部 contributing events。
14. AMS 必须定义 conflict taxonomy：
   - `CONFLICT_MULTIPLE_ACTIVE_REVISIONS_FOR_EVENT`: 同一 `event_id` 出现多个 active revision
   - `CONFLICT_MUTUALLY_INCOMPATIBLE_ACTIVE_EVENTS`: 多个 distinct active events 对同一 `date + bond_code` 给出互斥业务结论
   - `CONFLICT_INVALID_REVISION_GRAPH`: revision 链不满足单调递增 / 单 active 规则
15. AMS 必须定义 representative event selection rule：
   - 先仅在 active revisions 范围内选择
   - 若多个 distinct active events 在同一 `date + bond_code` 共存且都有效，则代表事件按以下顺序选择：
     1. 最早 `announcement_date`
     2. 若相同，最新 `updated_at`
     3. 若仍相同，最小字典序 `event_id`
16. AMS 必须定义 canonical row conflict behavior：
   - 对 coexistence case，canonical row 仍然产出，且 `redeem_risk=true`
   - 对 conflict case，canonical row 不得静默产出伪确定结果；必须通过 trace/audit surface 显式标记 `blocked` 或 `conflicted`
17. AMS 必须定义 ingress artifact、ledger artifact、trace artifact、canonical state artifact 的固定 schema、逻辑默认路径、字段类型、null 语义、日期格式、更新语义、冲突语义。
18. AMS 必须用 **persisted ledger 的 active revisions** 推导 daily `redeem_risk`，而不是依赖 provider 每天重复给出 daily bit，也不是继续从 import artifact 直接推导。
19. AMS 必须将 `redeem_risk` 的共享推导逻辑冻结为一个可复用 contract，并要求后续 updater / consumer integration 只能复用该 contract。
20. AMS 必须定义日度 canonical redemption state contract，明确：
   - logical default path
   - required fields
   - date grain
   - unique key
   - row cardinality
   - representative event selection rule
   - conflict vs coexistence rule
   - traceability linkage to persisted ledger
21. AMS 必须规定：回测、模拟盘、未来实盘 consumer 都只能依赖 canonical redemption state contract，而不是直接依赖 raw import facts。
22. AMS 必须支持“provider 只发一次 redemption event，后续多天仍能持续推导正确 daily state”的行为。
23. AMS 必须提供从 daily `redeem_risk=True` 行反向追溯到具体 `(event_id, revision)` ledger 记录的可验证路径。
24. 若未来支持 source cancellation / correction，本波设计必须留出演进接口，但不要求 day-one 完成 fully generalized revision engine。
25. 现有 Wave 1 / Wave 2 contract 必须保持不变：
   - `redeem_risk` 继续表示 trading-risk window；
   - `is_redeemed` 继续表示 terminal/delist state；
   - Wave 2 的 observability contract 不得回退。

### 2.2 Non-Functional Requirements
1. 本波改动必须局限在 ingress / ledger / trace / derivation / canonical state contract 及对应 tests，不得膨胀成 updater orchestration 或 consumer rollout。
2. 本波必须确保 deterministic correctness：相同 ingress artifact、相同 ledger state、相同 target date，必须导出相同 canonical redemption state。
3. 本波必须保持单一真相源：**post-ingestion 之后，import artifact 不得继续参与 daily state truth computation。**
4. 本波必须与 AMS 既有 path-resolver contract 对齐：冻结的是 *logical default paths under resolver contract*，不是 host-coupled absolute paths。
5. 本波必须保持最小存储与最小推导原则，不得提前引入过度复杂的通用事件平台。
6. 本波必须为 #17 / #18 / #19 提供稳定 contract，而不是抢先实现它们的职责。
7. 文档必须同步更新，使 ROADMAP / ARCHITECTURE 能明确说明：
   - ingress artifact
   - persisted ledger
   - trace artifact
   - canonical state
   - stable event identity
   - active revision rule
   - representative event selection rule
   - conflict vs coexistence rule
   - 这些合同的关系与边界。

### 2.3 User Stories
- 作为研究者，我希望系统不依赖 provider 每天重复发送 redeem bit，也能稳定得到每天的 redemption risk state。
- 作为架构维护者，我希望 import 只是入口、ledger 才是唯一 post-ingestion truth source，避免后续演化成 split-brain。
- 作为 Auditor，我希望某一日 `redeem_risk=True` 能被解释到具体的 persisted ledger `event_id + revision`，并知道当日是否存在其他 contributing events。
- 作为后续 Wave 5 / Wave 6 的实现者，我希望上游已经提供稳定 canonical state contract，而不是再回头重新设计事实边界。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Core Design Decision
本波采用如下分层：

```text
authoritative import artifact
  -> validated ingestion
  -> persisted ledger (sole post-ingestion truth)
  -> shared derivation helper
  -> canonical redemption state artifact
  -> downstream consumers (future waves)
```

关键决策：
1. import artifact 是 ingress-only，不是 post-ingestion truth source；
2. persisted ledger 是唯一事实源；
3. canonical redemption state 是给下游消费的 daily contract；
4. updater / rollout 不在本波实现，只依赖本波冻结的 contract。

### 3.2 Executable Checklist (可执行清单)
#### A. Authoritative Import Artifact
1. 定义并实现 authoritative redemption fact import artifact contract。
2. 冻结其 logical default path、schema、null 行为、日期格式。
3. import artifact 只承担 ingress 职责，不承担 post-ingestion derivation truth 职责。

#### B. Persisted Ledger as Sole Truth Source
4. 定义并实现 persisted ledger contract。
5. 冻结 ledger 的 stable event identity contract，明确 `event_id` 的 authority / allocation / validation rule。
6. 冻结 ledger 的 revision contract，明确 revision 递增、active revision 选择、duplicate/update/correction 生效规则。
7. 冻结 ledger 的 update / duplicate / invalid-row behavior。
8. 明确规定 canonical state 只能从 ledger 的 active revisions 推导。

#### C. Shared Derivation Contract
9. 抽取 shared derivation helper，用于从 persisted ledger 的 active revisions 推导 daily `redeem_risk`。
10. 冻结 derivation 规则与 fail-closed 语义。
11. 保证 derivation 输出可 trace 到 `(event_id, revision)`。

#### D. Canonical Redemption State Contract
12. 定义 canonical redemption state artifact 的 logical default path、schema、date grain、唯一键、行级基数、代表事件选择规则、冲突优先级与 traceability linkage。
13. 明确回测 / 模拟盘 / 未来实盘只能依赖 canonical state contract。
14. 不在本波实现 updater scheduling / rollout orchestration。

#### E. Regression / Traceability / Documentation
15. 增加 contract-focused tests：import、ledger、trace、canonical state、provider snapshot independence。
16. 增加 traceability tests，证明 `redeem_risk=True` 可反向定位至 persisted ledger event。
17. 增加冲突场景 tests，覆盖 multi-event / multi-revision 命中同一 `bond_code + date` 的 deterministic projection。
18. 更新文档，明确本波与 #17 / #18 / #19 的边界。

### 3.3 Scope of Code Changes
本波授权修改的目标区域应限定为：
- ingress artifact / persisted ledger / trace / canonical state contract 相关逻辑
- ETL / 领域接线层中的 redemption derivation 相关逻辑
- 与上述 contract 直接相关的 tests / fixtures
- `docs/architecture/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- 必要的小范围 path / contract 注释

本波不授权：
- canonical state updater scheduling
- backtest/live/sim consumer rollout orchestration
- generalized revision engine
- generalized event bus/platform

### 3.4 Required Semantic Contract
#### authoritative import artifact
- 是唯一 ingress contract；
- 负责把 redemption facts 送入系统；
- 不是 post-ingestion truth source。

#### persisted ledger
- 是唯一 post-ingestion truth source；
- 具备 stable event identity 与 revision semantics；
- canonical state 只能从 ledger 的 active revisions 推导。

#### canonical redemption state
- 是从 persisted ledger 的 active revisions 推导出的日度状态产物；
- 必须有固定 path、固定最小字段、固定日期粒度；
- 必须冻结唯一键、行级基数、代表事件选择规则与冲突/覆盖优先级；
- 必须能通过 trace artifact 反向解释到具体 `(event_id, revision)`，并保留 contributing events 证据；
- 必须作为回测/模拟盘/实盘共同依赖的上游 contract，而不是让各 consumer 自己重算 raw facts。

#### `redeem_risk`
- 继续表示 trading-risk window；
- 从 ledger 通过 shared derivation 推导；
- 不再依赖 provider repeated snapshot；
- 不再允许 import artifact 与 ledger 双重参与 post-ingestion truth。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Ingress artifact, persisted ledger, trace artifact, and canonical state artifact all exist with exact contracts**
  - **Given** 一次支持 redemption facts 获取的数据导入运行
  - **When** redemption facts 被接收并处理
  - **Then** AMS 必须生成：ingress artifact、persisted ledger、trace artifact、canonical redemption state artifact
  - **And** 它们都必须满足 PRD Section 7 中冻结的 exact schema/path contract

- **Scenario 2: Post-ingestion derivation depends only on persisted ledger**
  - **Given** 一份已经完成 ingestion 的 ledger
  - **When** 系统生成某日 canonical redemption state
  - **Then** daily state 必须只依赖 persisted ledger
  - **And** import artifact 不得继续作为并行 truth source 参与该次推导

- **Scenario 3: Daily state is derived correctly from redemption facts**
  - **Given** 某转债存在一条 announcement event 和一个后续 delisting date
  - **When** AMS 推导公告日至退市前的 daily state
  - **Then** 该窗口内每日 `redeem_risk=True`
  - **And** 公告前日期 `redeem_risk=False`

- **Scenario 4: Canonical state is consumer-ready without raw fact reconstruction**
  - **Given** 已物化好的 canonical redemption state artifact
  - **When** 下游 consumer 读取该状态
  - **Then** consumer 不应再需要直接重建 raw import facts 才能得到 daily `redeem_risk`
  - **And** canonical state 必须能够作为后续回测/模拟盘/实盘 integration 的上游 contract

- **Scenario 5: A daily risk row is traceable to a persisted ledger event identity**
  - **Given** 某一交易日的某只债被标记为 `redeem_risk=True`
  - **When** 审计该日状态来源
  - **Then** AMS 必须能够指出触发该状态的具体 `(event_id, revision)` ledger 记录
  - **And** 该 traceability 证据必须可通过 trace artifact 的冻结 schema 进行验证

- **Scenario 6: Canonical projection resolves multi-event and multi-revision conflicts deterministically**
  - **Given** 同一 `bond_code + date` 命中多个 event 或多个 revision
  - **When** AMS 生成 canonical redemption state
  - **Then** 输出的行级基数、唯一键与生效 revision 必须满足冻结的 projection contract
  - **And** 同一输入不得产生不稳定或多义的 state 输出

- **Scenario 7: Provider snapshot repetition is not required**
  - **Given** provider 仅提供一次 redemption event
  - **When** 后续多天状态继续生成
  - **Then** AMS 仍必须通过 persisted ledger 正确推导出 daily `redeem_risk`

- **Scenario 8: Existing Wave 1 / Wave 2 semantics remain intact**
  - **Given** Wave 3 落地
  - **When** 检查 strategy / validator / audit / metrics 语义
  - **Then** `redeem_risk` 仍表示 trading-risk window
  - **And** `is_redeemed` 仍表示 terminal/delist state
  - **And** Wave 2 observability contract 不得被破坏

- **Scenario 9: Deterministic correctness holds for the same ingress and target date**
  - **Given** 同一份 ingress artifact、同一份 persisted ledger、同一目标日期
  - **When** 系统生成 canonical redemption state
  - **Then** 输出必须 deterministic
  - **And** 该一致性必须可通过固定 artifact 的外部行为验证

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### 5.1 Core Quality Risk
本波的核心风险是：
- import 与 ledger 双重参与 truth，形成 split-brain；
- stable event identity 不明确，revision/correction 语义无法演进；
- traceability 只停留在口号；
- canonical projection 在多事件/多 revision 下不 deterministic；
- canonical state contract 未真正冻结，导致后续 updater / integration 建在流沙上。

### 5.2 Recommended Test Layers
1. **Ingress artifact contract tests**
   - path
   - schema
   - null behavior
   - date format
2. **Persisted ledger contract tests**
   - stable event identity authority/validation rule
   - revision selection / active revision rule
   - duplicate/update/correction semantics
3. **Shared derivation tests**
   - `announcement_date <= date < delisting_date`
   - invalid date order
   - missing fact handling
4. **Canonical state contract tests**
   - path
   - schema
   - date grain
   - unique key
   - row cardinality
   - conflict priority
   - deterministic outputs
5. **Provider snapshot independence tests**
   - one event persists; many daily states derive correctly
6. **Traceability tests**
   - `redeem_risk=True` row maps back to `(event_id, revision)`
   - trace artifact matches frozen JSON shape
7. **Regression / doc tests**
   - Wave 1 / Wave 2 contracts remain intact
   - docs updated consistently

### 5.3 Mocking Guidance
- Use deterministic fixture import rows / ledger rows / trace rows / state rows
- Do not require real announcement-source E2E for this wave
- Do not use mocks to hide source-of-truth ambiguity
- Future live runtime validation remains contract-readiness only, not full rollout

### 5.4 Quality Goal
Wave 3 完成后，AMS 必须达到：
- redemption facts 已通过 authoritative ingress artifact 进入系统；
- persisted ledger 成为唯一 post-ingestion truth source；
- canonical redemption state 已被正式定义为后续 updater / integration 的上游 contract；
- provider 不重复发 daily bit 时系统仍保持正确；
- redeem 问题的主干事实闭环被正式建立。

## 6. Framework Modifications (框架防篡改声明)
- 无。
- 本 PRD 不授权修改 SDLC framework 脚本。

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]**
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial execution brief created from Issue #16 after Wave 1 (#14) and Wave 2 (#15) completed.
- **Audit Rejection (v1.0)**: Multiple rounds exposed the need to separate ingress, sole ledger truth, canonical state contract, updater orchestration, and consumer rollout.
- **v2.0 Revision Rationale**: This revision freezes Wave 3 at the correct layer: ingress/ledger/trace/state contracts only.

---

## 7. Hardcoded Content (硬编码内容)
### `phase_positioning_statement`
```text
This change is the Phase 1.5 closeout completion step for authoritative redemption ingress, sole persisted ledger truth, shared daily derivation, traceability, and canonical redemption state contract definition. It is not the updater orchestration wave and not the consumer rollout wave.
```

### `required_authoritative_ingress_contract`
```json
{
  "logical_default_path": "data/redemption_event_facts_import.csv",
  "resolver_contract_category": "mutable_research_data",
  "fallback_allowed": false,
  "fallback_precedence": [],
  "null_behavior": "reject_row_and_record_trace"
}
```

### `required_import_artifact_schema`
```json
{
  "logical_default_path": "data/redemption_event_facts_import.csv",
  "format": "csv",
  "columns": {
    "source_native_event_id": "string_non_empty_non_null",
    "bond_code": "string_non_empty_raw_bond_code",
    "announcement_date": "date_iso_yyyy_mm_dd_non_null",
    "delisting_date": "date_iso_yyyy_mm_dd_non_null",
    "source": "string_non_empty_non_null",
    "updated_at": "datetime_iso_utc_non_null"
  },
  "same_event_classification_rule": "same source + same source_native_event_id => same real-world event",
  "distinct_event_classification_rule": "different source_native_event_id => distinct event even if business dates match",
  "null_representation": "empty string is invalid; null facts must be rejected before ledger persistence"
}
```

### `required_persisted_ledger_contract`
```json
{
  "logical_default_path": "data/redemption_event_ledger.csv",
  "resolver_contract_category": "mutable_research_data",
  "format": "csv",
  "columns": {
    "event_id": "string_non_empty_non_null_stable_event_identity",
    "revision": "int_non_negative_non_null",
    "is_active_revision": "bool_non_null",
    "source_native_event_id": "string_non_empty_non_null",
    "bond_code": "string_non_empty_raw_bond_code",
    "announcement_date": "date_iso_yyyy_mm_dd_non_null",
    "delisting_date": "date_iso_yyyy_mm_dd_non_null",
    "source": "string_non_empty_non_null",
    "updated_at": "datetime_iso_utc_non_null"
  },
  "primary_key": ["event_id", "revision"],
  "event_id_authority_rule": "event_id = source + ':' + source_native_event_id",
  "active_revision_rule": "for each event_id, exactly one revision must have is_active_revision=true",
  "invalid_date_order_behavior": "reject_row_and_record_trace",
  "duplicate_same_identity_behavior": "idempotent_no_duplicate_row",
  "newer_revision_behavior": "append_new_revision_and_flip_previous_active_revision_to_false"
}
```

### `required_trace_artifact_schema`
```json
{
  "logical_default_path": "reports/redemption_event_trace.json",
  "resolver_contract_category": "runtime_output",
  "format": "json",
  "top_level_keys": [
    "ingress_artifact_path",
    "ledger_artifact_path",
    "trace_generated_at",
    "accepted_fact_count",
    "rejected_fact_count",
    "updated_revision_count",
    "rejected_facts",
    "conflict_rows",
    "daily_state_trace_examples"
  ],
  "rejected_fact_item": {
    "source_native_event_id": "string",
    "bond_code": "string",
    "reason": "MISSING_ANNOUNCEMENT_DATE|MISSING_DELISTING_DATE|INVALID_DATE_ORDER|MISSING_SOURCE_NATIVE_EVENT_ID",
    "source": "string"
  },
  "conflict_row_item": {
    "date": "date_iso_yyyy_mm_dd",
    "bond_code": "string",
    "conflict_type": "CONFLICT_MULTIPLE_ACTIVE_REVISIONS_FOR_EVENT|CONFLICT_MUTUALLY_INCOMPATIBLE_ACTIVE_EVENTS|CONFLICT_INVALID_REVISION_GRAPH",
    "contributing_event_ids": ["string"],
    "resolution_mode": "blocked|representative_selected",
    "representative_event_id": "string_or_null",
    "representative_revision": "int_or_null"
  },
  "daily_state_trace_example_item": {
    "date": "date_iso_yyyy_mm_dd",
    "bond_code": "string",
    "redeem_risk": true,
    "representative_event_id": "string",
    "representative_revision": 0,
    "contributing_event_ids": ["string"],
    "announcement_date": "date_iso_yyyy_mm_dd",
    "delisting_date": "date_iso_yyyy_mm_dd"
  }
}
```

### `required_canonical_state_contract`
```json
{
  "logical_default_path": "data/canonical_redemption_state.csv",
  "resolver_contract_category": "mutable_research_data",
  "format": "csv",
  "date_grain": "daily",
  "unique_key": ["date", "bond_code"],
  "row_cardinality_rule": "exactly one row per date+bond_code",
  "coexistence_rule": "multiple distinct active events may co-exist if they all imply redeem_risk=true for the same date+bond_code",
  "conflict_rule": "mutually incompatible active events or revision states must not be silently collapsed; they must be emitted as conflict findings/trace evidence",
  "representative_event_selection_rule": "choose earliest announcement_date; if tied choose latest updated_at; if still tied choose lexical min event_id",
  "required_fields": [
    "date",
    "bond_code",
    "redeem_risk",
    "representative_event_id",
    "representative_revision",
    "contributing_event_count"
  ],
  "traceability_rule": "representative_event_id+representative_revision must map to persisted ledger, and full contributing_event_ids must be visible in trace output"
}
```

### `required_single_truth_statement`
```text
After ingestion completes, persisted ledger is the sole source of truth for downstream redemption-state derivation. The ingress artifact must not continue as a parallel truth source.
```

### `required_daily_derivation_rule`
```python
redeem_risk = announcement_date <= date < delisting_date
```

### `required_canonical_state_usage_contract`
```text
Backtest, simulated trading, and future live trading must consume canonical redemption state rather than reconstructing raw redemption facts on the fly. Wave 3 defines the contract only; updater scheduling and consumer rollout are deferred to later waves.
```

### `required_bounded_non_goal_statement`
```text
No fully generalized bitemporal platform in v1. No canonical state updater orchestration in Wave 3. No consumer rollout orchestration in Wave 3.
```

### `required_executable_checklist_items`
```text
A. Authoritative Import Artifact
B. Persisted Ledger as Sole Truth Source
C. Shared Derivation Contract
D. Canonical Redemption State Contract
E. Regression / Traceability / Documentation
```
