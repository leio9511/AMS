---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix TuShare premium_rate Calculation and volume Field Mapping

## 1. Context & Problem (业务背景与核心痛点)
`TuShareProvider` 的 cb_daily 查询策略已在 PRD_Fix_TuShare_cb_daily_Query_Strategy 中修复并部署，价格数据已能正常收取（Stage A 通过）。但还有两个代码缺陷导致 Stage C（Premium Join）和 Stage F（Validator）无法通过。

### 缺陷 1：cb_daily 没映射 volume 字段名
TuShare 的 cb_daily 接口返回的成交量为 `vol`，但 AMS canonical schema 期望的字段名为 `volume`。

`TuShareProvider.fetch_cb_daily()` 目前直接返回 TuShare 原始字段名，没有做 `vol → volume` 的 rename。这导致 downstream Stage F 中的 validator 在索引 `CANONICAL_CB_COLUMNS` 时找不到 `volume` 字段，报 `['volume'] not in index`。

这不是 TuShare 数据不全，是代码遗漏了字段映射。

### 缺陷 2：fetch_cb_price_changes 引用了不存在的字段 cb_over_rate
`TuShareProvider.fetch_cb_price_changes()` 在 premium_rate 推算路径中，当主路径因某种原因无法完成时，使用 `bond_daily["cb_over_rate"]` 作为 fallback。

但 TuShare 的 `cb_daily` 接口 **根本没有 `cb_over_rate` 字段**。cb_daily 的返回字段为：
```text
ts_code, trade_date, pre_close, open, high, low, close, change, pct_chg, vol, amount
```

代码尝试读取不存在的 `cb_over_rate` 列会导致 KeyError（被异常处理器吞掉并返回空 DataFrame），整条 premium 计算路径因此崩塌。

这不是 TuShare 数据不全。TuShare 实际提供所有需要的原料字段：
- `cb_daily.close`：可转债收盘价
- `daily(ts_code=...).close`：正股收盘价
- `cb_price_chg.convertprice_aft`：有效转股价

premium_rate 可以通过以下公式直接计算，不需要任何 fallback：
```text
premium_rate = (bond_close / ((100 / effective_conv_price) × stock_close) - 1) × 100
```

### 核心问题定义
> `TuShareProvider` 存在两个代码级的数据映射缺陷：`vol → volume` 字段名未映射，以及 premium 计算路径引用了不存在的 fallback 字段。修复这两个缺陷后，TuShare 路径的 ETL 即可完整通过 Stage A~F（仅 redemption gap 为已知独立问题）。

## 2. Requirements & User Stories (需求定义)

### Functional Requirements
1. `TuShareProvider.fetch_cb_daily()` 必须将 TuShare 的 `vol` 字段重命名为 `volume`。
2. `TuShareProvider.fetch_cb_price_changes()` 必须移除对不存在的 `cb_over_rate` 字段的引用。
3. `TuShareProvider.fetch_cb_price_changes()` 必须使用以下公式重建 premium_rate：
   `premium_rate = (bond_close / ((100 / effective_conv_price) × stock_close) - 1) × 100`
4. premium 计算必须支持历史转股价变化，不能仅使用静态最新 conv_price。
5. 修复后，以下条件必须同时满足：
   - Stage C 的 `missing_premium_ratio` < 0.20
   - Stage F 的 `schema_validator_status = PASS`
   - `volume` 列在 validator 输入中正常存在

### Non-Functional Requirements
1. 目标文件：`etl/tushare_provider.py`；配套文件：`tests/test_tushare_provider.py`。
2. 不改变 JQDataProvider 或其他 provider 的行为。
3. 不改变 `fetch_cb_daily()` 和 `fetch_cb_price_changes()` 的接口签名。


### Boundaries
**In Scope**
- `vol → volume` 字段重命名
- premium_rate 计算路径修复
- 明确无 `cb_price_chg` 历史记录时的 premium_rate 处理策略
- 对应单元测试更新（`tests/test_tushare_provider.py`）

**Out of Scope**
- Redemption gap 分析
- 改进 stock daily 数据获取效率
- 其他 provider 的修改

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Target Files
- `etl/tushare_provider.py`（核心修复）
- `tests/test_tushare_provider.py`（测试更新）

### 3.2 volume 字段映射修复
在 `fetch_cb_daily()` 的 DataFrame 处理部分增加一行 rename：

```python
df = df.rename(columns={"vol": "volume"})
```

### 3.3 premium_rate 计算修复
当前代码存在三段 `cb_over_rate` fallback 引用，均须移除。改用纯计算路径：

#### 数据链
1. `fetch_cb_daily()` → `bond_close`
2. `cb_price_chg` → `effective_conv_price`（通过 `merge_asof` 获取每个交易日有效的转股价）
3. `daily()` → `stock_close`
4. 计算：`premium_rate = (bond_close / ((100 / effective_conv_price) × stock_close) - 1) × 100`

