---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Remove_Mock_Data_from_CB_Backtest

## 1. Context & Problem (业务背景与核心痛点)
当前 AMS v2.0 的回测数据同步脚本 `scripts/jqdata_sync_cb.py` 仅实现了基础的 OHLCV 数据获取，对于核心策略因子（溢价率、ST 状态、强赎状态）采取了硬编码 Mock（如 `is_st=False`, `premium_rate=0.0`）的处理方式。这导致当前所有的回测结果均无法反映真实市场逻辑，双低轮动策略实际上退化成了单纯的低价轮动，且存在严重的未来函数风险（无法识别历史真实的强赎和 ST 风险）。

## 2. Requirements & User Stories (需求定义)
1. **真实数据回填**：将 `scripts/jqdata_sync_cb.py` 中的 Mock 逻辑替换为基于 JQData (JoinQuant) 的真实历史数据查询。
2. **单一数据源原则**：历史回填过程严格使用 JQData 接口，确保数据格式和时间轴的内部一致性。
3. **消除未来函数**：数据获取逻辑必须模拟“实盘可获得性”。例如，强赎状态必须基于“公告日期”而非“退市日期”进行判定。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
目标模块: `scripts/jqdata_sync_cb.py`

**技术实现路径：**
1. **真实因子回填 (JQData Queries)**：
   - **溢价率 (premium_rate)**：使用 `jqdatasdk.finance.run_query` 查询 `finance.CCB_DAILY_PRICE` 表，提取 `convert_premium_rate` 字段并除以 100（转换为小数）。
   - **ST 状态 (is_st)**：映射转债至正股代码，使用 `jqdatasdk.get_extras('is_st', ...)` 获取历史状态。必须使用向量化（Vectorized）查询，严禁循环请求。
   - **强赎状态 (is_redeemed)**：查询 `finance.CCB_CALL`。判定逻辑：`date >= pub_date` 且 `date < delisting_date`（杜绝未来函数）。
   - **正股代码 (underlying_ticker)**：从转债基础信息表拉取真实关联代码。

2. **数据安全写入流程 (集成 1144 成果)**：
   - **原子写入**：脚本写入文件时，严禁直接覆盖原文件。必须先写入临时文件（如 `data/cb_history_factors.csv.tmp`）。
   - **强制校验 (Circuit Breaker)**：在完成数据处理后，必须实例化并调用 `ams.validators.cb_data_validator.CBDataValidator` 对新生成的 DataFrame 进行校验。
   - **原子替换**：只有当 `validator.validate_dataframe(df)` 返回 `True` 时，才调用 `os.replace()` 将临时文件替换为正式的 `data/cb_history_factors.csv`。
   - **自动快照**：脚本启动初期，自动将旧的 `.csv` 备份为 `.bak`。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 数据真实性校验**
  - **Given** 运行更新后的同步脚本
  - **When** 检查生成的 `data/cb_history_factors.csv` 文件
  - **Then** `premium_rate` 字段应为非零浮点数，且随日期动态变化。
  - **Then** `is_st` 和 `is_redeemed` 字段在历史上的特定风险时段应出现 `True` 值。
- **Scenario 2: 数据安检门拦截测试**
  - **Given** 故意注入一个带 NaN 的异常数据或不合法的溢价率
  - **When** 运行同步脚本
  - **Then** 脚本应被 Validator 拦截，并在日志中输出 `[DataContractViolation]`。
  - **Then** 正式的 `cb_history_factors.csv` 文件应保持原样，不被脏数据污染。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **数据完整性测试**：增加针对 `jqdata_sync_cb.py` 的回归测试，验证联表查询后的 DataFrame 是否存在意外的空值（NaN），尤其是 Join 之后的日期对齐情况。
- **一致性校验**：抽样 3-5 只转债在特定日期的溢价率和 ST 状态，手动对比聚宽官网数据，确保 ETL 逻辑无偏。

## 6. Framework Modifications (框架防篡改声明)
- 无。仅修改业务脚本 `scripts/jqdata_sync_cb.py`。

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: 初始方案，将 `scripts/jqdata_sync_cb.py` 从 Mock 模式切换为 JQData 联表查询模式。

---

## 7. Hardcoded Content (硬编码内容)
- **JQData Finance Table Schema**:
  - 溢价率查询表名: `finance.CCB_DAILY_PRICE`
  - 溢价率字段名: `convert_premium_rate`
  - 强赎公告表名: `finance.CCB_CALL`
  - 强赎判定关键字段: `pub_date` (公告日), `delisting_date` (退市日)
