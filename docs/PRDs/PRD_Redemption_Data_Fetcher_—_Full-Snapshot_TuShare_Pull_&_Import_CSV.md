---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Redemption Data Fetcher — Full-Snapshot TuShare Pull & Import CSV

## 1. Context & Problem

### Background
AMS Wave 3 (`etl/redemption_pipeline.py`) 已交付完整的 redemption event ledger pipeline：
- `process_ingress_to_ledger` 管理新事件 / dedup / correction 三类 revision
- `derive_canonical_redemption_state` 从 ledger active revisions 推导每日 canonical
- 均已在 `master` 中 deploy

### 核心痛点
Wave 3 pipeline 目前已能消费静态 Import CSV，但**没有自动化的数据获取路径**。Import CSV 必须手动准备，无法满足日常增量更新的需求。

### 关键发现
TuShare `cb_call` 是全量 snapshot API（支持 `start_date` / `end_date` 按日期范围过滤）。实测验证：
- 全量（2019-01-01 至今）：**~2000 行**
- 最近 7 天：17 行

全量 2000 行的规模完全可接受。因此 PRD 采用 **全量 Snapshot Pull + Ledger 幂等去重** 的方案。

### 关于 Snapshot Absence Reconciliation 的声明

**结论：Snapshot absence reconciliation 在此业务域不成立。**

TuShare `cb_call` 返回的是**历史既成事实**：某可转债在某个日期发生了一次强制赎回。这是一个不可撤销的企业行为事件——

判断依据：
1. 数据是历史事实，不是可变的实时状态。
2. 全量 ~2000 行，每天全量 refresh，即使发生极端数据异常，correction 路径接得住。
3. 若 TuShare 因上游异常导致事件从 snapshot 消失（理论上不会发生），应 **告警 + 人工介入**，而不是被自动化 reconciliation 无声处理掉。

因此本 PRD **不做负向对账**。已确认进入 ledger 的事件除非被 correction 替代，否则不会因为从 TuShare snapshot 消失而自动撤回。

**消失检测：** pipeline 每次运行后持久化本次 snapshot 的 **领域过滤后观测集合**（`previous_id_set`，基于 `MappedRedemptionResult.filtered_snapshot_ids`——已完成 `call_type="强赎"` 过滤、重复 identity 拒绝前）。下轮运行时计算 `missing_ids = set(previous_id_set) - set(filtered_snapshot_ids)`。若 `missing_ids` 非空，写入 `freshness_report.json` 并触发告警。**全量历史 pull 返回 EMPTY 不进入消失检测——先触发 EMPTY 告警。**

### 范围声明
本 PRD **只做 TuShare 数据获取 + 字段映射 + Import CSV 生成 + state tracker + 编排闭环**。以下内容不在本 PRD 范围内，由后续 PRD B/C 处理：
- 手工事件注入（DECLARE / CANCEL）
- 数据源冲突（manual 纠偏 TuShare）
- TuShare API 失败时的降级处理
- RESTORE / supersede 等复杂状态机

### 前提假设
- **Snapshot absence reconciliation 不适用**（见上）。
- `call_type="强赎"` 标识强制赎回事件。其他 `call_type` 值不纳入。
- `source_native_event_id = f"{ts_code.replace('.','')}_{ann_date}"` 唯一标识（ts_code 去点号，如 `"118033SH_20260514"`）。**若 TuShare 返回重复行**（ts_code + ann_date 完全一致），所有重复行被拒绝（写入 `rejected_facts`），不 ingesting 任何一条。不存在静默裁剪。
- `tushare_provider.TuShareProvider` 实例由 `redemption_fetcher.py` 在构造时接收。不直接调用模块函数。

## 2. Requirements & User Stories

### 2.1 Data Contracts

#### 数据源
| 数据源 | 获取方式 |
|--------|----------|
| TuShare cb_call | TuShareProvider.fetch_and_map_redemption_events(start_date, end_date) — 内部完成 cb_call + filter + join cb_basic + 映射 |
| TuShare cb_basic | TuShareProvider.fetch_cb_basic() — 已有方法，provider 内部 join |

`redemption_fetcher.py` **不感知 TuShare 字段名**。只调用 `provider.fetch_and_map_redemption_events()`。

#### State Tracker
```python
STATE_TRACKER_PATH = "data/redemption_fetcher_state.json"
```
`last_successful_sync` 记录最后一次成功同步时间。每次 pipeline 拉取 2019-01-01 → today。**不依赖 state tracker 做决策。**