注意点：
- 必须在每日数据上使用正确的有效转股价，而不是单一静态值；
- 如果某个交易日缺少 `stock_close` 或 `effective_conv_price`，该交易日的 `premium_rate` 必须保持 `NaN`，不得填任何 fallback 默认值；
- 参考 `PRD_CB_ETL_Audit_Report_Mode` 的 source contract：禁止用默认值伪造关键字段；
- `cb_daily` API 不提供任何名为 `cb_over_rate` 的字段，因此 provider 内部不得再依赖该字段存在。

#### 无 `cb_price_chg` 历史记录时的处理策略
- 对于没有任何 `cb_price_chg` 历史记录的债券，如果该债券仍进入 premium 计算范围，则其 `premium_rate` 在对应日期必须保持 `NaN`；
- 不允许用静态 `cb_basic.conv_price` 覆盖全历史窗口来“伪造”完整 premium 序列；
- 此类 `NaN` 行应自然计入 downstream 的 missing-premium 统计，由 pipeline / audit runner 负责按既有规则分类，不在 provider 层偷偷吞掉。

### 3.4 Rollback Strategy (回滚方案)
本 PRD 的改动范围仅限于 `etl/tushare_provider.py` 与 `tests/test_tushare_provider.py`。

回滚路径：
1. **代码回滚**：`git revert <merge_commit>` 恢复到修复前版本；
2. **验后退回**：merge 后但 deploy 前，必须执行一次 `python3 -m etl.cb_etl_runner --data-source tushare --start 2025-01-20 --end 2025-01-24 --audit`；
3. 若该 audit 仍出现以下任一结果，则不部署并原地回滚：
   - Stage C 继续出现由 provider bug 导致的全量 premium 缺失；
   - Stage F 继续因缺少 `volume` 失败；
   - provider 抛出新的 schema / join 级异常。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
### Provider-level
- **Scenario 1: TuShare daily-price retrieval exposes canonical volume field**
  - **Given** a valid TuShare price window of `2025-01-20` to `2025-01-24`
  - **When** the TuShare daily-price retrieval path is executed
  - **Then** the resulting DataFrame must expose a `volume` column
  - **And** the `volume` values must equal the source API's original `vol` values for the same rows

- **Scenario 2: TuShare premium reconstruction yields observable premium_rate values for bonds with conversion-price history**
  - **Given** one or more convertible bonds that have valid `cb_price_chg` history and matching bond/stock daily prices in the same date window
  - **When** the TuShare premium reconstruction path is executed
  - **Then** the resulting records must contain non-null `premium_rate` values for those bond-date rows

- **Scenario 3: TuShare premium reconstruction fails closed when conversion-price history is unavailable**
  - **Given** a convertible bond/date combination with missing effective conversion-price history
  - **When** the TuShare premium reconstruction path is executed
  - **Then** the resulting `premium_rate` for those rows must remain `NaN`
  - **And** no fallback numeric value may be injected

### Pipeline / Audit-level
- **Scenario 4: TuShare audit runner no longer fails because of missing volume schema**
  - **Given** the fix is deployed
  - **When** `python3 -m etl.cb_etl_runner --data-source tushare --start 2025-01-20 --end 2025-01-24 --audit` is executed
  - **Then** Stage F must not fail due to a missing `volume` column

- **Scenario 5: TuShare audit runner no longer reports complete premium absence caused by provider bug**
  - **Given** the same deployed fix and audit window
  - **When** the audit report is produced
  - **Then** Stage C must not report `missing_premium_ratio = 1.0` caused by provider-side premium reconstruction failure

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- 单元测试覆盖 `vol → volume` 重命名；
- 单元测试覆盖 premium_rate 计算（mock 输入值，验证公式输出）；
- 单元测试覆盖无 `cb_price_chg` 历史时返回 `NaN` 的 fail-closed 行为；
- E2E 黑盒测试：修复后对 `2025-01-20 ~ 2025-01-24` 窗口跑一次真实 TuShare audit runner，确认 Stage C 不再因 provider bug 全空、Stage F 不再因缺少 `volume` 失败；
- 不依赖 JQData 交叉比对，仅验证 TuShare 自身数据完整性和 provider contract 正确性。

## 6. Framework Modifications (框架防篡改声明)
- `/root/projects/AMS/etl/tushare_provider.py`（`fetch_cb_daily` 和 `fetch_cb_price_changes` 方法）
- `/root/projects/AMS/tests/test_tushare_provider.py`（测试更新）

---

## Appendix: Architecture Evolution Trace (架构演进与追踪审查)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]**

- **v1.0**: 基于现场验证结果，两个 bug 均非 TuShare 数据缺失，而是代码映射问题。

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
