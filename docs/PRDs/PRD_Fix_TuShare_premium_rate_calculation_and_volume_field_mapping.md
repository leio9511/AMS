---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix TuShare Full-Ticker Contract, premium_rate Reconstruction, and volume Mapping

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

进一步诊断后发现，真正的根问题不是 TuShare 缺数据，而是 provider 与 pipeline 的**方法边界契约**仍然含糊：

### Problem A — 当前 provider 边界仍然接收“半成品标识”
`CBETLPipeline` 在进入 Stage C 后当前持有的是：
- `bond_code_raw`（例如 `127076`）
- `bond_exchange_code`（例如 `SZ` / `SH`）

而 TuShare provider 的外部查询天然基于：
- `ts_code` / full ticker（例如 `127076.SZ`）

之前的 PRD 试图让 provider 在内部“恢复”出 `ts_code`。Auditor 指出这会形成隐藏 side-channel：
- coder 需要猜 provider 是否允许 raw code 输入；
- provider 需要偷偷依赖缓存推断后缀；
- 一旦 raw code 恢复规则变化，Stage C 仍会无声失败。

### Problem B — premium_rate 修复若不先修边界契约，公式仍可能拿不到源数据
目前已知：
- `cb_daily` API 没有 `cb_over_rate`
- premium_rate 必须通过 `bond_close + stock_close + effective_conv_price` 重建

但如果 pipeline 仍然只把 raw code 传到 provider 边界，provider 仍可能拿不到：
- 正确的债券日线 `cb_daily`
- 正确的转股价变动 `cb_price_chg`
- 正确的 bond ↔ stock 映射

那公式再正确也无法产出 premium_rate。

### Problem C — `volume` 缺失是 canonical schema normalization 漏项
TuShare `cb_daily` 返回 `vol`，AMS canonical schema 需要 `volume`。这是 provider 输出归一化的一部分。

### 核心问题定义
> 这次修复的本质不是“补两个字段”，而是把 `CBETLPipeline` 与 provider 的边界正式改为 **full ticker contract**：pipeline 向 provider 传完整债券代码（如 `127076.SZ`），provider 不再隐式从 raw code 猜测后缀；在这个明确边界之上，再完成 `premium_rate` 的 provider-side 重建与 `vol → volume` 的 canonical schema 映射。

## 2. Requirements & User Stories (需求定义)

### Functional Requirements
1. `CBETLPipeline` 与 provider 的边界必须正式统一为 **full ticker contract**。
2. `CBETLPipeline` 在调用 provider 获取债券价格和转股价变动时，不得再传递“仅 raw code”的半成品标识；必须传递完整 ticker（例如 `127076.SZ`）。
3. `BaseDataProvider` 必须把其相关方法契约写死为接收 full ticker，而不是让实现类自行猜测 raw code 是否可接受。
4. 该 contract 至少必须覆盖以下方法边界：
   - `fetch_cb_daily(...)`
   - `fetch_cb_price_changes(...)`
5. `TuShareProvider.fetch_cb_daily()` 必须将 TuShare 的 `vol` 字段重命名为 `volume`。
6. `TuShareProvider.fetch_cb_price_changes()` 必须移除对不存在的 `cb_over_rate` 字段的引用。
7. `TuShareProvider.fetch_cb_price_changes()` 必须使用以下公式重建 premium_rate：
   `premium_rate = (bond_close / ((100 / effective_conv_price) × stock_close) - 1) × 100`
8. premium 计算必须支持历史转股价变化，不能使用静态最新 `conv_price` 覆盖全历史窗口。
9. 若 bond/date 缺少 `stock_close` 或 `effective_conv_price`，该行 `premium_rate` 必须保持 `NaN`，不得填 fallback 数值。
10. 对 provider 而言，不允许再承担“从 raw code 猜完整 ticker 后缀”的隐式责任；full ticker 的拼装必须在 provider 边界之前完成。
11. 修复后，TuShare audit 路径必须满足：
   - Stage C 不再因 provider bug 出现 `missing_premium_ratio = 1.0`
   - Stage F 不再因缺少 `volume` 字段失败

### Non-Functional Requirements
1. 目标文件：
   - `etl/cb_etl_pipeline.py`
   - `etl/cb_provider_base.py`
   - `etl/tushare_provider.py`
   - `etl/jqdata_provider.py`（如 provider contract 变化需要同步适配）
   - `tests/test_tushare_provider.py`
   - 如有必要，可补充 provider contract 测试文件，但不得扩散到策略/Broker/Runner 层
2. 不改变 Strategy、Broker、Runner 或 `BaseDataFeed` 层的主接口。
3. 不允许通过默认值注入掩盖 contract failure。
4. provider 与 pipeline 的接口含义必须在文档与测试中完全一致，不允许出现“文档接收 full ticker、实现实际仍接收 raw code”的双重语义。

