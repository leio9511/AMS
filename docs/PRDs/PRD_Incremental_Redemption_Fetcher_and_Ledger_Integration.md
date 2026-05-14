---
> **DEPRECATED** — This PRD was rejected by Auditor and superseded by `PRD_Redemption_Data_Fetcher_—_Full-Snapshot_TuShare_Pull_&_Import_CSV.md` (PRD A). Retained for architecture reference only.
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Redemption Snapshot Ingestion & Ledger Merge

## 1. Context & Problem

### Background
AMS Wave 3 已交付完整的 Redemption Event Ledger：`process_ingress_to_ledger` 管理 new/dedup/correction 三类 revision；`derive_canonical_redemption_state` 从 ledger active revisions 推导每日 canonical。均已 deploy。

### 核心痛点
Ledger 架构完整但无自动化摄入路径。手动维护不可持续。

### 架构决策

1. **全量刷新**。TuShare 是 snapshot API，无 changelog。

2. **手工事件以 append-only 指令日志管理**。`manual_events.csv` 每行是一条不可变命令：`DECLARE`（声明事件）或 `CANCEL`（撤回）。Reduce-then-apply：按 `identity_tuple` 折叠至最终命令态，只推最终态进入导入。完整历史保留在日志中。

3. **Ledger 内解决数据矛盾：manual 纠偏 TuShare 时，TuShare 被显式标记为 SUPERSEDED。不共存，不掩盖。**

   核心问题：当 manual 和 TuShare 都对同一只转债定义了强赎窗口但 delisting_date 不同时，ledger 不能同时 preserve 两个矛盾的事实。一个说退市是 03-01，另一个说是 04-01——至少有一个是错的。

   解决方式：用户是权威。用户填入 manual 数据时，表明 TuShare 数据不准确。pipeline 为该 TuShare 事件生成 supersede row，`process_ingress_to_ledger` 将其标记为 `is_active_revision=False` + `revision_reason="SUPERSEDED"`。 Manual 事件保持 active。

   这跟 Wave 3 已有的 correction 机制是同一逻辑：旧 revision 被标记为 inactive，新 revision 成为 active。唯一差异是 TuShare 的旧数据在后续全量刷新中仍会反复出现（数据相同），因此新增一条检查——latest revision 是 SUPERSEDED 且传入数据相同 → skip，防止 replay-churn。若 TuShare 发布修正后的数据（不同）→ 走正常 correction 路径，复活。

   撤回 manual 纠偏后，TuShare 仍保持 SUPERSEDED（它的数据仍是错的）。若 TuShare 将来发布了正确数据 → 自动复活。这是正确的行为：撤回纠偏不代表 provider 数据突然变对。

4. **`revision_reason` 枚举**：`ACTIVE`（活跃）、`CORRECTED`（被 correction 替代）、`CANCELLED`（用户撤回）、`SUPERSEDED`（被 manual 纠偏替代）。

5. **不 bypass ledger，不 split-brain**。所有事件走同一 import CSV → ledger → canonical 管道。

## 2. Requirements & User Stories

### 2.1 Data Contracts

#### Import CSV
```python
IMPORT_COLUMNS = [
    "source_native_event_id", "bond_code", "announcement_date",
    "delisting_date", "source", "updated_at", "is_cancelled",
    "is_unsupersede"
]
```
`is_cancelled`：True = cancellation row（用户 CANCEL）或 supersede row（自动覆盖 TuShare）。`source` 字段区分是 CANCELLED（source=manual）还是 SUPERSEDED（source=tushare）。
`is_unsupersede`（boolean）：True = RESTORE 命令产生的 unsupersede row，跳过 SUPERSEDED 检查，创建新 active revision。

#### Manual Events CSV
```python
MANUAL_CSV_COLUMNS = [
    "identity_tuple", "source_native_event_id", "bond_code",
    "announcement_date", "delisting_date", "source", "updated_at",
    "command", "reason"
]
```

#### Ledger
```python
LEDGER_COLUMNS = [
    "event_id", "revision", "is_active_revision", "revision_reason",
    "source_native_event_id", "bond_code", "announcement_date",
    "delisting_date", "source", "updated_at"
]
```
`revision_reason` 取值：
- `ACTIVE`：当前活跃 revision
- `CORRECTED`：因 correction 被替代的旧 revision
- `CANCELLED`：用户 CANCEL 命令产生的 tombstone
- `SUPERSEDED`：manual DECLARE 自动覆盖产生的 TuShare tombstone

