---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix TuShare Ticker Normalization Contract, premium_rate Reconstruction, and volume Mapping

## 1. Context & Problem (业务背景与核心痛点)
AMS 已经完成了多 provider 的 CB ETL 抽象，并且 TuShare 路径已经具备：
- 可转债基础信息：`cb_basic`
- 可转债日线：`cb_daily`
- 转股价变动：`cb_price_chg`
- ST 列表：`stock_st`

同时，`cb_daily` 的按 `trade_date` 查询策略也已经修复，TuShare 路径的 Stage A（price source acquisition）已能正常返回数据。

然而，最近一次 TuShare audit 暴露出两个表面症状：
1. Stage C premium_rate 全部缺失；
2. Stage F validator 因缺少 `volume` 字段失败。

进一步诊断后发现，真正的根问题不是 TuShare 缺数据，而是：

### Problem A — pipeline 与 TuShare provider 的 ticker contract 未明确
`CBETLPipeline` 在进入 Stage C 之后使用的是规范化过的：
- `bond_code_raw`（例如 `127076`）
- `bond_exchange_code`（例如 `SZ`）

而 TuShare provider 的内部查询能力天然基于：
- `ts_code`（例如 `127076.SZ`）

当前 PRD 只针对字段名和公式做修补，但没有明确写死：
> 当 pipeline 传入 raw bond code 时，TuShareProvider 如何恢复为 TuShare 需要的完整 `ts_code`，以及这个恢复在哪些数据链路上必须生效。

如果这个 contract 不定义清楚，那么即使：
- `vol → volume` 映射修了；
- `cb_over_rate` 幻觉 fallback 删了；

provider 仍可能因为拿不到正确的 `ts_code`，导致：
- `cb_daily` 查不到正确债券价格；
- `cb_price_chg` 查不到正确转股价变动；
- `bond → stock` 映射链路断裂；
- premium_rate 继续为空。

### Problem B — 当前 premium_rate 修复是 contract-blind fix
目前已知：
- `cb_daily` API 没有 `cb_over_rate`
- premium_rate 必须通过 `bond_close + stock_close + effective_conv_price` 重建

但如果输入标识仍是错误的 raw code，公式再正确也无法拿到正确的源数据。

### Problem C — `volume` 缺失是 schema normalization 漏项
TuShare `cb_daily` 返回 `vol`，AMS canonical schema 需要 `volume`。这是 provider contract normalization 的一部分。

### 核心问题定义
> 这次修复的本质不是“补两个字段”，而是要补齐 `CBETLPipeline` 与 `TuShareProvider` 之间的 ticker normalization contract；在该 contract 正确建立后，再完成 `premium_rate` 的 provider-side 重建与 `vol → volume` 的 canonical schema 映射。

## 2. Requirements & User Stories (需求定义)

### Functional Requirements
1. `TuShareProvider` 必须明确定义并实现 pipeline raw bond code 到 TuShare `ts_code` 的归一化策略。
2. 该归一化策略至少必须覆盖：
   - `bond_code_raw + bond_exchange_code -> ts_code`
   - `cb_basic` 内部缓存 / 映射时使用完整 `ts_code`
   - `fetch_cb_daily()` 对债券价格查询使用完整 `ts_code`
   - `fetch_cb_price_changes()` 对转股价变动查询使用完整 `ts_code`
3. 如果某个 raw bond code 无法恢复成完整 `ts_code`，provider 必须 fail-closed：
   - 不得伪造默认值
   - 不得 silent skip 为成功
   - 下游 premium_rate 对应行必须自然保持 `NaN`
4. `TuShareProvider.fetch_cb_daily()` 必须将 TuShare 的 `vol` 字段重命名为 `volume`。
5. `TuShareProvider.fetch_cb_price_changes()` 必须移除对不存在的 `cb_over_rate` 字段的引用。
6. `TuShareProvider.fetch_cb_price_changes()` 必须使用以下公式重建 premium_rate：
   `premium_rate = (bond_close / ((100 / effective_conv_price) × stock_close) - 1) × 100`