#### Import CSV（不变）
```python
IMPORT_COLUMNS = ["source_native_event_id", "bond_code", "announcement_date", "delisting_date", "source", "updated_at"]
```

#### Ledger（扩展）
```python
LEDGER_COLUMNS = ["event_id", "revision", "is_active_revision", "revision_reason",
    "source_native_event_id", "bond_code", "announcement_date", "delisting_date", "source", "updated_at"]
```

`revision_reason` 完整枚举（本 PRD 仅写入 ACTIVE / CORRECTED / LEGACY）：
- `"ACTIVE"`：当前活跃
- `"CORRECTED"`：被 correction 替代
- `"CANCELLED"`：用户撤回（PRD B 启用）
- `"SUPERSEDED"`：被 manual 覆盖（PRD C 启用）
- `"LEGACY"`：历史兼容，`is_active=False` 且无法区分原因。中性占位，不隐含 correction 语义。

### 2.2 Functional Requirements

1. **`etl/tushare_provider.py` → TuShareProvider.fetch_and_map_redemption_events(start_date, end_date) → MappedRedemptionResult**
   - 调用 `self.pro.cb_call(start_date=start_str, end_date=end_str)`，`_handle_exception` 兜底
   - 过滤 `call_type="强赎"`
   - 调用 `self.fetch_cb_basic()` 全量拉取，left join on `ts_code`
   - `source_native_event_id = f"{ts_code.replace('.','')}_{ann_date}"`，最终格式：`"118033SH_20260514"`（ts_code 去点号 + 下划线 + ann_date，纯 ascii 无空格）
   - `delisting_date` 优先级：`cb_basic.delist_Date` → `cb_call.call_date` → `""`
   - **重复行检查：** 对 `source_native_event_id` 做 `.duplicated(keep=False)`。若有重复：
     - 所有重复行 **不进入** 返回的 DataFrame
     - 返回 `MappedRedemptionResult`（见 Section 7），含：
     - `df`（有效映射行，纯 DataFrame）
     - `filtered_snapshot_ids`（list[str]，已完成 `call_type="强赎"` 过滤后、重复 identity 拒绝前的观测集合）
     - `rejected_duplicates`（list[dict]，与 df 分离）

2. **`etl/redemption_fetcher.py`** — 编排器。
   - `__init__(self, provider: TuShareProvider, ...)` — 接收已认证的 provider 实例
   - `fetch_and_build_import_csv(import_csv_path) → FetchResult`
     - 调用 `self.provider.fetch_and_map_redemption_events(BOOTSTRAP_START_DATE, today)`
     - 重复行写入 `data/reports/redemption_fetcher_rejected.json`（与 wave3 的 `redemption_event_trace.json` 分属不同写者，避免冲突）
     - 写 Import CSV 到 `import_csv_path`（直接写入正式路径）
     - 保存 `filtered_snapshot_ids`（provider 返回的领域过滤后观测集合）供消失检测使用
     - 返回 FetchResult

     Import CSV 是临时产物（“不持久化，每次重新生成”），wave3 失败时直接删除。
   - `run_redemption_sync_pipeline() → PipelineResult`

3. **编排决策（单一语义）**
   - `fetch_and_build_import_csv()` → 返回 FetchResult
     - `success=True, status="OK"`：正常 → 继续
     - `success=False, status="EMPTY_ABORT"`：0 行。**全量历史 pull（2019-01-01→today）不应返回 0 行（已知 ~2000 行），此异常应终止 pipeline**，不写 tracker，写入 `freshness_report.json` 的 `empty_snapshot_warning`。
     - `success=False, status="API_FAILED"`：API 调用失败 → 终止，不写 tracker
     - **无 INVALID 状态**。行级有效校验由 `process_ingress_to_ledger` 统一负责（`_validate_and_generate_identity`），不在 fetcher/provider 层重复。所有行均通过校验、全部被 ledger 拒绝、或部分通过部分拒绝，最终行为相同——wave3 幂等处理有效行，拒绝行计入 rejected_facts，pipeline 正常继续。
   - **Step 2（不变）：** 推导 `target_dates = fetch_trade_calendar(BOOTSTRAP_START_DATE, today)`
   - **Step 3（多产物原子提交）：** 调用 `run_redemption_wave3_pipeline()` 前，对 ledger + canonical + trace 三个真相源文件做备份（`{path}.bak`）。成功后删除备份。异常时恢复三文件，删除 import_csv 和 rejected 产物（临时/观测文件，下轮重新生成）→ 终止，不写 tracker。
   - **Step 4（集合级消失检测）：** pipeline 成功后，从 `filtered_snapshot_ids` 获取领域过滤后观测集合。计算 `missing_ids = set(prev) - set(filtered)`。若非空 → 写入 `freshness_report.json`。EMPTY 路径不走此步骤。
   - **Step 5（不变）：** `update_state_tracker()`