#### Canonical State（不变）
```python
CANONICAL_COLUMNS = [
    "date", "bond_code", "redeem_risk", "representative_event_id",
    "representative_revision", "contributing_event_count"
]
```

### 2.2 Functional Requirements

1. **`etl/redemption_fetcher.py`**：全量拉取 TuShare 数据。

2. **`manual_redemption_inject.py`**：CLI 追加至 `manual_events.csv`。

3. **`run_redemption_sync_pipeline()`**：
   - step 1: `fetch_redemption_events()` → auto_df
   - step 2: 读取 `manual_events.csv` → manual_df
   - step 2.5: `resolve_manual_commands(manual_df)` → active_rows + cancel_ids
   - step 3: `merge_import(auto_df, active_rows)` → base import CSV
   - step 4: `generate_cancellation_rows(ledger, cancel_ids, import_csv)` — 同轮 DECLARE 检测 + ledger 活跃检查 → 追加 `is_cancelled=True`（source=manual）。Atomic overwrite
   - step 4.5: `generate_supersede_rows(active_rows, auto_df, import_csv)` — 遍历 active_rows，对每条 manual DECLARE 查 auto_df 中同 `bond_code` + `announcement_date` 双键的 TuShare 行。匹配策略：0 条跳过，1 条且 delisting_date 不同 → 追加 supersede row，>1 条 → 拒绝（写入 trace）。幂等由 `process_ingress_to_ledger` 的 `is_cancelled` 分支处理。Atomic overwrite
   - step 4.6: `process_restore_commands(ledger, manual_df, import_csv)` — 过滤 manual_df 中 `command="RESTORE"` 的行。对每条，在 ledger 中查同 `bond_code` + `announcement_date` 双键且 `revision_reason="SUPERSEDED"` 的 TuShare 事件。匹配 → 追加 unsupersede row（同 `source_native_event_id`，`is_unsupersede=True`，`is_cancelled=False`）。匹配策略：0 条跳过，1 条 unsupersede，>1 条拒绝。Atomic overwrite — 遍历 active_rows（manual DECLARE），查 auto_df 中同 `bond_code` + `announcement_date` 双键的 TuShare 行。匹配且 delisting_date 不同 → 追加 supersede row（`source_native_event_id` 复用 TuShare 值，`source="tushare"`，`is_cancelled=True`）。幂等由 `process_ingress_to_ledger` 的 `is_cancelled` 分支处理。Atomic overwrite
   - step 5: `derive_target_dates(import_csv)`
   - step 6: `run_redemption_wave3_pipeline(target_dates)` — `process_ingress_to_ledger` 扩展
   - step 6 前 backup；失败后 restore



**Import CSV 行顺序：** auto_df（TuShare snapshot）→ active_rows（manual DECLARE）→ cancellation rows（source=manual, is_cancelled=True）→ supersede rows（source=tushare, is_cancelled=True）。此顺序确保 `process_ingress_to_ledger` 在处理 cancellation/supersede row 时，对应事件已在同一批中建立了 active revision。

### 2.3 `process_ingress_to_ledger` 扩展

**新增分支 A（correction 路径追加 CORRECTED）：** 现有 correction 分支翻转旧 revision 的 `is_active_revision` 时，同时将 `revision_reason` 设为 `"CORRECTED"`。这是一行追加。

**新增分支 B（is_cancelled=True）：**
```python
if row.get("is_cancelled", "False") in ("True", True):
    if event_id in max_revisions and active_states.get(event_id):
        # 翻批内新行或已有 ledger 行的 active 标记（同 correction 模式）
        if event_id in active_in_new_rows:
            idx = active_in_new_rows[event_id]
            new_rows[idx]["is_active_revision"] = False
        else:
            mask = (new_ledger["event_id"] == event_id) & (new_ledger["is_active_revision"] == True)
            new_ledger.loc[mask, "is_active_revision"] = False
        # 根据 source 区分 CANCELLED 或 SUPERSEDED
        reason = "CANCELLED" if str(row["source"]).strip() == "manual" else "SUPERSEDED"
        new_rows.append({"revision_reason": reason, "is_active_revision": False, ...})
    else:
        continue  # 已无 active → 幂等跳过
```

