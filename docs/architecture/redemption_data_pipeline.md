# Redemption Data Pipeline Architecture

> 本文档分两阶段描述：「当前（PRD A 已实现）」和「未来（PRD B/C 待实现）」。当前阶段只涉及 TuShare 数据获取 + ledger 幂等去重。Manual 注入、多源整合、SUPERSEDED 状态等为未来阶段。

---

## 当前状态（PRD A 已实现）

### 数据流概览

```
TuShare cb_call API (全量 Snapshot, ~2000行)
    │
    ▼
tushare_provider.TuShareProvider.fetch_and_map_redemption_events()
    ├── pro.cb_call(start, end)
    ├── 过滤 call_type="强赎"
    ├── left join cb_basic.delist_Date on ts_code
    ├── 字段映射到 IMPORT_COLUMNS
    └── 重复 identity 检查 (全拒绝, 不入 df)
    │ 产出: MappedRedemptionResult
    │   ├── df (有效行)
    │   ├── filtered_snapshot_ids (领域过滤后观测集合)
    │   └── rejected_duplicates (重复行原始数据)
    │
    ▼
redemption_fetcher.fetch_and_build_import_csv()
    ├── 拥有 fetch artifact/status gate：
    │   ├── 写 Import CSV
    │   ├── 写 rejected trace
    │   ├── OK → 继续
    │   ├── EMPTY_ABORT → 停止
    │   └── API_FAILED → 停止
    │
    ▼ (仅 OK 路径继续)
Step 2: target_dates = BOOTSTRAP_START_DATE→today 交易日
    │
    ▼
Step 3: 在 redemption_fetcher.py 中为 truth sources 创建相邻 `.bak` sidecars
    ├── data/redemption_event_ledger.csv.bak
    ├── data/canonical_redemption_state.csv.bak
    └── data/reports/redemption_event_trace.json.bak
    │
    ▼
run_redemption_wave3_pipeline(target_dates)
    ├── process_ingress_to_ledger (new/dedup/correction + revision_reason)
    ├── derive_canonical_redemption_state
    └── 写 Ledger + Canonical + Trace
    │
    ├── 成功 → 删除 `.bak` sidecars
    └── 异常 → 恢复 truth sources，删除 import_csv + rejected trace，停止
    │
    ▼ (成功后)
Step 4: 消失检测 (filtered_snapshot_ids set diff)
    └── 写入 freshness_report.json
    │
    ▼
Step 5: update_state_tracker(last_successful_sync, previous_id_set)

失败分支:
  EMPTY_ABORT (0行) → empty_snapshot_warning, 不写 tracker, 不进入 trade calendar / wave3 / disappearance
  API_FAILED → 终止, 不写 tracker, 不进入 trade calendar / wave3 / disappearance
  wave3 异常 → 回滚 ledger+canonical+trace, 删 import_csv+rejected, 不写 tracker / freshness
```

### 1. 持久化构件

#### 1.1 TuShare API — 外部数据源（PRD A 已实现）

| 属性 | 值 |
|---|---|
| 接口 | `cb_call` — 可转债强赎公告 |
| 获取方式 | 每次全量拉取 2019-01-01 至今日（~2000 行）。Snapshot API，无 changelog |
| 封装层 | `tushare_provider.TuShareProvider.fetch_and_map_redemption_events()`，内部完成 API 调用 + `call_type="强赎"` 过滤 + `cb_basic` join + 字段映射 |
| 重复处理 | 重复 `source_native_event_id` 全拒绝（不 ingesting），写入 rejected trace |
| 出错处理 | `_handle_exception` 透传 → 编排出层捕获为 `FetchResult.status="API_FAILED"` |

`redemption_fetcher.py` 不感知 TuShare 字段名，只调用 provider 接口。字段映射定义在 provider 内部。

#### 1.2 `manual_events.csv` — Append-only 指令日志（PRD B 待实现）

**当前状态：未实现。** 由后续 PRD B 追加。

设计目标概要（来自 issue #13）：CLI 追加 `--command DECLARE/CANCEL`，Reduce-then-apply 模式，与 PRD A 的 `process_ingress_to_ledger` 集成。