4. **消失检测合约**
   ```python
   # state_tracker 新增字段
   TRACKER_PREVIOUS_ID_SET = "previous_id_set"  # list[str]，上轮领域过滤后观测集合

   # 检测逻辑
   # 1. pipeline 成功后，从 MappedRedemptionResult.filtered_snapshot_ids 提取过滤后观测集合
   # 2. 读取 state_tracker 中的 previous_id_set
   # 3. 若 previous_id_set 非空且当前 fetch 非 EMPTY，计算 missing_ids = set(previous_id_set) - set(filtered_snapshot_ids)
   # 4. 若 missing_ids 非空 → 写入 freshness_report.json 的 disappearance_warning
   # 5. 当次 fetch 为 EMPTY_ABORT → 跳过消失检测，previous_id_set 保留旧值
   # 6. 非 EMPTY 时更新 previous_id_set = filtered_snapshot_ids
   # 注：filtered_snapshot_ids 是领域过滤后（call_type="强赎"）、重复拒绝前的观测集合。
   #   与 Import CSV 有效行分开——准入层变化不污染基线。领域过滤在前：非强赎事件不进入基线。
   ```
   ```

### 2.3 Pipeline 流程图
```
run_redemption_sync_pipeline()
  Step 1: fetch_and_build_import_csv()
    └── provider.fetch_and_map_redemption_events(BOOTSTRAP_START_DATE, today)
          ├── pro.cb_call()
          ├── filter call_type="强赎"
          ├── left join cb_basic
          ├── 重复 identity 检查 → 拒绝所有重复行，入 rejected_facts
          └── 映射到 IMPORT_COLUMNS

    ├── OK → 继续
    ├── EMPTY_ABORT → 终止，empty_snapshot_warning，不写 tracker
    └── API_FAILED → 终止，不写 tracker

  Step 2: derive target_dates = BOOTSTRAP_START_DATE→today 交易日
  Step 3: backup (ledger+canonical+trace) → run_wave3
    ├── 成功 → 删除备份
    └── 异常 → restore three, 删 import_csv+rejected（临时/观测产物）, 终止, 不写 tracker

  Step 4: 消失检测
  Step 5: update_state_tracker()

EMPTY 分支:
  EMPTY_ABORT: 同 API_FAILED 终止规则