**新增分支 C（已 SUPERSEDED 不复活）：**
```python
# 在"无 active + event 存在"路径前插入
if event_id in max_revisions and not active_states.get(event_id):
    latest = new_ledger[new_ledger["event_id"] == event_id].iloc[-1]
    latest_reason = latest.get("revision_reason", "ACTIVE")
    if latest_reason == "SUPERSEDED":
        if row.get("is_unsupersede", "False") in ("True", True):
            pass  # RESTORE 命令→跳过 SUPERSEDED 检查，创建新 active revision
        elif all(str(latest[f]) == str(row[f]) for f in bus_fields):
            continue  # 同数据→跳过（TuShare 数据仍错，不复活）
        # 不同数据→TuShare 已修正→fall through 到 correction 路径
    elif latest_reason in ("CANCELLED", "CORRECTED"):
        continue  # 明确终态的 revision 不复活
```

### 2.4 `derive_canonical_redemption_state`

**排序修改：** 代表事件选择增加 `source_priority`（manual > tushare）。当 TuShare 自我修正后 manual 和 TuShare 同时 active 时，manual 事件优先被选为 `representative_event_id`。

```python
overlapping_events['source_priority'] = overlapping_events['source'].map({'manual': 0, 'tushare': 1}).fillna(2)
sorted_events = overlapping_events.sort_values(
    by=['source_priority', 'announcement_date', 'updated_at', 'event_id'],
    ascending=[True, True, False, True]
)
```

SUPERSEDED 的 TuShare 事件 `is_active_revision=False`，标准过滤已排除，不参与排序。排序修改仅影响 TuShare 自我修正后两者同时 active 的场景。

### 2.5 User Stories
- 运维者：收盘后一次 pipeline 保持最新
- 手工注入者：CLI 追加 DECLARE → TuShare 被 supersede → canonical 由 manual 覆盖
- 审计者：`revision_reason` 区分 CANCELLED（用户撤回）和 SUPERSEDED（自动覆盖），ledger 可审计

### 2.6 Backward Compatibility
- 历史 ledger 无 `revision_reason` 列。`read_ledger()` 检测缺失时：`is_active_revision=True`的行默认 `"ACTIVE"`，`is_active_revision=False` 的行默认 `"CORRECTED"`。

### 2.7 Contract Migration

本 PRD 对 Wave 3 的以下 contract 做正式迁移：

**1. Revision invariant**
   - 旧：Exactly one active revision per event_id。
   - 新：At most one active revision per event_id。0 active 是正常状态（cancelled/superseded）。
   - 影响：`derive_canonical_redemption_state` 的 invalid_revision_graph 检查需放宽。Scope 锁定在该函数内（约 2 行）。

**2. Canonical representative selection**
   - 旧：按 `announcement_date → updated_at → event_id` 排序（时间序规则）。
   - 新：按 `source_priority`（manual > tushare）→ `announcement_date → updated_at → event_id`。Manual 事件在代表事件选择中优先。
   - 影响：`derive_canonical_redemption_state` 的排序逻辑增加 source_priority（约 3 行）。仅当 TuShare 修正后 manual 仍 active 时生效。

**3. Supersession 机制（已废弃）**
   - 旧：`data/manual_supersessions.json` 作为 sidecar 持久化 supersession 集合。
   - 新：Ledger 内通过 `revision_reason="SUPERSEDED"` 表达，`generate_supersede_rows()` 生成 supersede row 进入 import CSV。
   - 迁移：`manual_supersessions.json` 不再创建或使用。已有文件保留不删除（不影响运行）。架构文档 `docs/architecture/redemption_data_pipeline.md` 中的 sidecar 流程图已更新为 ledger-only 方案。相关测试用例迁移至新方案。

**未变更的 contract：** canonical schema、ledger 结构、ingress 管道、全量刷新策略、append-only 纪律。

## 3. Architecture & Technical Strategy

### 3.1 Pipeline
```
step 1: fetch → auto_df
step 2: read manual_events.csv → manual_df
step 2.5: resolve_manual_commands → active_rows + cancel_ids
step 3: merge_import(auto_df, active_rows) → base import CSV
step 4: generate_cancellation_rows → append is_cancelled=True (source=manual)
step 4.5: generate_supersede_rows → append is_cancelled=True (source=tushare)
step 5: derive_target_dates(import_csv)
step 6: run_redemption_wave3_pipeline(target_dates)
        ├── process_ingress_to_ledger:
        │   └── is_cancelled=True, source=manual → CANCELLED
        │   └── is_cancelled=True, source=tushare → SUPERSEDED
        │   └── SUPERSEDED + 同数据 → skip（不复活）
        ├── derive_canonical_redemption_state(ledger) # 排序增加 source_priority
        └── fail → restore from backup
```

### 3.2 resolve_manual_commands / generate_cancellation_rows
同前。不变。