#### 1.3 Source 间冲突解决（PRD C 待实现）

**当前状态：未实现。** 由后续 PRD C 追加。

**关于 Snapshot Absence Reconciliation 的架构声明（来自 PRD A）：**

TuShare `cb_call` 返回的是历史既成事实（某转债在某个日期发生了强赎）。这是一个不可撤销的企业行为。不存在 "TuShare 上月说有强赎，本月说没有" 的情形。因此：

- **本系统不做负向对账（absence reconciliation）**。已确认进入 ledger 的事件除非被 correction 替代，否则不会因为从 TuShare snapshot 消失而自动撤回。
- 如果出现超量事件从 snapshot 消失（理论上不可能），触发消失检测告警，人工介入。
- PRD C 的 manual 纠偏逻辑走 `source_priority`（manual > tushare）而非 reconciliation 对账。

#### 1.4 Ledger — 持久化 Revision 账本（PRD A 已实现，5 值枚举预留）

| 属性 | 值 |
|---|---|
| 文件 | `data/redemption_event_ledger.csv` |
| 性质 | Append-only。从不删行 |
| 唯一真相源 | Post-ingestion 唯一事实源 |

```python
LEDGER_COLUMNS = [
    "event_id",               # source + ":" + source_native_event_id
    "revision",               # 同 identity 下从 0 递增
    "is_active_revision",     # True=参与 canonical 推导
    "revision_reason",        # ACTIVE | CORRECTED | CANCELLED | SUPERSEDED | LEGACY
    "source_native_event_id",
    "bond_code",
    "announcement_date",
    "delisting_date",
    "source",
    "updated_at",
]
```

`revision_reason` 枚举：

| 值 | 含义 | 由哪个 PRD 写入 |
|---|---|---|
| `ACTIVE` | 当前活跃 revision | PRD A |
| `CORRECTED` | 被 correction 替代的旧 revision | PRD A |
| `LEGACY` | 历史兼容占位（列缺失时回填 `is_active=False` 的行），不隐含 correction 语义 | PRD A |
| `CANCELLED` | 用户 CANCEL 命令产生的 tombstone | PRD B（已预留） |
| `SUPERSEDED` | manual DECLARE 自动覆盖 TuShare 事件 | PRD C（已预留） |

**Revision invariant:** At most one active revision per event_id。0 active 为正常（cancelled/superseded）。

### 2. 中间产物

#### 2.1 Import CSV（PRD A 已实现，6 列）

| 属性 | 值 |
|---|---|
| 文件 | `data/redemption_event_facts_import.csv` |
| 性质 | 每轮 pipeline 重新生成。临时 fetch 产物，不属于 rollback truth；wave3 失败时删除 |

```python
# PRD A: 仅包含 TuShare 映射后数据（6 列）
IMPORT_COLUMNS = ["source_native_event_id", "bond_code", "announcement_date", "delisting_date", "source", "updated_at"]
```

注：`is_cancelled` 列由后续 PRD B 添加（7 列），同时引入 manual rows + cancellation rows。

#### 2.2 State Tracker（PRD A 新增）

| 属性 | 值 |
|---|---|
| 文件 | `data/redemption_fetcher_state.json` |
| 用途 | 仅记录 `last_successful_sync` 和 `previous_id_set`（消失检测基线）。不参与查询范围决策 |
| 写入者 | `run_redemption_sync_pipeline()` |

#### 2.3 Freshness Report（PRD A 新增）

| 属性 | 值 |
|---|---|
| 文件 | `data/reports/freshness_report.json` |
| 用途 | `empty_snapshot_warning` + `disappearance_warning`（仅观测，不干预 ledger） |
| 写入者 | `run_redemption_sync_pipeline()`（成功时 overwrite，失败路径不写） |

#### 2.4 Rejected Trace（PRD A 新增）

| 属性 | 值 |
|---|---|
| 文件 | `data/reports/redemption_fetcher_rejected.json` |
| 用途 | 记录重复 identity 被拒绝的原始行数据 |
| 语义 | 观测产物，不是 rollback truth source；wave3 失败时删除，下一轮重新生成 |

