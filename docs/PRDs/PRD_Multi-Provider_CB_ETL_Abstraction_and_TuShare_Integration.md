---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Multi-Provider CB ETL Abstraction and TuShare Integration

## 1. Context & Problem (业务背景与核心痛点)
AMS 当前的可转债 ETL 已具备 staged pipeline（source acquisition → supportability → premium join → ST join → redemption → validator），但实现层仍把 JQData 的 provider 细节直接写进了 pipeline。

当前真实耦合点：
- `etl/cb_etl_pipeline.py` 直接调用 JQData 风格接口：
  - `bond.run_query(...)`
  - `get_price(...)`
  - `get_extras("is_st", ...)`
  - `bond.CONBOND_DAILY_CONVERT...`
- `etl/jqdata_sync_cb.py` 同时承担：
  - production promote runner
  - audit runner
  - JQData provider 注入入口
- helper 和 stage 默认假设输入 DataFrame 符合 JQData 字段语义，例如：
  - `company_code`
  - `convert_premium_rate`
  - `delist_Date`

这带来三个核心问题：

### Problem A — 数据源被硬绑定到 JQData
AMS 现在不是“有一套 ETL pipeline，可以换 provider”，而是“pipeline 自己知道自己在调用 JQData”。
这意味着：
- 引入 TuShare 不是简单加一个 adapter 就结束；
- 未来引入 QMT、AKShare 或内部数据库时，会继续把 provider-specific 分支塞回 stage；
- ETL 层没有像 AMS 2.0 DataFeed/Broker 那样明确的接口边界。

### Problem B — JQData quota 已证明会阻塞 full-window ETL
已验证：
- JQData 免费版存在 **100 万条/天** 总量限制；
- full-window audit / ETL 很容易打满日限额；
- 一旦打满，当天后续连小窗口验证也可能失败；
- 这使得 canonical backtest dataset 的生产和 audit 诊断高度不稳定。

### Problem C — TuShare 已具备基本替代能力，但缺少统一接入方式
今天已验证：
- `cb_basic` 可用，能提供 `stk_code`、`delist_date`、`conv_price`；
- `cb_daily` 可用，能提供可转债日线；
- `cb_price_chg` 可用，能提供历史转股价变化序列；
- `stock_st` 可用，能按交易日返回 ST 股票列表；
- `cb_call` 当前 token 也可用。

因此，TuShare 已经具备成为 AMS CB ETL 替代/补充数据源的基本能力。

### 核心问题定义
> AMS 需要在不改变既有 CB source contract（`underlying_ticker`、`premium_rate`、`is_st`、`is_redeemed`）的前提下，把 CB ETL 从“JQData-specific implementation”重构成“source-agnostic staged pipeline + pluggable providers”。

## 2. Requirements & User Stories (需求定义)

### Functional Requirements
1. AMS 必须为 CB ETL 引入显式 provider abstraction，例如 `BaseDataProvider`。
2. 该 abstraction 至少支持：
   - `JQDataProvider`
   - `TuShareProvider`
3. `CBETLPipeline` 不得再直接调用 JQData-specific API 表达式（如 `bond.run_query(...)`、`bond.CONBOND_DAILY_CONVERT...`、`get_extras("is_st")`）。
4. `CBETLPipeline` 只允许调用抽象 provider contract，例如：
   - 获取可转债基础信息
   - 获取可转债日线行情
   - 获取转股价变动
   - 获取某交易日 ST 股票列表
   - 获取交易日历 / 证券池（如需要）
5. `TuShareProvider` 必须能输出满足 AMS 当前 source contract 的语义字段：
   - `underlying_ticker`
   - `premium_rate`
   - `is_st`
   - `is_redeemed`
6. `TuShareProvider` 的 `premium_rate` 实现必须支持历史转股价变化，不能仅用静态 `cb_basic.conv_price` 覆盖全历史窗口。
7. `is_st` 的实现必须基于 `stock_st(trade_date=...)` 或等价历史 ST 列表接口，不允许使用名称关键词近似。
8. ETL 入口脚本必须新增 provider 选择能力，例如：
   - `--data-source jqdata`
   - `--data-source tushare`
   - `--data-source auto`