### 3.3 generate_supersede_rows
- 遍历 `active_rows`（manual DECLARE 最终态）
- 对每条，查 `auto_df` 中同 `bond_code` + `announcement_date` 双键的 TuShare 行
- 找到且 `delisting_date` 不同 → 追加 supersede row（`source="tushare"`，`is_cancelled=True`）
- 不匹配 → 跳过。
- Supersede row 进入 `process_ingress_to_ledger` 后自动处理幂等：若 TuShare 已 SUPERSEDED → `is_cancelled=True` + 无 active → skip；若 TuShare 是 active（被修正后）→ `is_cancelled=True` + active → 翻转至 SUPERSEDED。
- Atomic overwrite。

## 4. Acceptance Criteria (BDD)

- **Scenario 1** — 正常注入
  Given import CSV 含 N 行 TuShare + M 行 manual DECLARE
  When `run_redemption_wave3_pipeline` 处理
  Then Ledger 含 N+M 个 active revision。Canonical 包含所有事件对应的日度行。

- **Scenario 2** — 数据幂等
  Given 相同 import CSV 连续两次输入
  When 第二次处理
  Then Ledger 无额外 revision。Canonical 一致。

- **Scenario 3** — Manual CANCEL
  Given import CSV 含 `is_cancelled=True`（source=manual）的 cancellation row
  When 处理
  Then Ledger 新增 revision（`revision_reason="CANCELLED"`，`is_active_revision=False`）。重跑幂等。

- **Scenario 4** — Manual 纠偏 TuShare（首次运行）
  Given TuShare 含 bond A（`delisting_date=2025-03-01`），manual DECLARE 含 bond A（`delisting_date=2025-04-01`）
  When pipeline 运行
  Then import CSV 含 supersede row（source=tushare, is_cancelled=True）。Ledger 中 TuShare A 新增 revision（`revision_reason="SUPERSEDED"`，`is_active_revision=False`）。Manual A 为 active。Canonical 仅由 manual A 覆盖。

- **Scenario 5** — 纠偏后重跑幂等
  Given 上轮已 supersede bond A 的 TuShare
  When 相同 snapshot + 相同 manual 再次 pipeline
  Then Ledger 无额外 revision。Canonical 与第一轮一致（仅 manual A 覆盖）。

- **Scenario 6** — TuShare 自我修正
  Given bond A 的 TuShare 已被 supersede
  When TuShare snapshot 发布修正后的 `delisting_date=2025-04-01`（与 manual 相同数据）
  Then Ledger 中 TuShare A 新增 active revision（`revision_reason="ACTIVE"`）。Manual A 保持 active。Canonical 中 `representative_event_id` 指向 manual。

- **Scenario 7** — CANCEL 后 TuShare 不自动复活
  Given bond A 的 TuShare 已被 supersede
  When 用户追加 CANCEL(manual A)，重跑 pipeline
  Then manual A 新增 CANCELLED revision。TuShare A 保持 SUPERSEDED + 同数据 → skip。Bond A 无 active 事件。Canonical 中该债 `redeem_risk=False`。

- **Scenario 8** — RESTORE 恢复 TuShare
  Given bond A 的 TuShare 已被 supersede（manual DECLARE active），且用户已追加 CANCEL(manual A)
  When 用户追加 `RESTORE` 行（`identity_tuple=A`）→ pipeline 运行
  Then `process_restore_commands` 生成 unsupersede row。`process_ingress_to_ledger` 跳过 SUPERSEDED 检查，创建 TuShare A 新 active revision。Canonical 由 TuShare A 覆盖。

- **Scenario 9** — Pipeline 原子恢复
  Given step 6 前已备份
  When 中途失败
  Then ledger + canonical + trace + freshness 全部恢复。Freshness=FAILED。

## 5. Overall Test Strategy & Quality Goal
1. Fetcher 测试
2. `resolve_manual_commands` 测试
3. `generate_cancellation_rows` + `generate_supersede_rows` + `process_restore_commands` 测试
4. `process_ingress_to_ledger`：cancellation、supersede、幂等、CORRECTED、不复活检查
5. Pipeline E2E：inject → supersede → idempotent rerun → TuShare correct → CANCEL → RESTORE
6. Backup/restore 测试

## 6. Framework Modifications
- `IMPORT_COLUMNS`：新增 `is_cancelled` 和 `is_unsupersede`（boolean）
- `LEDGER_COLUMNS`：新增 `revision_reason`（string enum）
- `process_ingress_to_ledger`：correction 加 CORRECTED（~1 行）+ `is_cancelled=True` 分支（~10 行）+ 不复活检查（~8 行）
- `derive_canonical_redemption_state`：代表事件排序增加 source_priority（manual > tushare，~3 行）

