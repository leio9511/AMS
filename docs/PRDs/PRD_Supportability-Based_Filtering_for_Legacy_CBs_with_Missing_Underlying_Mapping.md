---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Supportability-Based Filtering for Legacy CBs with Missing Underlying Mapping

## 1. Context & Problem (业务背景与核心痛点)

AMS 当前可转债 canonical research/backtest dataset 的核心问题，已经不再是“某些债不在 `CONBOND_BASIC_INFO` 里”。真实 live rerun 证明，问题更本质地出在 **系统把“出现在 security master 中”误当成了“满足最小研究合同（supportability contract）”**。

最新现场证据如下：
1. 旧问题 `ISSUE-1184` 暴露的是 `underlying_ticker` 映射失败。第一轮修复后，原本大范围失败已经收缩到极少数历史债。
2. 第一版 follow-up PRD（`PRD_Relax_CB_dataset_regeneration_fail-fast_for_bonds_outside_CONBOND_BASIC_INFO.md`）已经通过 SDLC 并 UAT PASS，新增了“outside `CONBOND_BASIC_INFO` 的债先过滤，再保留对 valid-bond mapping failure 的 fail-fast”。
3. 但真实再次执行 `sync_cb_data(start_date="2025-01-17", end_date="2026-01-24")` 仍然失败：
   - 报错：`ValueError: Missing underlying_ticker for bonds in CONBOND_BASIC_INFO`
   - 唯一核心样本：`125302`（茂炼转债）
   - 该债 **在** `bond.CONBOND_BASIC_INFO` 中存在，但 `company_code = NaN`
   - 同时在允许窗口中仍有 247 行价格数据
   - 这说明它“存在于 basic_info”，但并“不满足最小 underlying mapping contract”
4. 因此，当前实现仍然存在治理缺口：
   - 它只区分“outside basic_info” 与 “inside basic_info”
   - 没有进一步区分：
     - **可支持（supportable）的正常标的**
     - **历史遗留但已知不可支持（legacy unsupported）的标的**
     - **真正的 source-contract regression / 数据异常**

这会导致：
- 一类极老、已退市多年、reference mapping 天然残缺的历史债，持续阻断 canonical dataset 的正式生成；
- 同时，系统又没有建立显式 exception bucket 和 reason-coded observability，无法把“可解释的 legacy exclusion”与“不可接受的 mapping regression”分层治理。

本 PRD 的核心目标不是简单“放松 fail-fast”，而是：
- **把 filtering contract 从 existence-based filtering（只看是否出现在 basic_info）升级为 supportability-based filtering（看是否满足最小研究合同）**；
- 对 legacy unsupported instruments 做显式过滤和记账；
- 对真正的 mapping regression 保留 hard fail。

## 2. Requirements & User Stories (需求定义)

### Functional Requirements
1. ETL 必须把 CB universe 分成三类：
   - **supportable instruments**：满足最小 underlying mapping contract，允许进入 canonical dataset；
   - **explicit legacy-unsupported instruments**：允许被过滤，但必须写入 reason-coded metrics；
   - **unexpected contract regression**：必须继续 hard fail。
2. **supportable** 的第一版 deterministic 定义固定为：
   - 存在有效 `bond_code_raw`
   - 存在至少 1 行价格数据
   - `bond_code_raw` 可映射到非空 `company_code`
   - 因而能生成有效 `underlying_ticker`
3. 对 **outside `CONBOND_BASIC_INFO`** 的债，允许继续过滤，但必须记录独立 metrics。
4. 对 **inside `CONBOND_BASIC_INFO` but `company_code = NaN`** 的债，不允许统一粗暴吞掉；必须先判断它是否属于 **legacy unsupported class**。
5. 第一版 deterministic **legacy unsupported** 分类规则固定为：
   - `bond_code_raw` 在 `CONBOND_BASIC_INFO` 中存在
   - `company_code` 为 null
   - `delist_Date` 非空
   - `delist_Date < start_date`
   - 满足以上条件者，视为 *legacy unsupported*，允许过滤并记录 metrics
6. 第一版 deterministic **unexpected contract regression** 定义固定为：
   - 不满足 `supportable`
   - 且不满足 `outside_basic_info`
   - 且不满足 `missing_company_code_legacy`
   - 满足以上条件者必须 hard fail
7. 对 `company_code` 为 null 但**不满足**上述 legacy 规则的债（例如未明确早于研究窗口退市，或 delist 语义不充分），必须继续 hard fail，防止把真实 contract regression 静默掩盖。
8. 过滤必须发生在 `underlying_ticker` 映射之前，并且在 `premium_rate` / `is_st` / `is_redeemed` 计算之前完成，防止 NaN 传播。
9. Metrics artifact 必须把 exclusion reason 分桶，至少区分：
   - `outside_basic_info`
   - `missing_company_code_legacy`
10. 对于本次已知样本 `125302`，在 2025-01-17~2026-01-24 真实窗口下，ETL 必须不再因它阻断整条链路；它应落入 `missing_company_code_legacy` exclusion bucket。

