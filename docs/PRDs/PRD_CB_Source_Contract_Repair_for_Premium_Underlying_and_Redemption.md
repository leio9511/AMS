---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: CB_Source_Contract_Repair_for_Premium_Underlying_and_Redemption

## 1. Context & Problem (业务背景与核心痛点)
AMS 当前已经明确把 `ISSUE-1142` 定义为进入 Phase 2 前的 research dataset governance blocker。但在正式执行 1142 之前，最新 source audit（`ISSUE-1182`）证明：当前问题并不只是 ETL 治理不足，而是 **CB 三个关键字段的 source usage contract 本身写错了**。

已经查清的事实如下：
1. **`underlying_ticker` 不是缺数据，而是取法错了**
   - 当前脚本使用 `get_security_info(ticker).parent` 获取正股映射。
   - live probe 已确认该路径对可转债返回 `parent=None`。
   - 同时 `bond.CONBOND_BASIC_INFO` 明确提供 `company_code`，且值形态就是标准正股 ticker（例如 `600301.XSHG`、`000301.XSHE`）。
   - 结论：AMS 当前 `underlying_ticker` 失败不是 source 缺失，而是 extraction path 错误。
2. **`premium_rate` 不是缺数据，而是 query/filter/join 假设错了**
   - 当前脚本查询 `bond.CONBOND_DAILY_CONVERT` 时，对 sample CB tickers 在允许日期窗口中返回 0 rows。
   - 但 unrestricted probe 已确认这张表本身有真实数据。
   - probe 结果说明其 key 形态是分裂的，例如 `code=123056` 与 `exchange=XSHE`，而不是当前 AMS 脚本隐含假设的完整 ticker 形态。
   - 结论：`premium_rate` 失败是 query/filter/join contract 错误，不是 JQData 没数据。
3. **`is_redeemed` 当前 source assumption 明确错误**
   - 当前脚本依赖 `finance.CCB_CALL`。
   - live probe 已确认：`database 'finance' has no table 'CCB_CALL'`。
   - 同时 JQData 并非没有 redemption/delist 相关数据，`bond.CONBOND_BASIC_INFO` 已确认存在：
     - `convert_start_date`
     - `convert_end_date`
     - `delist_Date`
     - `maturity_date`
     - `last_cash_date`
     - `cash_comment`
   - 对 sample CBs，`delist_Date` 已在大多数可转债上可见，但部分样本（如 `123107`）为 `None`，说明最终语义规则仍需明确 fallback contract。
   - 结论：`is_redeemed` 不是 source 缺失，而是 current source assumption 错误。

所以，`ISSUE-1182` 的目标不是做数据治理，而是 **先把这三个字段的正确 source contract 修好并写死**。如果不先修这一步，后续 1142 再严的 quality gate 也只是在给错误 source assumption 上保险。

因此，本 PRD 的唯一目标是：
- 修复 `underlying_ticker` / `premium_rate` / `is_redeemed` 的 upstream source usage contract
- 让 AMS 的 ETL 先能够“拿对数据”
- 再由后续 1142 去负责“拿到的数据如何被治理、阻断和晋升”

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. `underlying_ticker` 必须停止使用 `get_security_info(ticker).parent`，改为基于 `bond.CONBOND_BASIC_INFO.company_code` 的显式映射。
2. `premium_rate` 必须继续使用 `bond.CONBOND_DAILY_CONVERT` 作为 source，但修正 query/filter/join contract，使其按表的真实 key 结构取数。
3. `is_redeemed` 必须废弃 `finance.CCB_CALL` 假设，改为基于 `bond.CONBOND_BASIC_INFO` 中已存在的生命周期字段建立第一版 deterministic 语义。
4. 本次必须把三项字段的 source contract 写死在代码与文档中，避免继续靠隐含假设运行。
5. 对 `is_redeemed`，本次必须明确写清楚：
   - 主判定字段
   - fallback 字段
   - 当主字段为空时的 deterministic 行为
6. ETL 产出的 research dataset 必须在这三项字段上不再依赖当前错误 assumption。
7. 本次必须更新相关测试，使未来 source usage 不会再悄悄漂回旧假设。

### Non-Functional Requirements
1. 本次 PRD 不引入正式 dataset governance gate，不与 1142 混做。
2. 变更必须低爆炸半径，只修 source acquisition / mapping / field semantics。
3. 所有修正必须可通过 live probe + deterministic tests 被验证。
4. 不允许用“先跑通再说”的默认值兜底掩盖 source contract 仍错误的情况。

### Boundaries
- **In Scope**:
  - `underlying_ticker` source contract 修复
  - `premium_rate` source contract 修复
  - `is_redeemed` source contract 修复
  - 对应 probe/test/documentation 更新
- **Out of Scope**:
  - canonical research dataset path 收敛
  - dataset-level semantic gates
  - promotion / rollback
  - golden snapshot refresh
  - QMT live integration
  - broader data governance policy

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Scope Separation from ISSUE-1142
本次 PRD 只修 **source truth / source usage contract**，不修 **dataset governance**。

