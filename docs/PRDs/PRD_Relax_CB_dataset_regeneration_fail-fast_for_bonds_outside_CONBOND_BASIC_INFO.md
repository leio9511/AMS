---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Relax CB dataset regeneration fail-fast for bonds outside CONBOND_BASIC_INFO

## 1. Context & Problem (业务背景与核心痛点)

ISSUE-1184 的修复（normalize cb underlying mapping by raw bond code）已在代码层面落地。但在 2025-01-17~2026-01-24 全量数据重跑验证中，ETL 仍然在 `underlying_ticker` mapping 的 fail-fast gate 处 `ValueError` 阻断。

现场探测结果：
- 总 CB 数目：1046 个唯一 ticker，其中 1045 个成功映射到 `company_code`
- 唯一失败代码：`125302`（0.095% 行数）
- `125302` 在 `CONBOND_BASIC_INFO`、`get_security_info`、`get_price` 中均无记录，是一个极其古老的退市可转债
- 该债在 2025~2026 回测窗口没有任何实际意义

当前 fail-fast 逻辑在 `etl/jqdata_sync_cb.py` ~line 185-186：
```python
df["underlying_ticker"] = df["bond_code_raw"].map(bond_to_stock)
if df["underlying_ticker"].isna().any():
    raise ValueError("Missing underlying_ticker for some records")
```

这条 gate 的问题是：当一个债连 JQData 自身的 reference table 都不存在时，`underlying_ticker` 不可能被映射成功。此时阻断整条数据链路晋升是不合理的——应该跳过该债的处理，保留 fail-fast 给那些本应能被映射但意外的缺失。

核心痛点：**fail-fast 的范围太宽，覆盖了本应降级为 warning 的场景。** 对于能通过 `CONBOND_BASIC_INFO` 验证存在的债，fail-fast 仍应保留；对于在 `CONBOND_BASIC_INFO` 中完全没有记录的债（通常是远古已摘牌债券），应 filter out 而不是阻塞全线数据。

## 2. Requirements & User Stories (需求定义)

### Functional Requirements
1. ETL 必须能成功跑通 2025-01-17~2026-01-24 的全量 CB 数据生成，不再因 `125302` 等不在 `CONBOND_BASIC_INFO` 中的老债而阻塞
2. 处理方式：在 `underlying_ticker` 映射之前，先过滤掉 `bond_code_raw` 不在 `CONBOND_BASIC_INFO` 中的债券行
3. 对于在 `CONBOND_BASIC_INFO` 中存在、但 `company_code` 为 `NaN` 的债券，fail-fast 仍需保留（这代表真实的 contract bug）
4. 过滤行为必须在 `premium_rate`、`is_st`、`is_redeemed` 等后续计算之前发生，避免这些计算因缺失 underlying_ticker 而产生 NaN 传播
5. ETL 完成后，metrics artifact 必须记录被过滤掉的债券数量与占比

### Non-Functional Requirements
1. 不改动已有的 validators (`CBDataValidator`, `DatasetSemanticValidator`) 及 quality gates
2. 不改动 `CONBOND_BASIC_INFO` source contract 本身
3. 逻辑变更低爆炸半径：只在 `underlying_ticker` mapping 之前增加一层 pre-filter

### Boundaries
- **In Scope**:
  - `etl/jqdata_sync_cb.py` 中的 fail-fast 逻辑调整
  - metrics 输出增加过滤统计
  - 相关测试更新
- **Out of Scope**:
  - 任何 validator 或 quality gate 的调整
  - `CONBOND_BASIC_INFO` source contract 的修改
  - ETL 全局架构变更

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 修改定位
唯一需要变更的文件：`etl/jqdata_sync_cb.py`，约 line 181-186 区域。

### 3.2 具体逻辑变更

**当前流程（简化）**：
```
build bond_to_stock mapping from CONBOND_BASIC_INFO
df["underlying_ticker"] = df["bond_code_raw"].map(bond_to_stock)
if df["underlying_ticker"].isna().any():
    raise ValueError   ← 阻断整条链路
...
fetch is_st for underlying_tickers
...
validate and promote dataset
```