9. 回测入口（`main_runner.py`）必须支持 provider 维度的数据集选择，而不是只靠手工传裸 `--data-path`。
10. AMS 必须支持“默认 provider 配置 + CLI 显式覆盖”的优先级规则。
11. 迁移期必须允许 JQData 和 TuShare 的 canonical dataset 并存，以便做对比验证与灰度迁移。

### Non-Functional Requirements
1. 本 PRD 不得修改策略逻辑、Broker 行为或 Runner 主流程。
2. 本 PRD 不得把 DataProvider abstraction 和 DataFeed/Broker abstraction 混为一谈；本次仅处理 ETL / source acquisition 层。
3. 不得通过 provider-specific fallback/default-fill 掩盖字段缺失。
4. abstraction 必须保持 audit runner 和 promote runner 共用同一套 pipeline，不得复制两套 ETL。
5. 迁移期的数据文件组织必须支持 provenance（来源可追溯），不能让不同 provider 无痕覆盖同一个文件。
6. 入口参数、配置字段、默认值优先级必须文档化并受测试保护。

### User Stories
- 作为 Boss，我希望 AMS 不再被单一数据源 quota 卡死，而能在 JQData / TuShare 之间切换。
- 作为 Manager，我希望 ETL pipeline 只关心 source contract，而不是每个 stage 都知道底层用的是哪家 API。
- 作为 Reviewer/Auditor，我希望 provider 切换是可审计的：入口参数明确、默认值明确、输出来源明确。
- 作为未来维护者，我希望新增第三种 provider 时不需要复制 ETL，只要实现 provider contract 即可。

### Boundaries
**In Scope**
- CB ETL provider abstraction
- JQDataProvider 抽离
- TuShareProvider 接入
- provider-aware ETL runner 参数与默认配置
- provider-aware dataset path / output naming
- provider 对比验证所需测试

**Out of Scope**
- 策略逻辑变更
- Broker 合约统一
- QMT live feed / live broker 改造
- Redemption gap 的业务分析与修正
- 重新定义 validator 业务规则
- 全量迁移所有 AMS 模块到 TuShare（本次仅限 CB ETL 路径）

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Core Design Decision
采用 **Option B：抽象 provider 层**，而不是继续在 pipeline 中对 TuShare 做“伪 JQData adapter”。

目标结构：

```text
etl/
  cb_provider_base.py
  jqdata_provider.py
  tushare_provider.py
  cb_etl_pipeline.py
  cb_etl_runner.py
```

### 3.2 Provider Contract
新增 `BaseDataProvider` 抽象层，至少包含以下能力（命名可微调，但语义必须清晰）：
- `fetch_cb_basic(...)`
- `fetch_cb_daily(...)`
- `fetch_cb_price_changes(...)`
- `fetch_stock_st_by_date(...)`
- `fetch_trade_calendar(...)`（如 pipeline 需要）
- `fetch_security_universe(...)`（如 pipeline 需要）

要求：
- provider 返回的数据结构应以 ETL source contract 作为第一目标，而不是原样暴露上游 API quirks；
- provider 内部可以保留上游字段的可追溯映射。

### 3.3 JQDataProvider
将现有 JQData-specific 获取逻辑从 `CBETLPipeline` 和 `jqdata_sync_cb.py` 中抽离到 `JQDataProvider`。

要求：
- 抽离后行为必须与现有通过的 JQData 路径等价；
- 既有 JQData source contract 不得改变；
- JQData free-tier quota 限制仍可存在，但应通过 provider 层显式暴露和分类，不再由 pipeline 直接吸收底层异常细节。

### 3.4 TuShareProvider
`TuShareProvider` 必须完成以下映射：

#### underlying_ticker
- 来源：`cb_basic.stk_code`
- 输出：符合 AMS 当前 `underlying_ticker` 语义

#### is_redeemed
- 主来源：`cb_basic.delist_date`
- 语义：保持与当前 AMS 一致，即 `date >= delist_date => is_redeemed = True`
- `cb_call` 可以作为审计/增强来源，但本 PRD 不要求改变当前主 contract