明确分工：
- `ISSUE-1182` / 本 PRD：把三项关键字段的取数方式修对
- `ISSUE-1142` / 已过审 PRD：在 source contract 正确后，再加 canonical path、semantic gate、promotion/rollback

### 3.2 `underlying_ticker` Source Contract
#### Current Wrong Assumption
- `get_security_info(ticker).parent`
- 实证：对 sample CBs 返回 `parent=None`

#### Correct Contract
- Source table: `bond.CONBOND_BASIC_INFO`
- Source field: `company_code`
- Mapping rule:
  - 用 CB `code` 与 `CONBOND_BASIC_INFO.code` 建映射
  - 取 `company_code` 作为 `underlying_ticker`

### 3.3 `premium_rate` Source Contract
#### Current Wrong Assumption
- 当前 AMS 对 `bond.CONBOND_DAILY_CONVERT` 的 query/filter/join 使用了错误的 key 假设，导致 probe 命中为 0 rows。
- 最新 live probe 已确认这张表的真实 key 结构不是完整 ticker，而是：
  - `code`（例如 `123071`）
  - `exchange_code`（例如 `XSHE`）
  - `date`

#### Correct Contract
- Source table: `bond.CONBOND_DAILY_CONVERT`
- Required fields:
  - `code`
  - `exchange_code`
  - `date`
  - `convert_premium_rate`
- Canonical join contract:
  1. Price dataset 中的 `ticker` 必须先被规范化为两部分：
     - `bond_code_raw`
     - `bond_exchange_code`
  2. 规范化规则固定为：
     - `110052.XSHG` -> `bond_code_raw = "110052"`, `bond_exchange_code = "XSHG"`
     - `123071.XSHE` -> `bond_code_raw = "123071"`, `bond_exchange_code = "XSHE"`
  3. ETL 对 `bond.CONBOND_DAILY_CONVERT` 的 query/filter/join 必须基于：
     - `bond_code_raw == code`
     - `bond_exchange_code == exchange_code`
     - `date == date`
  4. 不允许再用完整 ticker 直接与 `code` 列比较。
  5. `convert_premium_rate` 必须转换为 decimal ratio：
     - `premium_rate = convert_premium_rate / 100.0`

- Observable output contract:
  - ETL 过程中必须暴露以下 join metrics：
    - `premium_rate_source_row_count`
    - `premium_rate_joined_row_count`
    - `premium_rate_join_coverage_ratio`
  - 其中：
    - `premium_rate_join_coverage_ratio = premium_rate_joined_row_count / total_price_rows`

### 3.4 `is_redeemed` Source Contract
#### Current Wrong Assumption
- Source: `finance.CCB_CALL`
- 实证：表不存在，必须废弃

#### Replacement Contract
本次第一版 deterministic 语义固定为：
1. Source table: `bond.CONBOND_BASIC_INFO`
2. Primary field: `delist_Date`
3. Fallback informational fields:
   - `maturity_date`
   - `last_cash_date`
   - `convert_end_date`
4. First deterministic rule:
   - 若 `delist_Date` 非空，则 `is_redeemed = (date >= delist_Date)`
   - 若 `delist_Date` 为空，则本次不猜测“已经强赎”，统一视为 `False`
5. Missing-delist observability contract:
   - ETL 必须显式输出一个 metrics 文件字段：
     - `is_redeemed_missing_delist_count`
   - 定义为：
     - `is_redeemed_missing_delist_count = count(records where delist_Date is null)`
   - 该指标必须写入 ETL metrics artifact，并在测试中可被读取与断言
6. External acceptance behavior:
   - 若样本债 `delist_Date=None`，则该样本生成的记录中 `is_redeemed` 必须为 `False`
   - 同时 `is_redeemed_missing_delist_count` 必须大于等于该样本对应记录数

这条规则的意义不是宣称它已经等价于完美的强赎标签，而是:
- 先从“错误 source/table 假设”升级到“确定可执行的第一版生命周期语义”
- 让系统停止依赖不存在的表
- 为下一阶段治理与质量门提供真实的、可解释的上游语义基础

### 3.5 Integration Points
本次预计涉及：
- `etl/jqdata_sync_cb.py`
- 如需要：相关数据加载/对齐辅助函数
- 相关测试文件（JQData sync 逻辑 / source contract probes）
- 文档 / issue 说明中对 source contract 的固化描述

### 3.6 Design Restraint
本次不做以下事情：
- 不引入 dataset-level gate
- 不调整正式 canonical path
- 不处理 `.openclaw/workspace` vs AMS canonical 路径问题
- 不做 promotion / rollback
- 不刷新 golden snapshot

本次只做一件事：
- **把三项关键字段的 source usage contract 修对。**

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: `underlying_ticker` comes from `company_code`**
  - **Given** `bond.CONBOND_BASIC_INFO` 中存在 sample CB 的 `company_code`
  - **When** 执行 CB ETL
  - **Then** 产出的 `underlying_ticker` 必须来自 `company_code`
  - **And** 不再依赖 `get_security_info(...).parent`

