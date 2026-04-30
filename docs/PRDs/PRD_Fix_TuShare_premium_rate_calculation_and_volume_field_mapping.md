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
1. 只修改 `etl/tushare_provider.py`，不修改其他文件。
2. 不改变 JQDataProvider 或其他 provider 的行为。
3. 不改变 `fetch_cb_daily()` 和 `fetch_cb_price_changes()` 的接口签名。

### Boundaries
**In Scope**
- `vol → volume` 字段重命名
- premium_rate 计算路径修复
- 对应单元测试更新

**Out of Scope**
- Redemption gap 分析
- 改进 stock daily 数据获取效率
- 其他 provider 的修改

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Target File
只修改：`/root/projects/AMS/etl/tushare_provider.py`

### 3.2 volume 字段映射修复
在 `fetch_cb_daily()` 的 DataFrame 处理部分增加一行 rename：

```python
df = df.rename(columns={"vol": "volume"})
```

### 3.3 premium_rate 计算修复
当前代码存在三段 `cb_over_rate` fallback 引用，均须移除。改用纯计算路径：

#### 数据链
1. `fetch_cb_daily()` → bond_close
2. `cb_price_chg` → effective_conv_price（通过 merge_asof 获取每个交易日有效的转股价）
3. `daily()` → stock_close
4. 计算：`premium_rate = (bond_close / ((100 / effective_conv_price) × stock_close) - 1) × 100`

注意点：
- 确保在每日数据上使用正确的有效转股价，而不是单一静态值
- 如果某个交易日缺少 stock_close 或 effective_conv_price，该交易日的 premium_rate 应为空（不填默认值）
- 参考 PRD_CB_ETL_Audit_Report_Mode 的 source contract：禁止用默认值伪造关键字段

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: volume field is properly mapped**
  - **Given** TuShareProvider.fetch_cb_daily() returns data
  - **When** the result DataFrame is inspected
  - **Then** it must contain a `volume` column (not `vol`)
  - **And** the data values in `volume` must match the original `vol` values

- **Scenario 2: premium_rate is calculated correctly for a known week**
  - **Given** a valid trading week (2025-01-20 to 2025-01-24)
  - **When** `TuShareProvider.fetch_cb_price_changes()` is called
  - **Then** the result must contain non-empty `premium_rate` values
  - **And** `missing_premium_ratio` must be < 0.20

- **Scenario 3: E2E ETL audit with TuShare passes Stage C and F**
  - **Given** the fix is deployed
  - **When** `python3 -m etl.cb_etl_runner --data-source tushare --start 2025-01-20 --end 2025-01-24 --audit`
  - **Then** Stage C must NOT be classified as `PREMIUM_RATE_MISSING_BROAD_COVERAGE`
  - **And** Stage F must show `schema_validator_status == PASS`
  - **And** `volume` must not appear in missing column reasons

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- 单元测试覆盖 `vol → volume` 重命名
- 单元测试覆盖 premium_rate 计算（mock 输入值，验证公式输出）
- E2E 黑盒测试：修复后对 2025-01-20 ~ 2025-01-24 窗口跑一次真实 TuShare audit runner，确认 Stage C 和 Stage F 通过
- 不依赖 JQData 交叉比对，仅验证 TuShare 自身数据完整性和计算正确性

## 6. Framework Modifications (框架防篡改声明)
- `/root/projects/AMS/etl/tushare_provider.py`（`fetch_cb_daily` 和 `fetch_cb_price_changes` 方法）

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

- **`no_cb_over_rate_guard`**
```text
cb_daily API does not provide a cb_over_rate field. premium_rate must be computed from bond_close, stock_close, and effective_conv_price.
```