#### is_st
- 来源：`stock_st(trade_date=...)`
- 构造方式：按交易日拿 ST 股票列表，映射到 underlying ticker，产生日频布尔值
- 禁止使用名称关键词猜测 ST 状态

#### premium_rate
- 来源组合：
  - `cb_daily.close`
  - `cb_basic.conv_price`
  - `cb_price_chg` 历史转股价变化
- 要求：必须能为每个交易日恢复当日有效的 `conv_price`，再计算 `premium_rate`
- 禁止只用静态 `cb_basic.conv_price` 覆盖全历史窗口

### 3.5 Pipeline Refactor Boundary
`CBETLPipeline` 的职责必须被收窄为：
- stage orchestration
- supportability classification
- join / validator / audit classification
- report generation / promotion contract

`CBETLPipeline` 不再直接知道：
- JQData 的 ORM / 表名 / method 名称
- TuShare 的 API 名称
- provider-specific 权限/限额细节

### 3.6 Entry Script and Parameter Design
现有 `etl/jqdata_sync_cb.py` 文件名已经过度绑定 JQData。重构后应满足以下之一：
1. 引入新的 provider-neutral 入口，例如 `etl/cb_etl_runner.py`；
2. 或保留旧文件但仅作为兼容 shim，真正逻辑迁移到 neutral runner。

入口参数要求：
- `--data-source {auto,jqdata,tushare}`
- `--audit <start> <end>` 或等价 audit mode semantics
- `--promote <start> <end>` 或等价 production mode semantics

参数优先级要求：
1. CLI 显式参数
2. AMS 本地 provider 默认配置
3. 代码硬编码安全默认值

### 3.7 Config Strategy
必须新增一个 provider-aware 的 AMS 本地配置面，允许设置默认 provider 和对应的 dataset path。允许采用以下任一实现方式：
- 新增轻量 JSON/YAML 配置文件（推荐）
- 或在现有 AMS Python config 模块中增加运行时 provider 配置

必须满足：
- 能声明 `default_provider`
- 能声明每个 provider 的 canonical dataset path
- 能被 CLI override

### 3.8 Dataset Path Strategy
迁移期必须采用 provider 分文件存储：

```text
data/
  cb_history_factors_jqdata.csv
  cb_history_factors_tushare.csv
  cb_history_factors_jqdata.metrics.json
  cb_history_factors_tushare.metrics.json
```

禁止在迁移期让不同 provider 无标识地共用同一个输出文件。原因：
- 无法做并排回测对比
- 无法做 provenance 审计
- provider 切换会产生隐形覆盖

`main_runner.py` 可继续保留 `--data-path` 作为高级 override，但应新增更高层的 `--data-source` 语义入口。

### 3.9 Main Runner Integration
`main_runner.py` 当前只接受 `--data-path`。本 PRD 要求新增 provider 选择支持：
- `--data-source auto|jqdata|tushare`
- `--data-path` 保留，但降级为高级手动 override

推荐行为：
- `--data-source auto`：使用配置中的 `default_provider`
- `--data-source jqdata`：自动选择 jqdata canonical dataset path
- `--data-source tushare`：自动选择 tushare canonical dataset path

### 3.10 Skill / Runbook Impact
AMS `SKILL.md` 必须同步更新：
- Strategy Backtester 命令新增 `--data-source`
- 如果暴露 ETL / audit 能力，也必须支持 provider 选择
- 文档中明确：迁移期默认不要手工传裸路径，优先通过 `--data-source` 选择 provider

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Provider-neutral ETL runner can switch sources explicitly**
  - **Given** AMS has both JQDataProvider and TuShareProvider configured
  - **When** the operator runs the CB ETL runner with `--data-source tushare`
  - **Then** the ETL must execute without touching JQData-specific API call paths
  - **And** the output dataset and metrics must be labeled/provenanced as TuShare-derived artifacts

- **Scenario 2: Provider-neutral pipeline no longer hardcodes JQData API semantics**
  - **Given** the refactored `CBETLPipeline`
  - **When** a reviewer inspects the stage implementations
  - **Then** stage code must call provider contract methods instead of JQData-native ORM/table methods
  - **And** no stage may directly reference `CONBOND_DAILY_CONVERT`, `get_extras("is_st")`, or equivalent provider-specific expressions