### Non-Functional Requirements
1. 不允许通过默认值、兜底映射、假 `underlying_ticker` 等方式绕过 source-contract 缺陷。
2. 不修改现有 validators（`CBDataValidator`, `DatasetSemanticValidator`）和 dataset promotion pipeline 的总体架构。
3. 变更必须保持低爆炸半径，集中在 `etl/jqdata_sync_cb.py` 及相关测试。
4. 结果必须保持可审计：任何被过滤的 legacy unsupported 债，都必须能从 metrics artifact 中追溯其数量、代码和过滤原因。

### Boundaries
- **In Scope**:
  - supportability-based filtering contract
  - legacy unsupported classification rule (v1 deterministic)
  - reason-coded metrics for filtered bonds
  - 相关测试和真实 rerun 验证
- **Out of Scope**:
  - 重写 validators
  - 修改 `premium_rate` / `is_st` / `is_redeemed` 的 source contract
  - broader dataset governance redesign beyond this filtering layer
  - 历史债 `company_code` 的外部补录/人工回填系统

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Design Principle
当前错误在于把“存在于 security master”当成“可支持研究/回测”。新设计应改为：
- **准入条件 = 满足最小 supportability contract**
- 而不是“只要出现在 `CONBOND_BASIC_INFO` 中就保留”

### 3.2 Proposed Classification Flow
在 `sync_cb_data()` 中，对 price-side rows 做如下四层分类：

1. **Bucket A — Supportable**
   - 满足以下全部条件：
     - `bond_code_raw` 非空
     - 至少存在 1 行价格数据
     - `bond_code_raw` 可映射到非空 `company_code`
   - 这些债进入后续正式 ETL 流程

2. **Bucket B — Legacy Unsupported / Outside Basic Info**
   - `bond_code_raw` 不在 `CONBOND_BASIC_INFO` 中
   - 允许过滤，记录为 `outside_basic_info`

3. **Bucket C — Legacy Unsupported / Missing Company Code**
   - `bond_code_raw` 在 `CONBOND_BASIC_INFO` 中
   - 但 `company_code` 为 null
   - 且 `delist_Date` 非空且 `< start_date`
   - 允许过滤，记录为 `missing_company_code_legacy`

4. **Bucket D — Unexpected Contract Regression**
   - 不满足 Bucket A
   - 且不满足 Bucket B
   - 且不满足 Bucket C
   - 这种情况必须 hard fail

### 3.3 Why This Is Safer Than Blanket Filtering
这不是简单把 `company_code = NaN` 全部吞掉，而是只对**可解释的历史遗留 class**放行：
- 对于像 `125302` 这种 1999 发行、2004 退市、研究窗口远晚于其退市时间的老债，reference mapping 缺失属于历史遗留数据不完整，可归入 legacy unsupported class；
- 对于任何更“现代”、更模糊、或缺乏足够 delist 语义支撑的 null `company_code` 债，继续 hard fail，避免把真实 regression 误当成 legacy 垃圾数据。

### 3.4 Implementation Target
重点修改文件：
- `etl/jqdata_sync_cb.py`

建议实现方式：
1. 构建：
   - `all_basic_info_codes`
   - `supportable_mapping_codes`（本质上是 `bond_to_stock.keys()`）
   - `legacy_missing_company_code_codes`
2. 先对 price-side rows 分类，再执行过滤
3. 过滤后的 `df` 再继续 `underlying_ticker` 映射与后续 ETL
4. 若仍出现 `underlying_ticker` 缺失，则说明是 Bucket D / unexpected regression，应 hard fail

### 3.5 Metrics Strategy
Metrics 不再只记录“被过滤了多少”，而要记录“为什么被过滤”：
- outside basic_info 的数量、行数、代码
- missing company_code legacy 的数量、行数、代码

所有 code lists 必须 deterministic（排序输出）。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Legacy unsupported bond with null company_code is filtered, not blocking**
  - **Given** 某转债在 `CONBOND_BASIC_INFO` 中存在，但 `company_code = null`
  - **And** 它的 `delist_Date` 非空且早于 `start_date`
  - **When** 执行 `sync_cb_data(start_date="2025-01-17", end_date="2026-01-24")`
  - **Then** 该债不得阻断 ETL
  - **And** 该债应被排除出最终 canonical dataset
  - **And** metrics artifact 中必须把它记入 `missing_company_code_legacy` exclusion bucket

- **Scenario 2: Bond outside CONBOND_BASIC_INFO is filtered with explicit reason**
  - **Given** 某转债价格数据存在，但 `bond_code_raw` 完全不在 `CONBOND_BASIC_INFO` 中
  - **When** 执行 ETL
  - **Then** 该债可被过滤而不阻断全流程
  - **And** metrics artifact 中必须把它记入 `outside_basic_info` exclusion bucket

- **Scenario 3: Null company_code without legacy justification still hard fails**
  - **Given** 某转债在 `CONBOND_BASIC_INFO` 中存在
  - **And** `company_code = null`
  - **But** 它不满足 `delist_Date < start_date` 的 legacy unsupported 条件
  - **When** 执行 ETL
  - **Then** 系统必须 hard fail
  - **And** 错误信息必须明确说明缺少 `underlying_ticker` for supportable bonds in `CONBOND_BASIC_INFO`