- **Scenario 2: `premium_rate` source query returns real rows and joins by canonical key**
  - **Given** `bond.CONBOND_DAILY_CONVERT` 中存在 sample CB 的有效数据
  - **When** 执行修正后的 ETL query/filter/join
  - **Then** `premium_rate` 必须能够被成功拉取并 merge 到 research dataset
  - **And** join 必须基于 `bond_code_raw + bond_exchange_code + date`
  - **And** 不再因为错误 key 假设导致 0-row 假失败

- **Scenario 3: `is_redeemed` no longer relies on nonexistent table**
  - **Given** 旧实现依赖 `finance.CCB_CALL`
  - **When** 执行修正后的 ETL
  - **Then** 系统不得再访问 `finance.CCB_CALL`
  - **And** 必须改为从 `bond.CONBOND_BASIC_INFO` 生命周期字段计算第一版 deterministic redemption/delist 语义

- **Scenario 4: `delist_Date` drives first deterministic redemption semantics**
  - **Given** 某转债样本存在 `delist_Date`
  - **When** 生成对应日期范围内的 ETL 数据
  - **Then** `date >= delist_Date` 的记录必须被标记为 `is_redeemed=True`

- **Scenario 5: null `delist_Date` has explicit fallback behavior and observable metrics**
  - **Given** 某转债样本 `delist_Date=None`
  - **When** 生成 ETL 数据
  - **Then** `is_redeemed` 本次必须按显式 fallback 规则处理为 `False`
  - **And** `is_redeemed_missing_delist_count` 必须在 metrics artifact 中可见且大于等于该样本记录数
  - **And** 不允许回到不存在的 `CCB_CALL` 路径

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
最大的风险不是 ETL 崩溃，而是继续把错误的 source assumption 写死在数据生产链里，导致 1142 后续治理建立在错误输入之上。

### Testing Strategy
1. **Live probe validation**
   - 使用小样本对三项 source contract 做真实 probe，证明 source assumption 正确
2. **Unit / integration tests**
   - 对 `underlying_ticker` 映射
   - 对 `premium_rate` query/filter/join
   - 对 `is_redeemed` first deterministic semantics
3. **Regression protection**
   - 锁住“不再访问 `finance.CCB_CALL`”
   - 锁住“不再依赖 `get_security_info(...).parent`”

### Mocking Guidance
- 可以 mock JQData 返回样本行来构造 deterministic tests
- 但至少要有一层 live probe / real-source evidence 作为验收依据

### Quality Goal
完成后，AMS 不再对这三项关键字段使用错误的 source assumption。后续 1142 执行时，dataset governance 将建立在正确 source contract 之上。

## 6. Framework Modifications (框架防篡改声明)
- `etl/jqdata_sync_cb.py`
- 相关测试文件
- 如有必要的 source contract helper

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 最初把问题理解成“可能是数据源没有数据”。
- **v1.1**: spike 证实三项都不是简单的 source absence，而是 AMS 的 source usage contract 错了。
- **v1.2**: 确认 1182 必须独立于 1142，先修 source contract，再修 dataset governance。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **Wrong `underlying_ticker` source assumption to remove**:
```text
get_security_info(ticker).parent
```

- **Correct `underlying_ticker` source contract**:
```text
bond.CONBOND_BASIC_INFO.company_code
```

- **Wrong `is_redeemed` source assumption to remove**:
```text
finance.CCB_CALL
```

- **Correct first deterministic `is_redeemed` primary field**:
```text
bond.CONBOND_BASIC_INFO.delist_Date
```

- **Canonical `premium_rate` join contract**:
```json
{
  "price_side_fields": ["ticker", "date"],
  "normalized_price_fields": ["bond_code_raw", "bond_exchange_code", "date"],
  "source_side_fields": ["code", "exchange_code", "date"],
  "join_contract": [
    "bond_code_raw == code",
    "bond_exchange_code == exchange_code",
    "date == date"
  ],
  "normalization_examples": {
    "110052.XSHG": {"bond_code_raw": "110052", "bond_exchange_code": "XSHG"},
    "123071.XSHE": {"bond_code_raw": "123071", "bond_exchange_code": "XSHE"}
  }
}
```

- **Required premium-rate metrics names**:
```json
[
  "premium_rate_source_row_count",
  "premium_rate_joined_row_count",
  "premium_rate_join_coverage_ratio"
]
```

- **Required redemption-missing metrics name**:
```json
[
  "is_redeemed_missing_delist_count"
]
```

- **`premium_rate` source table to keep but query contract to repair**:
```text
bond.CONBOND_DAILY_CONVERT
```

- **Failure message if legacy redemption source is still invoked**:
```text
[FATAL] Invalid redemption source contract: finance.CCB_CALL is not a valid JQData table for AMS convertible-bond lifecycle semantics.
```

- **Failure message if legacy underlying source is still invoked**:
```text
[FATAL] Invalid underlying-ticker source contract: get_security_info(ticker).parent is not valid for AMS convertible bonds.
```