- **Scenario 3: TuShareProvider can satisfy the AMS CB source contract**
  - **Given** a validation window and a set of representative convertible bonds
  - **When** the TuShare provider is used to produce ETL inputs
  - **Then** the resulting data must provide valid `underlying_ticker`, `premium_rate`, `is_st`, and `is_redeemed`
  - **And** `premium_rate` must be derived from date-correct effective conversion prices rather than a static latest value

- **Scenario 4: CLI override beats config default**
  - **Given** AMS config sets `default_provider = jqdata`
  - **When** the operator runs either ETL runner or `main_runner.py` with `--data-source tushare`
  - **Then** the run must use TuShare-derived artifacts instead of jqdata defaults

- **Scenario 5: Main runner can choose provider without manual raw path editing**
  - **Given** both jqdata and tushare canonical datasets exist side by side
  - **When** the operator runs `main_runner.py --data-source tushare`
  - **Then** the backtest must automatically read the TuShare canonical dataset path
  - **And** the operator must not need to pass a raw provider-specific file path to switch sources

- **Scenario 6: Migration period preserves provider provenance**
  - **Given** both providers are active during migration
  - **When** ETL promotion is executed from each provider
  - **Then** each provider must write to its own dataset and metrics artifacts
  - **And** provenance must remain auditable after the run

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
本 PRD 的核心风险不是某一行 API 调用写错，而是 provider abstraction 做成后表面可切换、实际 source contract 已经悄悄偏离，导致 ETL 虽然“能跑”，但语义不再一致。

测试策略要求：
1. **Mocked unit tests**
   - 覆盖 `BaseDataProvider` contract 行为
   - 覆盖 JQDataProvider / TuShareProvider 的字段映射与错误分类
   - 覆盖 `main_runner.py` 和 ETL runner 的 `--data-source` 优先级逻辑
2. **Provider contract tests**
   - 对 TuShare provider 的 `underlying_ticker`、`is_redeemed`、`is_st`、`premium_rate` 构造做定向验证
   - 对 `cb_price_chg` 重建出来的 effective conversion price 做时间序列验证
3. **Black-box ETL tests**
   - 同一小窗口下，使用 jqdata 与 tushare 各跑一次 audit runner
   - 确认 pipeline 无 provider-specific 崩溃、输出结构完整
4. **Migration smoke tests**
   - 同时生成 `cb_history_factors_jqdata.csv` 与 `cb_history_factors_tushare.csv`
   - 用 `main_runner.py --data-source jqdata/tushare` 各跑一次策略回测，验证路径选择正确
5. **Live validation guidance**
   - provider 精度对比应优先使用小窗口样本验证，不在本 PRD 中强制要求 full-window 完全一致；
   - 当 provider contract 与运行通路都验证通过后，再进行更大窗口的对比评估。

质量目标：
- ETL pipeline 真正 source-agnostic；
- 新增 provider 不再需要复制 ETL；
- `main_runner.py` 和 skill/runbook 的 provider 选择一致且可审计；
- TuShare 能以不破坏 AMS 既有 source contract 的方式接入。

## 6. Framework Modifications (框架防篡改声明)
- None

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 基于 Boss 对 AMS 2.0“策略执行层统一、数据源层可替换”的确认，决定在 CB ETL 路径上引入 Option B：provider abstraction，而不是继续扩大 JQData-specific pipeline。
- **Audit Rejection (v1.0)**: None yet.
- **v2.0 Revision Rationale**: None yet.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`provider_option_values`**
```text
auto|jqdata|tushare
```

- **`provider_override_precedence_text`**
```text
CLI explicit parameter overrides AMS local provider default configuration.
```

- **`tushare_premium_guard_message`**
```text
TuShare premium_rate must be derived from trade-date-correct effective conversion prices and must not be computed from a single static latest conversion price.
```

- **`provider_provenance_required_message`**
```text
Migration-period datasets from different providers must be stored as separate artifacts and must not silently overwrite one another.
```
