---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix TuShare cb_daily Query Strategy

## 1. Context & Problem (业务背景与核心痛点)
PRD_Multi-Provider_CB_ETL_Abstraction_and_TuShare_Integration.md 已通过 SDLC 并完成部署。`TuShareProvider` 已经实现了 `fetch_cb_daily()` 方法，但在实架审计时发现该方法无法返回任何价格数据。

### 当前状态
已验证的事实：
- `TuShareProvider.fetch_cb_basic()` 正常工作，返回 1125 只债券基础数据
- `TuShareProvider` 在 audit runner 执行时，Stage A 因 `fetch_cb_daily()` 返回空而失败
- 错误信息：`No price data found for the given range`

### 根因分析
直接调用 `tushare.pro.cb_daily(ts_code='...')` 发现：
- ✅ 传入单个 ts_code（`'127076.SZ'`）时，正常返回 5 行日线数据
- ❌ 传入逗号分隔的多个 ts_code（`'127076.SZ,127080.SZ'`）时，返回 0 行数据
- ✅ 传入 `trade_date` 参数而不传 ts_code 时，返回当日全市场 506 行数据

当前 `TuShareProvider.fetch_cb_daily()` 的实现如下：

```python
# 当前实现（不工作）
batch_size = 100
for i in range(0, len(tickers), batch_size):
    batch = tickers[i:i+batch_size]
    ts_codes = ",".join(batch)
    df = self.pro.cb_daily(ts_code=ts_codes, start_date=..., end_date=...)
```

此假设 "cb_daily 接受逗号分隔的 ts_code" 是错误的。**cb_daily 是 TuShare 中少数不支持多代码批量查询的接口。**

### 更好的替代方案已验证
`pro.cb_daily(trade_date='20250120')` 单次调用即可返回当日全部可转债日线数据（约 500 行 / 天）。

### 核心问题定义
> `TuShareProvider.fetch_cb_daily()` 使用了 cb_daily 不支持的逗号分隔 ts_code 查询方式，导致所有 CB 日线价格数据获取失败，必须改为按交易日全量拉取策略。

## 2. Requirements & User Stories (需求定义)

### Functional Requirements
1. `TuShareProvider.fetch_cb_daily()` 必须改为不依赖 `ts_code` 逗号分隔的查询方式。
2. 替代策略必须使用 `pro.cb_daily(trade_date=<date>)` 按每个交易日拉取当日全市场可转债日线数据。
3. 对目标时间段内的每个交易日，必须精确查询一次 `cb_daily(trade_date=...)`。
4. 所有日期的结果必须拼接成一个完整的 DataFrame，以 `(code, time)` 作为 MultiIndex，时间格式与现有 pipeline 兼容。
5. 该方法必须能处理 `start_date` 至 `end_date` 之间的全部交易日，不得遗漏。
6. 修复后，`TuShareProvider` 在执行 audit 时必须能产出非空的 `price_row_count`，Stage A 不再因价格数据缺失而 FAIL。

### Non-Functional Requirements
1. 本 PRD 仅修改 `etl/tushare_provider.py`，不涉及其它 ETL 文件。
2. 查询纬度从 bond-count × date 变为 date-only，每年约 245 次 API 调用（对应约 245 个交易日），远低于 500 次/分钟的频次限制。
3. 按日期的全市场查询方式比按债券逐只查询更高效：一次 API 调用获取 500+ 日线行，不必为每只债券分别调用。
4. 必须维护交易日历信息以确定目标时间段内的有效交易日。

### Boundaries
**In Scope**
- `fetch_cb_daily()` 查询策略修复
- 与 `CBETLPipeline` Stage A 的对接兼容性

**Out of Scope**
- TuShareProvider 其他方法的修改
- premium_rate 计算逻辑的修改
- is_st 获取逻辑的修改
- JQDataProvider 的修改
- ETL runner 入口参数的修改

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Target File
该 FRD 只修改一个文件：
- `/root/projects/AMS/etl/tushare_provider.py`

### 3.2 修改内容：fetch_cb_daily 实现替换

当前实现：
```python
# 伪代码：遍历债券批次 → 逗号拼接 → cb_daily(ts_code)
→ 不工作（cb_daily 不支持多 ts_code）
```

目标实现：
```python
# 伪代码：遍历交易日 → 当日一次全量拉取 → cb_daily(trade_date)
→ 已验证可行

步骤：
1. 确定 start_date ~ end_date 间的所有交易日
2. 对每个交易日调用 pro.cb_daily(trade_date=<YYYYMMDD>)
3. 收集所有日期的 DataFrame 并拼接
4. 统一 rename + MultiIndex 格式
5. 返回
```

### 3.3 交易日历
`cb_daily(trade_date=...)` 只在交易日返回数据。非交易日调用返回空。因此：
- 可以惰性迭代：对范围内的每个日期都调用，空结果自动跳过
- 不必须预先获取交易日历

### 3.4 单次调用返回行数估算
已验证：
- 单日约 500 行
- 年窗口约 245 个交易日 → 约 122,500 行
- 需注意 cb_daily 的 "单次最大2000条" 限制：单日全市场约 500 行，远低于此限制

### 3.5 命名约定
- 传入参数格式：`YYYY-MM-DD`
- cb_daily 所需格式：`YYYYMMDD`
- 转换位置：方法内部

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: cb_daily query returns non-empty results for a valid week**
  - **Given** a known active week (2025-01-20 to 2025-01-24)
  - **When** `TuShareProvider.fetch_cb_daily()` is called with this window
  - **Then** it must return a non-empty DataFrame with `code` and `time` in the index
  - **And** the row count must be at least 500 (one day of market data)

- **Scenario 2: cb_daily query covers all trading days in the window**
  - **Given** the same week (2025-01-20 to 2025-01-24)
  - **When** the result is examined
  - **Then** unique dates in the result must match all 5 weekdays (Mon-Fri)
  - **And** each date must have approximately 500+ unique bond codes

- **Scenario 3: ETL audit with TuShare passes Stage A**
  - **Given** the fix is deployed
  - **When** `python3 -m etl.cb_etl_runner --data-source tushare --start 2025-01-20 --end 2025-01-24 --audit`
  - **Then** the audit report must show `source_coverage.status == PASS`
  - **And** `price_row_count` must be > 0

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
本 PRD 的风险很低：
- 修复范围仅限于一个方法的内部查询策略
- 已验证备选策略可以正常返回数据
- 不改变接口签名、数据映射逻辑或 pipeline 行为

质量目标：
- `fetch_cb_daily()` 在 2025-01-20 ~ 2025-01-24 窗口内必须能稳定返回 2500+ 行日线数据
- TuShare audit 的 Stage A 必须从 FAIL 变为 PASS

## 6. Framework Modifications (框架防篡改声明)
- `/root/projects/AMS/etl/tushare_provider.py`（`fetch_cb_daily` 方法）

---

## Appendix: Architecture Evolution Trace (架构演进与追踪审查)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY.

- **v1.0**: 基于现场验证：cb_daily 不支持逗号分隔 ts_code；备选方案按 trade_date 全量拉取已验证生效。

---

## 7. Hardcoded Content (硬编码内容)
### Exact Text Replacements:
- **`fetch_cb_daily_contract`**
```
fetch_cb_daily must query by trade_date (one date at a time) to retrieve the full-market CB daily snapshot.
Comma-separated ts_code batching is not supported by the cb_daily API and must not be used.
```