```

### 2.4 Backward Compatibility
- **历史 ledger 无 `revision_reason`**：`read_ledger()` 回填：`is_active=True` → `"ACTIVE"`；`is_active=False` → `"LEGACY"`

## 3. Architecture & Technical Strategy

### 3.1 模块职责
```
etl/
├── tushare_provider.py                # MODIFIED
│   └── TuShareProvider
│       ├── fetch_cb_call(start, end)  # 私有
│       ├── fetch_cb_basic()           # 已有
│       └── fetch_and_map_redemption_events(start, end) → MappedRedemptionResult  # 新增
├── redemption_fetcher.py              # NEW
│   └── __init__(self, provider: TuShareProvider, ...)
│       ├── fetch_and_build_import_csv() → FetchResult
│       ├── run_redemption_sync_pipeline() → PipelineResult
│       └── _check_disappearance()
├── redemption_pipeline.py             # UNCHANGED
├── redemption_ledger.py               # MODIFIED — COLUMNS + revision_reason + LEGACY
├── redemption_derivation.py           # UNCHANGED
└── tushare_enrichment_orchestrator.py # UNCHANGED
```

### 3.2 编排状态机
```
fetch(OK)   → target_dates → wave3 → 消失检测 → 写 tracker
fetch(EMPTY_ABORT) → 终止, empty_snapshot_warning, 不写 tracker
fetch(API_FAILED) → 终止，不写 tracker
wave3 异常 → 终止，不写 tracker
```
OK 走正常路径。EMPTY_ABORT 和 API_FAILED 终止——`FetchResult.success=False` 统一触发终止。

所有行级校验由 `process_ingress_to_ledger` 统一负责，不在 fetcher 层判定 INVALID。

### 3.3 重复 identity 处理
`source_native_event_id = f"{ts_code.replace('.','')}_{ann_date}"`。事实保证唯一（同一债券同一天至多一条强赎公告）。
若 TuShare 因上游异常返回重复行：
1. 检测到 `.duplicated(keep=False)` → 所有重复行被拒绝
2. 不 ingesting 任何一条重复行
3. 重复行原数据写入 `rejected_facts` trace 供人工审查
4. 一条重复行也不支持静默 dedup——identity 是确定性合约，不是可以随意压缩的东西

### 3.4 消失检测
pipeline 成功后，从 `MappedRedemptionResult.filtered_snapshot_ids` 获取观测集合，计算 `missing_ids = set(previous_id_set) - set(filtered_snapshot_ids)`。若非空，写入 `freshness_report.json`。
- 不设阈值
- EMPTY 路径不走此步骤
- 使用 `source_native_event_id` 格式（如 `"118033SH_20260514"`）

## 4. Acceptance Criteria (BDD)

### Scenario 1 — 首次运行
- **Given** ledger 空，tracker 不存在
- **When** pipeline 运行
- **Then** Import CSV 含全部赎回事件；Ledger 新增 revision（`revision_reason="ACTIVE"`）；Tracker 写入。

### Scenario 2 — 重复运行
- **Given** ledger 已有前次 revision
- **When** 第二次运行
- **Then** Ledger 无额外 revision（dedup）；Canonical 一致；Tracker 更新。

### Scenario 3 — Data Correction
- **Given** Bond A 在 ledger 中 `delisting_date=2025-03-01`
- **When** TuShare 返回不同 `delisting_date=2025-04-01`
- **Then** 旧 → `"CORRECTED"`；新 → `"ACTIVE"`。

### Scenario 4 — EMPTY 异常
- **Given** TuShare snapshot 全量历史返回 0 行（已知正常数据应为 ~2000 行）
- **When** pipeline 运行结束
- **Then** `freshness_report.json` 的 `empty_snapshot_warning` 字段非空；Ledger CSV 与运行前一致（无新 revision）；Canonical CSV 与运行前一致；State tracker 中 `last_successful_sync` 未更新。

### Scenario 5 — 全部行被行级校验拒绝
- **Given** Import CSV 中所有行的 `delisting_date` 字段均为空
- **When** pipeline 运行完成
- **Then** Ledger 无新 revision；Canonical 与运行前一致；`freshness_report.json` 的 `pipeline_status` 为 `"NORMAL"`；State tracker 中 `last_successful_sync` 已更新。

### Scenario 6 — API_FAILED
- **Given** TuShare API 不可用
- **When** pipeline 运行结束
- **Then** Import CSV 文件与运行前一致（未覆盖）；Ledger CSV 不变；Canonical CSV 不变；State tracker 中 `last_successful_sync` 未更新。

### Scenario 7 — 重复 identity 拒绝
- **Given** TuShare 返回两行具有相同的 `ts_code` + `ann_date`
- **When** pipeline 运行完成
- **Then** Import CSV 中不存在这两行记录；`data/reports/redemption_fetcher_rejected.json` 包含这两行的原始数据；Ledger 中未因这两行产生任何新 revision。

### Scenario 8 — 消失检测告警
- **Given** TuShare snapshot 上一次运行时包含事件 A、B、C，本次运行时仅包含 A、B（C 已不存在于 snapshot 中）
- **When** pipeline 运行完成
- **Then** `freshness_report.json` 的 `disappearance_warning` 字段包含事件 C 的 ID；Ledger 中事件 C 的 `is_active_revision` 仍为 True（告警不干预已持久化的账本数据）。

### Scenario 9 — Wave3 失败回滚
- **Given** pipeline 在 canonical 状态推导阶段异常退出
- **When** 检查所有持久化文件
- **Then** Ledger CSV 内容与运行前完全一致；Canonical CSV 与运行前一致；Trace JSON 与运行前一致；`redemption_fetcher_state.json` 中 `last_successful_sync` 未更新。

### Scenario 10 — EMPTY 不更新消失基线
- **Given** Tushare snapshot 上一次正常运行后持久化了事件 A、B 的观测记录
- **When** 本次全量拉取返回 0 行导致 EMPTY_ABORT
- **Then** `freshness_report.json` 包含 `empty_snapshot_warning`；State tracker 中 `last_successful_sync` 和 `previous_id_set` 均与运行前一致（未更新）；Ledger 不变。

### Scenario 11 — Backward Compatibility
- **Given** 一份未含 `revision_reason` 列的历史 ledger CSV，通过标准 pipeline 首次运行
- **When** 检查输出的 canonical 状态
- **Then** ledger 中 `is_active_revision=True` 的所有行在有 `revision_reason` 列后值为 `"ACTIVE"`；所有 `is_active_revision=False` 的行值为 `"LEGACY"`；Canonical 推导结果与回填前一致。

## 5. Overall Test Strategy & Quality Goal

### 核心质量风险
- 重复 identity 检查漏掉（应全部拒绝而非静默保留）
- 消失检测（set diff）漏掉
- State tracker 序列化/反序列化异常

### Mocking 策略
- `TuShareProvider.fetch_and_map_redemption_events` mock（OK / EMPTY_ABORT / 重复行 / API_FAILED 模式）
- `TuShareProvider.fetch_cb_basic` mock
- `TuShareProvider.fetch_trade_calendar` mock
- State tracker / import CSV I/O：tempfile

### 测试层级
- **Unit tests**：重复行拒绝、消失检测（set diff）、编排决策（EMPTY_ABORT 终止 / API_FAILED 终止）
- **Integration test**（1 个）：完整 E2E

## 6. Framework Modifications

- **`etl/tushare_provider.py`**：`TuShareProvider` 新增 `fetch_and_map_redemption_events(start_date, end_date) → MappedRedemptionResult`。内部调用 cb_call + 过滤 + join cb_basic + 字段映射。**重复 identity 行被拒绝（不 ingesting）。**
- **`etl/redemption_fetcher.py`**：新文件。接收 `TuShareProvider` 实例。编排 `fetch → target_dates → wave3 → 消失检测 → tracker`。
- **`etl/redemption_ledger.py`**：`LEDGER_COLUMNS` 加 `revision_reason`；`process_ingress_to_ledger()` 设置 ACTIVE / CORRECTED；`read_ledger()` 回填 LEGACY。

## 7. Hardcoded Content

### File Paths
```python
FETCHER_STATE_PATH = "data/redemption_fetcher_state.json"
IMPORT_CSV_PATH = "data/redemption_event_facts_import.csv"
LEDGER_CSV_PATH = "data/redemption_event_ledger.csv"
CANONICAL_CSV_PATH = "data/canonical_redemption_state.csv"
# Import CSV 直接写入正式路径。wave3 失败时删除（临时产物，不持久化）。
TRACE_JSON_PATH = "data/reports/redemption_event_trace.json"
REJECTED_TRACE_PATH = "data/reports/redemption_fetcher_rejected.json"  # 重复 identity 被拒绝的原始行
FRESHNESS_REPORT_PATH = "data/reports/freshness_report.json"
```

### freshness_report.json schema
```json
{
  "generated_at": "2026-05-14T19:00:00Z",
  "pipeline_status": "NORMAL | FAILED | EMPTY_ABORT",
  "empty_snapshot_warning": null | {
    "message": "全量历史 pull 返回 0 行，预期 ~2000 行",
    "suggested_action": "检查 TuShare API 状态，确认数据是否正确"
  },
  "disappearance_warning": null | {
    "missing_ids": ["118033SH_20260514"],
    "previous_count": 3,
    "current_count": 2
  }
}
```
写入所有权：`run_redemption_sync_pipeline()` 全权写入（overwrite 整文件）。state tracker 与 freshness_report 互不依赖。

写入时机：| 状态 | `pipeline_status` | 写入字段 |
|---|---|---|
| 正常完成 | `"NORMAL"` | `empty_snapshot_warning: null`, `disappearance_warning: null 或 {...}` |
| EMPTY_ABORT | `"EMPTY_ABORT"` | `empty_snapshot_warning: {...}`, `disappearance_warning: null` |
| fetch 层异常 | `"FAILED"` | 不写入（pipeline 终止前未创建 report 句柄） |
| wave3 异常 | `"FAILED"` | 不写入（后备恢复后终止，不写 tracker，也不写 report） |
两次成功运行之间 report 完全 overwrite。

### State Tracker
```python
STATE_TRACKER_KEYS = ["last_successful_sync", "version", "previous_id_set"]
STATE_TRACKER_VERSION = "1.0"
```

### Source Strings
```python
SOURCE_TUSHARE = "tushare"
BOOTSTRAP_START_DATE = "2019-01-01"
```

### Disappearance Detection
```python
# 消失检测不做阈值——直接 set diff，有 missing_ids 就告警
# 由人工判断 missing 的事件是否合理
```

### Columns
```python
IMPORT_COLUMNS = ["source_native_event_id", "bond_code", "announcement_date", "delisting_date", "source", "updated_at"]
LEDGER_COLUMNS = ["event_id", "revision", "is_active_revision", "revision_reason",
    "source_native_event_id", "bond_code", "announcement_date", "delisting_date", "source", "updated_at"]