- **Scenario 4: Real-window ETL completes for current known blocker case**
  - **Given** 当前真实 JQData 窗口 `2025-01-17 ~ 2026-01-24`
  - **And** 已知历史 legacy case `125302`
  - **When** 执行真实 ETL
  - **Then** 该窗口的 ETL 不得再因为 `125302` 阻断
  - **And** canonical dataset promotion 应继续由 validators 决定，而不是提前死在 `underlying_ticker` prefilter 阶段

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core Quality Risk
最大的风险不是“代码不能运行”，而是：
1. 过度放松 fail-fast，导致真实 contract regression 被静默吞掉；
2. 过滤逻辑仍然太粗，把不该删除的研究样本误删，带来隐性 survivorship bias / universe drift；
3. 缺乏 reason-coded observability，未来再次遇到历史债异常时无法解释为什么被排除。

### Testing Strategy
1. **Deterministic mocked tests**
   - 模拟 outside basic_info
   - 模拟 inside basic_info but null company_code + legacy delist case
   - 模拟 inside basic_info but null company_code + non-legacy case（应 hard fail）
2. **Metrics validation tests**
   - 验证 reason-coded metrics 字段存在
   - 验证 code lists deterministic sorted
3. **Live verification**
   - 真实执行 `sync_cb_data(start_date="2025-01-17", end_date="2026-01-24")`
   - 证明 `125302` 不再阻断
4. **Blast-radius verification**
   - validators unchanged
   - `premium_rate` / `is_st` / `is_redeemed` source contracts unchanged
   - preflight / pytest green

### Mocking Guidance
- `jqdatasdk` 应被 mock 出三种类别：
  - outside basic_info
  - inside basic_info + null company_code + legacy delist
  - inside basic_info + null company_code + non-legacy
- 测试中必须显式断言分类结果和 hard-fail/filtered 行为不同

### Quality Goal
让 AMS 的 CB ETL 从“存在性过滤”升级为“可支持性过滤”：
- 历史遗留、明确不可支持的债不再阻断 dataset 生成；
- 正常 universe 的 mapping regression 仍然会被 fail-fast 拦住；
- 所有 exclusion 都有 reason-coded、可审计的 metrics 记录。

## 6. Framework Modifications (框架防篡改声明)
- `etl/jqdata_sync_cb.py`
- `tests/test_jqdata_sync_cb.py`
- `tests/test_jqdata_sync_cb_metrics_artifact.py`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 问题被理解为“outside CONBOND_BASIC_INFO 的债不应阻断 ETL”。
- **v1.1**: 第一版 PRD 已执行并 UAT PASS，但 live rerun 发现 `125302` 并不属于 outside basic_info，而是 inside basic_info + null company_code。
- **v2.0 Revision Rationale**: 问题重定义为 supportability contract 缺失；从 existence-based filtering 升级为 supportability-based filtering，并引入 legacy unsupported class 与 reason-coded exclusion metrics。

---

## 7. Hardcoded Content (硬编码内容)

### Error message for unexpected regression on supportable bonds:
```text
Missing underlying_ticker for supportable bonds in CONBOND_BASIC_INFO
```

### Deterministic supportability rule (v1):
```json
{
  "class": "supportable",
  "conditions": [
    "bond_code_raw is not null",
    "price row exists",
    "bond_code_raw maps to non-null company_code"
  ],
  "behavior": "keep_in_canonical_dataset"
}
```

### Deterministic outside-basic-info exclusion rule (v1):
```json
{
  "class": "outside_basic_info",
  "conditions": [
    "bond_code_raw is not present in CONBOND_BASIC_INFO"
  ],
  "behavior": "filter_out_and_record_metrics"
}
```

### Deterministic legacy unsupported classification rule (v1):
```json
{
  "class": "missing_company_code_legacy",
  "conditions": [
    "bond exists in CONBOND_BASIC_INFO",
    "company_code is null",
    "delist_Date is not null",
    "delist_Date < start_date"
  ],
  "behavior": "filter_out_and_record_metrics"
}
```

### Deterministic unexpected contract regression rule (v1):
```json
{
  "class": "unexpected_contract_regression",
  "conditions": [
    "not supportable",
    "not outside_basic_info",
    "not missing_company_code_legacy"
  ],
  "behavior": "hard_fail"
}
```

### Reason-coded metrics fields:
```json
{
  "filtered_bonds_outside_basic_info_count": "<int>",
  "filtered_rows_outside_basic_info_count": "<int>",
  "filtered_bond_codes_outside_basic_info": ["<bond_code>", "..."],
  "filtered_bonds_missing_company_code_legacy_count": "<int>",
  "filtered_rows_missing_company_code_legacy_count": "<int>",
  "filtered_bond_codes_missing_company_code_legacy": ["<bond_code>", "..."]
}
```

### Sorting requirement for metrics code lists:
```text
All filtered bond code lists in metrics artifacts MUST be sorted alphabetically for deterministic output.
```