7. premium 计算必须支持历史转股价变化，不能使用静态最新 `conv_price` 覆盖全历史窗口。
8. 若 bond/date 缺少 `stock_close` 或 `effective_conv_price`，该行 `premium_rate` 必须保持 `NaN`，不得填 fallback 数值。
9. 修复后，TuShare audit 路径必须满足：
   - Stage C 不再因 provider bug 出现 `missing_premium_ratio = 1.0`
   - Stage F 不再因缺少 `volume` 字段失败

### Non-Functional Requirements
1. 目标文件：
   - `etl/tushare_provider.py`
   - `tests/test_tushare_provider.py`
2. 不改变 JQDataProvider 或其他 provider 的行为。
3. 不改变 `CBETLPipeline` 对外接口签名。
4. 不允许通过默认值注入掩盖 contract failure。

### User Stories
- 作为 Boss，我希望 TuShare 路径能真正生成可用于回测的 canonical dataset，而不是只在表面上“接上了 provider”。
- 作为 Manager，我希望 raw code 与 ts_code 的转换规则被写死，而不是让 coder 自己脑补。
- 作为 Reviewer/Auditor，我希望本次修复先补 contract，再补公式和字段映射，避免再次出现“症状修复但根因还在”的 PR。

### Boundaries
**In Scope**
- raw code ↔ ts_code 的归一化策略
- `vol → volume` 字段映射
- premium_rate 重建路径修复
- 对应单元测试更新（`tests/test_tushare_provider.py`）
- 对小窗口 TuShare audit 的黑盒验收

**Out of Scope**
- Redemption gap 分析
- 改进 stock daily 获取效率
- 其他 provider 的修改
- JQData 对照验证

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Target Files
- `etl/tushare_provider.py`
- `tests/test_tushare_provider.py`

### 3.2 Ticker Normalization Contract
必须在 `TuShareProvider` 中明确并固化以下 contract：

#### 输入侧
Pipeline 提供：
- `bond_code_raw`（如 `127076`）
- `bond_exchange_code`（如 `SZ` / `SH`）

#### Provider 内部规范化输出
Provider 必须恢复并使用：
- `ts_code = f(bond_code_raw, bond_exchange_code)`
- 例如：`127076 + SZ -> 127076.SZ`

#### 应用位置
该 normalization 必须应用于：
1. bond daily 价格查询
2. cb_price_chg 转股价变动查询
3. provider 内部 bond ↔ stock 映射缓存/查找

#### 失败策略
如果任何一步无法恢复 `ts_code`：
- 该 bond/date 的 provider 输出不得伪造数据；
- premium_rate 必须保持 `NaN`；
- downstream 由 pipeline 的既有 missing-premium 统计与 audit 分类接管。

### 3.3 volume 字段映射修复
在 `fetch_cb_daily()` 的 DataFrame 处理部分增加：

```python
df = df.rename(columns={"vol": "volume"})
```

要求：
- provider 输出必须对齐 AMS canonical schema；
- 不允许把 `vol` 留给下游自己猜测。

### 3.4 premium_rate 重建修复
当前代码存在 `cb_over_rate` 幻觉 fallback，必须全部移除。改用纯 provider-side 重建路径：

#### 数据链
1. `fetch_cb_daily()` → `bond_close`
2. `cb_price_chg` → `effective_conv_price`（通过 `merge_asof` 获取交易日有效转股价）
3. `daily()` → `stock_close`
4. 计算：`premium_rate = (bond_close / ((100 / effective_conv_price) × stock_close) - 1) × 100`

#### Contract 要求
- 必须用交易日有效的 `effective_conv_price`；
- 不得回落到任何不存在的字段；
- 缺少 `stock_close` 或 `effective_conv_price` 时，结果保持 `NaN`；
- 不允许填默认值掩盖 provider contract failure。

### 3.5 Rollback Strategy (回滚方案)
回滚路径：
1. **代码回滚**：`git revert <merge_commit>` 恢复修复前版本；
2. **验后退回**：merge 后 deploy 前，必须执行一次：
   `python3 -m etl.cb_etl_runner --data-source tushare --start 2025-01-20 --end 2025-01-24 --audit`
3. 若该 audit 仍出现以下任一结果，则不部署并回滚：
   - Stage C 继续因 provider bug 出现全量 premium 缺失；
   - Stage F 继续因缺少 `volume` 失败；
   - raw code → ts_code 恢复失败导致 provider 无法取得核心数据。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
