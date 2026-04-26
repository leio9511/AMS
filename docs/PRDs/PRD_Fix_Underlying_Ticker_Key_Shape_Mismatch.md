---
Affected_Projects: ["AMS"]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix_Underlying_Ticker_Key_Shape_Mismatch

## 1. Context & Problem（业务背景与核心痛点）

### 背景

ISSUE-1182 落地后，`etl/jqdata_sync_cb.py` 已从 `get_security_info(ticker).parent` 迁至 `bond.CONBOND_BASIC_INFO.company_code` 作为 `underlying_ticker` 的唯一 source contract。新 fail-fast gate 也在 ISSUE-1142 中上线，正确阻止了不可信数据集晋升为 canonical dataset。

### 问题

对 JQData 允许的时间窗口（`2025-01-15` 至 `2026-01-22`）做真实 canonical CB 数据集重建时，ETL 直接抛出 `ValueError: Missing underlying_ticker for some records`。量化诊断：

- `missing_rows = 259408`
- `missing_unique_tickers = 1046`
- 代表失败代码：`110001.XSHG`, `110010.XSHG`, `110020.XSHG`, `110031.XSHG`, `123001.XSHE`, `127001.XSHE` 等大量历史可转债代码

### 根因

**这并非 JQData 历史数据天然缺失，而是 AMS 自己的 key 形状用错了。**

当前实现（`etl/jqdata_sync_cb.py` 第 167 行）：

```python
df["underlying_ticker"] = df["ticker"].map(bond_to_stock)
```

这里 `bond_to_stock` 是从 `CONBOND_BASIC_INFO.code → company_code` 构建的字典。但实时 `get_price()` 返回的 price-side ticker 格式是完整 ticker（如 `110001.XSHG`），而 `CONBOND_BASIC_INFO.code` 的值形态是原始债券代码（如 `110001`）——两者 key 形状不匹配，导致 `.map()` 大面积 miss。

有趣的是：

- `_split_bond_ticker()` 辅助函数已存在且正确
- `_build_bond_key_columns()` 辅助函数也已存在且正确
- `premium_rate` 链路已经按"先归一化再 join"做对了
- 唯独 `underlying_ticker` 这条链路还停留在"完整 ticker 直接 map"的旧形态

### 为什么现有测试没抓住

当前所有测试的 mock `CONBOND_BASIC_INFO.code` 都使用了完整 ticker 形态（如 `"110059.XSHG"`），与 mock 的 `get_price()` index 形状一致，因此测试全部通过但覆盖了错误行为。真实 JQData 返回的 `CONBOND_BASIC_INFO.code` 是原始代码（如 `110059`），不含 `.XSHG` / `.XSHE` 后缀。

## 2. Requirements & User Stories（需求定义）

### Functional

1. **F1 — 归一化后再映射**：`underlying_ticker` 的映射链路必须先对 price-side `ticker` 做归一化（提取 `bond_code_raw`），再用 `bond_code_raw` 去匹配 `bond_to_stock` 字典。禁止继续使用完整 ticker 直接 `.map()`。

2. **F2 — Source contract key 一致性**：`_build_underlying_mapping()` 产出的字典 key 形态必须与 price-side 归一化后的 key（`bond_code_raw`）统一。如果 `CONBOND_BASIC_INFO.code` 返回的是原始代码（不含后缀），映射字典 key 也必须是原始代码。

3. **F3 — Fail-fast gate 行为不变**：`underlying_ticker` 缺失时仍然报 `ValueError("Missing underlying_ticker for some records")`，不放松 fail-fast 阈值，不引入静默默认值。

### Non-functional

- 不改变 `is_st` 获取链路（仍用 `underlying_ticker` 去拉 `get_extras("is_st", ...)`），只改变 `underlying_ticker` 的 **产生方式**。
- 不影响 `premium_rate` 链路（已正确）。
- 不影响 `is_redeemed` / `delist_Date` 链路。

## 3. Architecture & Technical Strategy（架构设计与技术路线）

### 目标文件

**唯一业务修改文件**：`/root/projects/AMS/etl/jqdata_sync_cb.py`

**必须修改的测试文件**：
- `/root/projects/AMS/tests/test_jqdata_sync_cb.py`
- `/root/projects/AMS/tests/test_jqdata_sync_cb_source_contracts.py`
- `/root/projects/AMS/tests/test_jqdata_sync_cb_premium_contract.py`
- `/root/projects/AMS/tests/test_jqdata_sync_cb_logic.py`
- `/root/projects/AMS/tests/test_jqdata_sync_cb_io.py`
- `/root/projects/AMS/tests/test_jqdata_sync_cb_metrics_artifact.py`

### 修改方案

#### 3.1 `_build_underlying_mapping()` 修正

当前实现从 `CONBOND_BASIC_INFO` 拉 `code` 列直接做 key。如果实时 JQData 返回的 `code` 是原始代码（如 `110001`），则映射字典 key 天然正确。如果实时 JQData `code` 包含后缀，则需要在此函数内部归一化 key。

**硬性目标**：确保 `bond_to_stock` 字典的 key 是原始债券代码（`bond_code_raw`），不含交易所后缀。

#### 3.2 `sync_cb_data()` 映射链路修正

将当前：

```python
df["underlying_ticker"] = df["ticker"].map(bond_to_stock)
if df["underlying_ticker"].isna().any():
    raise ValueError("Missing underlying_ticker for some records")
df = _build_bond_key_columns(df, ticker_col="ticker")
```

改为：