### 3. 派生产物（PRD A 不变）

#### 3.1 Canonical State
```python
CANONICAL_COLUMNS = ["date", "bond_code", "redeem_risk", "representative_event_id",
    "representative_revision", "contributing_event_count"]
```

注：`source_priority`（manual > tushare）排序需 PRD C 追加。

#### 3.2 Trace
`data/reports/redemption_event_trace.json`，由 `run_redemption_wave3_pipeline()` 写入。

### 4. 编排与原子性（PRD A 新增）

`run_redemption_sync_pipeline()` 定义在 `etl/redemption_fetcher.py`，由它独占运行时 gate 与提交顺序：

```
Step 1: fetch_and_build_import_csv()
  └── provider.fetch_and_map_redemption_events()
  ├── 负责写 fetch 产物: import_csv + rejected trace
  ├── OK → 继续
  ├── EMPTY_ABORT → 终止, empty_snapshot_warning, 不写 tracker, 不进入 Step 2+
  └── API_FAILED → 终止, 不写 tracker, 不进入 Step 2+

Step 2: 推导 target_dates = BOOTSTRAP_START_DATE→today 交易日

Step 3: backup truth sources with adjacent `.bak` sidecars
  ├── ledger.csv(.bak)
  ├── canonical.csv(.bak)
  └── trace.json(.bak)
  └── run_redemption_wave3_pipeline()
      ├── 成功 → 删除 `.bak` sidecars, 关闭 commit boundary
      └── 异常 → 恢复三份 truth sources
                 删除 import_csv + rejected trace
                 不写 freshness_report
                 不写 state tracker
                 终止返回 `WAVE3_FAILED`

Step 4: 消失检测 (set diff filtered_snapshot_ids)

Step 5: update_state_tracker()
```

这里的 rollback truth sources 仅限：ledger、canonical、wave3 trace。Import CSV 与 rejected trace 只是本轮 fetch 的临时/观测输出，不构成 committed baseline。

### 5. Identity 合约

```python
# source_native_event_id (TuShare 来源):
source_native_event_id = f"{ts_code.replace('.','')}_{ann_date}"
# 示例: "118033SH_20260514" (ts_code 去点号 + 下划线 + ann_date)

# event_id (ledger 级):
event_id = f"{source}:{native_id}"
# 示例: "tushare:118033SH_20260514"
```

### 6. 已实现的 revision 路径

| 场景 | 行为 |
|---|---|
| 新 identity 首次出现 | `revision_reason="ACTIVE"`, `is_active_revision=True` |
| 同数据重复出现 | Dedup，不产生新 revision |
| 同 identity 不同数据 | 旧 → `"CORRECTED"/False`；新 → `"ACTIVE"/True` |
| 历史 ledger 列缺失 | `is_active=True` → `"ACTIVE"`；`is_active=False` → `"LEGACY"` |

---

## 未来阶段（PRD B/C 待实现）

### PRD B — Manual Event Injection

- 新增 `manual_events.csv` append-only 指令日志 + `manual_redemption_inject.py` CLI
- `IMPORT_COLUMNS` 扩展为 7 列（+ `is_cancelled`）
- `process_ingress_to_ledger` 新增 `is_cancelled=True, source=manual` → 写 `revision_reason="CANCELLED"`
- 引入 cancellation rows
- DEPENDS ON: PRD A（identity 合约、provider 接口、编排框架）

### PRD C — Data Source Integration

- `derive_canonical_redemption_state` 增加 `source_priority`（manual > tushare）排序
- `process_ingress_to_ledger` 新增 SUPERSEDED 分支（`generate_supersede_rows` 等）
- TuShare API 失败降级（freshness FAILED 时已有 ledger 推导 canonical）
- `migrate_legacy_revision_reasons()` 脚本将 LEGACY 行重写为准确值
- DEPENDS ON: PRD A + PRD B

---

## 版本记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-05-14 | 初始版本（原始大 PRD 时期） |
| v2.0 | 2026-05-14 | PRD A 落地后更新：移除增量方案、Supersession、Manual 注入描述；新增编排、原子提交、消失检测、LEGACY 枚举、absence 声明 |