### Provider-level
- **Scenario 1: TuShare daily-price retrieval exposes canonical volume field**
  - **Given** a valid TuShare price window of `2025-01-20` to `2025-01-24`
  - **When** the TuShare daily-price retrieval path is executed
  - **Then** the resulting DataFrame must expose a `volume` column
  - **And** the `volume` values must equal the source API's original `vol` values for the same rows

- **Scenario 2: TuShare provider reconstructs full ts_code from pipeline raw bond code inputs**
  - **Given** pipeline-style inputs containing `bond_code_raw` and `bond_exchange_code`
  - **When** the TuShare provider executes bond-price and conversion-price retrieval
  - **Then** the provider must successfully obtain non-empty source data for bonds that are known to trade in the requested window

- **Scenario 3: TuShare premium reconstruction yields observable premium_rate values for bonds with conversion-price history**
  - **Given** one or more convertible bonds that have valid `cb_price_chg` history and matching bond/stock daily prices in the same date window
  - **When** the TuShare premium reconstruction path is executed
  - **Then** the resulting records must contain non-null `premium_rate` values for those bond-date rows

- **Scenario 4: TuShare premium reconstruction fails closed when conversion-price history is unavailable**
  - **Given** a convertible bond/date combination with missing effective conversion-price history
  - **When** the TuShare premium reconstruction path is executed
  - **Then** the resulting `premium_rate` for those rows must remain `NaN`
  - **And** no fallback numeric value may be injected

### Pipeline / Audit-level
- **Scenario 5: TuShare audit runner no longer fails because of missing volume schema**
  - **Given** the fix is deployed
  - **When** `python3 -m etl.cb_etl_runner --data-source tushare --start 2025-01-20 --end 2025-01-24 --audit` is executed
  - **Then** Stage F must not fail due to a missing `volume` column

- **Scenario 6: TuShare audit runner no longer reports complete premium absence caused by provider bug**
  - **Given** the same deployed fix and audit window
  - **When** the audit report is produced
  - **Then** Stage C must not report `missing_premium_ratio = 1.0` caused by provider-side premium reconstruction failure

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- 单元测试覆盖 raw code ↔ ts_code normalization；
- 单元测试覆盖 `vol → volume` 重命名；
- 单元测试覆盖 premium_rate 计算（mock 输入值，验证公式输出）；
- 单元测试覆盖无 `cb_price_chg` 历史时返回 `NaN` 的 fail-closed 行为；
- E2E 黑盒测试：修复后对 `2025-01-20 ~ 2025-01-24` 窗口跑一次真实 TuShare audit runner，确认 Stage C 不再因 provider bug 全空、Stage F 不再因缺少 `volume` 失败；
- 不依赖 JQData 交叉比对，仅验证 TuShare 自身数据完整性和 provider contract 正确性。

## 6. Framework Modifications (框架防篡改声明)
- `/root/projects/AMS/etl/tushare_provider.py`（`fetch_cb_daily` 和 `fetch_cb_price_changes` 路径）
- `/root/projects/AMS/tests/test_tushare_provider.py`（测试更新）

---

## Appendix: Architecture Evolution Trace (架构演进与追踪审查)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]**

- **v1.0**: 基于现场验证结果，两个 bug 均非 TuShare 数据缺失，而是代码映射问题。
- **v2.0**: Auditor 指出这是 contract-blind fix；因此将问题定义升级为“先补 provider ↔ pipeline 的 ticker normalization contract，再修 premium 与 volume”。

---

## 7. Hardcoded Content (硬编码内容)
### Exact Text Replacements:
- **`volume_rename`**
```text
rename(columns={"vol": "volume"})
```

- **`premium_formula`**
```text
premium_rate = (bond_close / ((100 / effective_conv_price) * stock_close) - 1) * 100
```

- **`no_cb_over_rate_guard_comment` (放在 `fetch_cb_price_changes` 开头的注释)**
```python
# cb_daily API does not provide a cb_over_rate field.
# premium_rate must be computed from bond_close, stock_close, and effective_conv_price.
```
