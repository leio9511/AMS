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
目标模块: 
1. `scripts/jqdata_sync_cb.py` (ETL 提取转换层)
2. `scripts/data_validator.py` (独立的数据质量校验网关)

**技术实现路径：**
1. **数据因子计算提取 (ETL)**：
   - **溢价率**：查 `finance.CCB_DAILY_PRICE`，提取 `convert_premium_rate` / 100。
   - **ST 状态**：查映射正股的 `is_st` 状态（强制批量 Vectorized 提取防限流）。
   - **强赎状态**：查 `finance.CCB_CALL`，规则：`date >= pub_date` 且 `date < delisting_date`。
   - **支持时间窗与增量**：脚本应支持 `--start_date` 和 `--end_date` 参数，未指定时从现有 CSV 最后日期自动续接。

2. **独立的数据校验组件 (Data Contract Validator)**：
   - 创建 `scripts/data_validator.py`，作为“数据契约（Data Contract）”的强制校验层。
   - **校验规则 (Rules)**：不允许日期跳空或NaN、溢价率范围必须在 `[-100, 1000]` 之间、价格必须 `> 0`、布尔值不可为空。
   - 它可以被 ETL 脚本作为函数调用（作为写入前的拦截器），也可以通过命令行独立运行（用于巡检已有 CSV 的健康度）。

3. **防御性 IO (原子写入与快照)**：
   - 脚本启动时，自动将 `data/cb_history_factors.csv` 备份为 `.bak`。
   - ETL 生成新 DataFrame 后，先写到 `.tmp` 临时文件。
   - 调用 `data_validator.py` 扫描该 `.tmp` 文件。
   - **只有 Validator 返回 True，才使用 `os.replace` (原子操作) 将 `.tmp` 覆盖为正式的 `.csv`。** 如果报错，则丢弃临时文件并告警。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 数据真实性校验**
  - **Given** 运行更新后的同步脚本
  - **When** 检查生成的 `data/cb_history_factors.csv` 文件
  - **Then** `premium_rate` 字段应为非零浮点数，且随日期动态变化。
  - **Then** `is_st` 和 `is_redeemed` 字段在历史上的特定风险时段应出现 `True` 值。
- **Scenario 2: 回测逻辑对齐**
  - **Given** 使用更新后的数据集运行 `BacktestRunner`
  - **When** 观察双低策略的选股排序
  - **Then** 排序结果应严格遵循 `close + premium_rate * 100` 的逻辑，而非仅仅按 `close` 排序。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Data Contract 测试 (数据契约)**：使用独立的 `data_validator.py` 扫描生成的历史数据，确保“无 NaN 漏水”、“因子值域无溢出”。
- **原子性测试**：编写单元测试模拟 `to_csv` 阶段抛出异常，断言原生的 `.csv` 文件内容和权限未遭到任何篡改（Shadow Writing 验证）。
- **一致性校验**：抽样 3-5 只转债在特定日期的溢价率和 ST 状态，对比聚宽官网数据，确保逻辑无偏。

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