**目标流程**：
```
build bond_to_stock mapping from CONBOND_BASIC_INFO
# NEW: identify bonds not in CONBOND_BASIC_INFO
valid_mask = df["bond_code_raw"].isin(bond_to_stock.keys())
filtered_count = (~valid_mask).sum()
# Apply mapping only on valid rows
df.loc[valid_mask, "underlying_ticker"] = df.loc[valid_mask, "bond_code_raw"].map(bond_to_stock)
# NEW: remove rows that can never be mapped
df = df[valid_mask].copy()
# FAIL-FAST: keep for bonds that ARE in basic_info but have NaN company_code
if df["underlying_ticker"].isna().any():
    raise ValueError("Missing underlying_ticker for bonds in CONBOND_BASIC_INFO")
...
fetch is_st for underlying_tickers
...
validate and promote dataset
```

### 3.3 Metrics 增强
在 metrics artifact 中新增：
```json
{
  "filtered_bonds_outside_basic_info_count": <int>,
  "filtered_rows_outside_basic_info_count": <int>,
  "filtered_bond_codes": ["125302", ...]
}
```

### 3.4 风险
- 极低。只 affect 一个已知的边缘场景（`125302`）。
- 不会降低对 `CONBOND_BASIC_INFO` 内债券的映射质量保护。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: ETL succeeds for full JQData-permitted window**
  - **Given** JQData available and `bond.CONBOND_BASIC_INFO` loaded
  - **When** `sync_cb_data(start_date="2025-01-17", end_date="2026-01-24")` is called
  - **Then** ETL completes without `ValueError`
  - **And** output dataset `cb_history_factors.csv` is written to disk
  - **And** quality validators (`CBDataValidator`, `DatasetSemanticValidator`) pass

- **Scenario 2: Bond outside CONBOND_BASIC_INFO is filtered, not blocking**
  - **Given** old delisted CB `125302` exists in `get_all_securities` but NOT in `CONBOND_BASIC_INFO`
  - **When** ETL runs with default window
  - **Then** records for `125302` are silently dropped (not raising ValueError)
  - **And** `filtered_bonds_outside_basic_info_count` in metrics artifact >= 1
  - **And** `filtered_bond_codes` in metrics contains `"125302"`

- **Scenario 3: Fail-fast still prevents promotion for bonds IN basic_info with null company_code**
  - **Given** a bond code exists in `CONBOND_BASIC_INFO` but its `company_code` is NaN
  - **When** ETL attempts mapping
  - **Then** `ValueError("Missing underlying_ticker for bonds in CONBOND_BASIC_INFO")` is raised
  - **And** dataset promotion is blocked

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core Quality Risk
最大的风险不是代码写错，而是降低 fail-fast 范围后无意中掩盖了真正的 `underlying_ticker` 映射问题。

### Testing Strategy
1. **基础验证**：在现有 pytest 基础上，增补一个 test case 验证 `125302` 场景的 filtering behavior
2. **保留保护**：增加一个 test case 验证：当 `CONBOND_BASIC_INFO` 内的债有 `company_code` 为 NaN 时，fail-fast 仍然生效
3. **end-to-end 验证**：最终需用真实 JQData 跑一次全窗口 sync，确认 pipeline 完全通过

### Mocking Guidance
- 可以 mock `jqdatasdk` 来构造 `125302` 不在 `CONBOND_BASIC_INFO` 的场景
- 也要 mock 一个在 basic_info 中但 company_code 为 NaN 的场景，用于保护 fail-fast 不被误删

### Quality Goal
跑通 `sync_cb_data(start_date="2025-01-17", end_date="2026-01-24")`，产出完整的 `cb_history_factors.csv`，通过所有 quality gates。

## 6. Framework Modifications (框架防篡改声明)
- `etl/jqdata_sync_cb.py`
- 如需要：相关测试文件

---

## 7. Hardcoded Content (硬编码内容)

### Fail-fast error message for bonds IN basic_info but with missing mapping:
```text
Missing underlying_ticker for bonds in CONBOND_BASIC_INFO
```

### Old fail-fast error message to replace:
```text
Missing underlying_ticker for some records
```

### ETL metrics fields to add:
```json
{
  "filtered_bonds_outside_basic_info_count": "<int>",
  "filtered_rows_outside_basic_info_count": "<int>",
  "filtered_bond_codes": ["125302", "..."]
}
```