CANONICAL_COLUMNS = ["date", "bond_code", "redeem_risk", "representative_event_id",
    "representative_revision", "contributing_event_count"]
```

### revision_reason 枚举
```python
REVISION_REASON_ACTIVE = "ACTIVE"
REVISION_REASON_CORRECTED = "CORRECTED"
REVISION_REASON_CANCELLED = "CANCELLED"
REVISION_REASON_SUPERSEDED = "SUPERSEDED"
REVISION_REASON_LEGACY = "LEGACY"
```

### revision_reason 迁移矩阵
- 新 identity：`"ACTIVE"`, `is_active=True`
- Dedup：不产生新 revision
- Correction：旧 → `"CORRECTED"`, `is_active=False`；新 → `"ACTIVE"`, `is_active=True`
- 历史（列缺失）：`is_active=True` → `"ACTIVE"`；`is_active=False` → `"LEGACY"`

### TuShare API Filter
```python
CALL_TYPE_REDEEM = "强赎"
```

### Provider 层返回类型（TuShareProvider.fetch_and_map_redemption_events 返回值）
```python
@dataclass
class MappedRedemptionResult:
    df: pd.DataFrame            # 有效映射行（已排除重复 identity），columns=IMPORT_COLUMNS
    filtered_snapshot_ids: list[str]  # `call_type="强赎"` 过滤后、重复拒绝前的观测集合
    rejected_duplicates: list[dict]  # 被拒绝的重复行原数据（JSON 序列化安全）