```python
df = _build_bond_key_columns(df, ticker_col="ticker")
df["underlying_ticker"] = df["bond_code_raw"].map(bond_to_stock)
if df["underlying_ticker"].isna().any():
    raise ValueError("Missing underlying_ticker for some records")
```

核心变更：**先归一化（`_build_bond_key_columns`），再用 `bond_code_raw` 做映射**，不再用完整 `ticker`。

### 设计决策

- **不放松 fail-fast gate**：`ValueError` 保持原样。如果归一化后仍有缺失，说明真实数据缺口存在，应由后续 issue 单独处理。
- **与 `premium_rate` 链路对齐**：`premium_rate` 已通过 `_normalize_premium_source()` 先归一化再 join，`underlying_ticker` 应与之一致。
- **不修改 `_split_bond_ticker()` / `_build_bond_key_columns()` 本身**：这两个辅助函数已验证正确，只需把它们用到正确位置。

## 4. Acceptance Criteria（BDD 黑盒验收标准）

- **Scenario 1: 完整 ticker 能通过归一化正确映射 underlying**
  - **Given** `CONBOND_BASIC_INFO` 中 `code = 110001`, `company_code = 600301.XSHG`
  - **And** `get_price()` 返回 ticker `110001.XSHG`
  - **When** 执行 `sync_cb_data()`
  - **Then** 产出的 `underlying_ticker` 必须是 `600301.XSHG`
  - **And** 不抛出 `ValueError`

- **Scenario 2: 多个不同交易所的债券各自映射到正确 underlying**
  - **Given** `CONBOND_BASIC_INFO` 中存在 `110001 → 600301.XSHG` 和 `123001 → 000301.XSHE`
  - **And** `get_price()` 返回 `110001.XSHG` 和 `123001.XSHE`
  - **When** 执行 `sync_cb_data()`
  - **Then** `110001.XSHG` 的 `underlying_ticker` 为 `600301.XSHG`
  - **And** `123001.XSHE` 的 `underlying_ticker` 为 `000301.XSHE`

- **Scenario 3: 归一化后仍然缺失时正确 fail-fast**
  - **Given** `CONBOND_BASIC_INFO` 中不包含某只债券的 `code`（真实数据缺口）
  - **And** `get_price()` 返回该债券的 ticker
  - **When** 执行 `sync_cb_data()`
  - **Then** 必须抛出 `ValueError("Missing underlying_ticker for some records")`

- **Scenario 4: 完整 ticker 直接作为 map key 被禁止（反回归）**
  - **Given** 任何 mock 或测试执行
  - **When** `underlying_ticker` 映射发生时
  - **Then** 映射 key 必须是归一化后的 `bond_code_raw`，不得是完整 ticker 字符串

## 5. Overall Test Strategy & Quality Goal（测试策略与质量目标）

### 核心质量风险

修复后如果测试仍然用 `"110059.XSHG"` 这种完整 ticker 做 mock `code`，则测试会继续掩盖真实行为。**最大的风险是 mock 数据与真实 JQData 返回形状不一致。**

### Mock 策略

- **`CONBOND_BASIC_INFO.code`**：mock 必须使用原始代码（如 `"110059"`），不含后缀 `".XSHG"` / `".XSHE"`。这是本 PRD 的关键质量要求。
- **`get_price()` 返回的 ticker**：保持完整格式（如 `"110059.XSHG"`），因为这是真实 JQData 行为。
- **`CONBOND_BASIC_INFO.company_code`**：保持完整 ticker 格式（如 `"600000.XSHG"`），这是真实 JQData 行为。

### 需要新增的测试

1. **确定性回归测试（单元级，不依赖 JQData）**：
   - `test_underlying_mapping_uses_normalized_bond_code_raw`：验证映射链路使用 `bond_code_raw` 而非完整 ticker
   - `test_underlying_mapping_succeeds_when_basic_info_code_is_raw`：验证当 `CONBOND_BASIC_INFO.code` 是原始代码时映射成功

2. **反回归测试**：
   - `test_full_ticker_cannot_be_used_as_underlying_map_key`：验证完整 ticker 不再被直接用于映射

3. **现有测试修正**：
   - 将所有 mock `CONBOND_BASIC_INFO.code` 从 `"110059.XSHG"` 改为 `"110059"`，使其匹配真实 JQData 行为
   - 确保修正后的测试仍然全部通过

### 不需要的测试

- 不需要真实 JQData E2E 回归（本 PRD 只修 key 形状 bug，真实数据覆盖验证是 ISSUE-1184 修完后单独跑 regeneration 的事）

## 6. Framework Modifications（框架防篡改声明）

- `etl/jqdata_sync_cb.py` — 唯一业务代码修改目标
- 无 SDLC framework 文件（如 `orchestrator.py`, `agent_driver.py`, `spawn_*.py` 等）需要修改

---

## Appendix: Architecture Evolution Trace（架构演进与审查追踪）

- **v1.0**: 基于 ISSUE-1184 诊断结论起草：`underlying_ticker` 映射链路 key 形状不匹配（完整 ticker vs 原始债券代码），修复方向为先归一化再映射。

---

## 7. Hardcoded Content（硬编码内容）

### 必须保留的 fail-fast 消息（不得修改）

- **For `etl/jqdata_sync_cb.py`**:
  ```python
  raise ValueError("Missing underlying_ticker for some records")
  ```

### 必须保留的 fatal source-contract guard 消息（不得修改）

- **For `LEGACY_UNDERLYING_SOURCE_FATAL`**:
  ```python
  LEGACY_UNDERLYING_SOURCE_FATAL = (
      "[FATAL] Invalid underlying-ticker source contract: get_security_info(ticker).parent "
      "is not valid for AMS convertible bonds."
  )
  ```