---

## Appendix: Architecture Evolution Trace
- v5.9 (final): Ledger 内解决数据矛盾。Manual 纠偏 → TuShare SUPERSEDED（inactive），不复活相同旧数据。CANCEL → CANCELLED。Correction 旧 revision → CORRECTED。没有共存，没有掩盖。`derive_canonical_redemption_state`：排序增加 source_priority（manual > tushare）。

---

## 7. Hardcoded Content

- **TuShare is_call filter**:
  ```python
  IS_CALL_FILTER = "公告实施强赎"
  ```
- **Source strings**:
  ```python
  SOURCE_TUSHARE = "tushare"
  SOURCE_MANUAL = "manual"
  ```
- **Default start year**: `2019`
- **Staleness threshold**: `3`

- **File paths**（不变）: `redemption_event_facts_import.csv`, `redemption_event_ledger.csv`, `canonical_redemption_state.csv`, `manual_events.csv`, `redemption_fetcher_state.json`, `freshness_report.json`, `reports/redemption_event_trace.json`

- **IMPORT_COLUMNS**:
  ```python
  IMPORT_COLUMNS = [
    "source_native_event_id", "bond_code", "announcement_date",
    "delisting_date", "source", "updated_at", "is_cancelled",
    "is_unsupersede"
  ]
  ```
- **LEDGER_COLUMNS**:
  ```python
  LEDGER_COLUMNS = [
    "event_id", "revision", "is_active_revision", "revision_reason",
    "source_native_event_id", "bond_code", "announcement_date",
    "delisting_date", "source", "updated_at"
  ]
  ```
- **MANUAL_CSV_COLUMNS**:
  ```python
  MANUAL_CSV_COLUMNS = [
    "identity_tuple", "source_native_event_id", "bond_code",
    "announcement_date", "delisting_date", "source", "updated_at",
    "command", "reason"
  ]
  ```
- **CANONICAL_COLUMNS**（不变）:
  ```python
  CANONICAL_COLUMNS = [
    "date", "bond_code", "redeem_risk", "representative_event_id",
    "representative_revision", "contributing_event_count"
  ]
  ```

- **revision_reason 迁移矩阵**:

  | 触发条件 | 旧 revision | 新 revision |
  |---|---|---|
  | 新 identity 首次出现 | — | `revision_reason="ACTIVE"`, `is_active_revision=True` |
  | 同 identity 同数据（dedup） | 不变 | 不产生新 revision |
  | 同 identity 不同数据（correction） | `is_active_revision=False`, `revision_reason="CORRECTED"` | `revision_reason="ACTIVE"`, `is_active_revision=True` |
  | `is_cancelled=True`, `source="manual"`（CANCEL） | `is_active_revision=False` | `revision_reason="CANCELLED"`, `is_active_revision=False` |
  | `is_cancelled=True`, `source="tushare"`（supersede） | `is_active_revision=False` | `revision_reason="SUPERSEDED"`, `is_active_revision=False` |

- **Pipeline status**:
  ```python
  PIPELINE_STATUS_NORMAL = "NORMAL"
  PIPELINE_STATUS_FAILED = "FAILED"
  ```

- **Representative selection rule**：
  ```python
  overlapping_events['source_priority'] = overlapping_events['source'].map({'manual': 0, 'tushare': 1}).fillna(2)
  sorted_events = overlapping_events.sort_values(
      by=['source_priority', 'announcement_date', 'updated_at', 'event_id'],
      ascending=[True, True, False, True]
  )
  ```
  新规则在旧规则基础上增加 source_priority。仅当 TuShare 自我修正后 manual 仍 active 时生效。

- **CLI warning**:
  ```text
  MANUAL_INJECT_WARNING = "Appended to manual_events.csv. Pipeline: import CSV -> ledger -> canonical. Manual events supersede matching TuShare events on (bond_code, ann_date). To cancel: inject --command CANCEL."
  ```

- **process_restore_commands rule**: 过滤 manual_df 中 `command="RESTORE"` 的行。对每条，在 ledger 中查同 `bond_code` + `announcement_date` 双键且 `revision_reason="SUPERSEDED"` 的 TuShare 事件。匹配策略：0 条跳过，1 条 → unsupersede row（`source_native_event_id` 复用 TuShare 值，`is_unsupersede=True`，业务字段复用 ledger 值），>1 条拒绝。Atomic overwrite。

- **Error types**: `SchemaValidationError`, `DataProviderError`