### User Stories
- 作为 Boss，我希望 TuShare 路径能真正生成可用于回测的 canonical dataset，而不是只在表面上“接上了 provider”。
- 作为 Manager，我希望 provider 边界只接收一种明确的证券标识（full ticker），而不是让 coder 在 raw code / full ticker 之间自行脑补。
- 作为 Reviewer/Auditor，我希望本次修复先把接口契约改正，再修公式和字段映射，避免再次出现“症状修复但根因还在”的 PR。

### Boundaries
**In Scope**
- pipeline → provider 的 full ticker contract
- `vol → volume` 字段映射
- premium_rate 重建路径修复
- 对应单元测试更新（`tests/test_tushare_provider.py`）
- 对小窗口 TuShare audit 的黑盒验收

**Out of Scope**
- Redemption gap 分析
- 改进 stock daily 获取效率
- 其他 provider 的新功能扩展
- JQData 精度对照验证

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Target Files
- `etl/cb_etl_pipeline.py`
- `etl/cb_provider_base.py`
- `etl/tushare_provider.py`
- `etl/jqdata_provider.py`（如 provider contract 变化需要同步适配）
- `tests/test_tushare_provider.py`

### 3.2 Provider Boundary Contract: full ticker only
这次修复的关键决策是：

> **pipeline 与 provider 的边界统一为 full ticker contract。**

也就是说，provider 边界相关方法不再接受“仅 raw code”的半成品标识。应统一使用如下完整标识：
- `127076.SZ`
- `110092.SH`

#### 规范定义
- `CBETLPipeline` 在调用 provider 获取债券价格与转股价变动前，必须先把现有的 `bond_code_raw` + `bond_exchange_code` 组装成 full ticker；
- `BaseDataProvider` 的相关方法契约必须以 full ticker 作为输入语义；
- `TuShareProvider` 与 `JQDataProvider` 都只消费 full ticker，不再承担“猜测后缀”的隐式职责。

#### 受影响方法边界
至少包括：
- `fetch_cb_daily(tickers, start_date, end_date)`
- `fetch_cb_price_changes(tickers, start_date, end_date)`

其中 `tickers` 的语义必须被正式定义为：
> full ticker list（例如 `['127076.SZ', '110092.SH']`），而不是 raw code list。

#### 失败策略
- 如果 pipeline 侧无法拼装出完整 ticker，则该 bond/date 不得进入 provider 查询；
- 不允许 provider 从隐藏缓存中猜测后缀来补洞；
- 对无法形成完整 ticker 的记录，下游 premium_rate 应自然保持 `NaN`，并由 pipeline 的 missing-premium 统计接管。

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
1. `fetch_cb_daily()` 接收 full ticker，返回 `bond_close`
2. `fetch_cb_price_changes()` 接收 full ticker，返回 `effective_conv_price`
3. `daily()` 通过 `cb_basic` 中的 `stk_code` 获取 `stock_close`
4. 计算：`premium_rate = (bond_close / ((100 / effective_conv_price) × stock_close) - 1) × 100`

#### Contract 要求
- 必须用交易日有效的 `effective_conv_price`；
- 不得回落到任何不存在的字段；
- 缺少 `stock_close` 或 `effective_conv_price` 时，结果保持 `NaN`；
- 不允许填默认值掩盖 provider contract failure；
- provider 内部允许把 full ticker 拆分为 raw code / exchange 去适配上游 API，但该拆分必须是确定性的、显式的、由 full ticker 驱动，而不是从 raw code 反向猜测。

### 3.5 Rollback Strategy (回滚方案)
回滚路径：
1. **代码回滚**：`git revert <merge_commit>` 恢复修复前版本；
2. **验后退回**：merge 后 deploy 前，必须执行一次：
   `python3 -m etl.cb_etl_runner --data-source tushare --start 2025-01-20 --end 2025-01-24 --audit`
3. 若该 audit 仍出现以下任一结果，则不部署并回滚：
   - Stage C 继续因 provider bug 出现全量 premium 缺失；
   - Stage F 继续因缺少 `volume` 失败；
   - full ticker contract 未被正确执行，导致 provider 无法取得核心数据。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
### Provider-level
- **Scenario 1: TuShare daily-price retrieval exposes canonical volume field**
  - **Given** a valid TuShare price window of `2025-01-20` to `2025-01-24`
  - **When** the TuShare daily-price retrieval path is executed with full tickers
  - **Then** the resulting DataFrame must expose a `volume` column
  - **And** the `volume` values must equal the source API's original `vol` values for the same rows

- **Scenario 2: Provider boundary accepts full tickers and retrieves non-empty bond source data**
  - **Given** a list of known active bond full tickers such as `127076.SZ`
  - **When** the provider executes bond-price and conversion-price retrieval
  - **Then** it must obtain non-empty source data for those bonds in the requested window

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
- 单元测试覆盖 pipeline 侧 full ticker contract（确保不再把 raw-only code 直接传入 provider）；
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