```
- `df`：准入层，经过 filter + mapping + 重复行拒绝后什么被允许进入 ledger

### FetchResult（编排层返回值）
```python
@dataclass
class FetchResult:
    success: bool
    status: str       # "OK" | "EMPTY_ABORT" | "API_FAILED"
    row_count: int
    rejected_count: int
```
注：无 INVALID 状态。行级校验由 ledger 统一处理，不在 fetcher 层复制。

### PipelineResult（编排层返回值）
```python
@dataclass
class PipelineResult:
    success: bool
    status: str       # "OK" | "EMPTY_ABORT" | "FETCH_FAILED" | "WAVE3_FAILED"
    ingress_count: int
    ledger_event_count: int
    canonical_date_count: int
    disappearance_warning: dict | None  # {"missing_ids": [...], "previous_count": int, "current_count": int}
```

### 编排规则（单一语义）
```
FetchResult.success=True, status="OK" → 继续 pipeline → 写 tracker
FetchResult.success=False → 终止, 不写 tracker
Wave3 异常 → 恢复（ledger+canonical+trace）, 删 import_csv+rejected, 终止, 不写 tracker
消失检测 → 仅观测和告警，不影响 tracker 写入
```

---

## Appendix: Architecture Evolution Trace

- **v1.0**: 增量方案
- **v1.1**: 预审修正（identity 钉死、tracker 时机）
- **v1.2**: 全量 Snapshot；delist_Date 修正；target_dates 推导
- **v1.3**: full enum；FetchResult/PipelineResult 双层编排
- **v1.4**: Absence 不成立声明；provider 下沉
- **v1.5（本轮）**：
  - EMPTY 异常处理：全量历史 pull 返回 0 行视为数据异常，终止 pipeline 并告警，不更新 tracker
  - 重复 identity 处理统一：全部拒绝，不 ingesting（去 "sort + drop_duplicates" lossy dedup）
  - Provider 抽象对齐：`TuShareProvider` 实例方法，`redemption_fetcher` 接收 provider 实例
  - 消失检测：set diff 精准检测 + `freshness_report.json` 告警，不干预 ledger
  - Section 7 新增 `FRESHNESS_REPORT_PATH`
