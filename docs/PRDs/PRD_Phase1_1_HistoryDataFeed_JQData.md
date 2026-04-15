---
Affected_Projects: [AMS]
---

# PRD: Phase1_1_HistoryDataFeed_JQData

## 1. Context & Problem (业务背景与核心痛点)
本 PRD 对应 ISSUE-1134，是 AMS 事件驱动回测微框架（ISSUE-1133）的第一步。
原有的 `crystal_fly_swatter.py` 等脚本严重依赖 AKShare（东方财富接口），频繁出现 `Connection aborted` 和超时，且无法满足回测系统海量历史数据的极速拉取需求。
为了构建坚固的回测底座，我们引入商业级数据源 **JQData（聚宽）** 替代 AKShare 作为回测数据的离线供应商。我们需要构建一个“离线拉取（ETL）”与“极速读取（DataFeed）”彻底解耦的数据管道。

## 2. Requirements & User Stories (需求定义)
1. **ETL 下载器 (`scripts/jqdata_sync_cb.py`)**:
   - 编写一个独立的离线下载脚本，使用 `jqdatasdk` 拉取全市场可转债的历史数据。
   - 数据需包含：开高低收、成交额、溢价率、双低值、正股代码、正股 ST 状态、强赎状态（如果有/可推算）。
   - 将结果保存为本地扁平化文件（如 `data/cb_history_factors.csv`）。
   - **安全要求**：账号密码绝对不能硬编码，必须通过环境变量 `JQDATA_USER` 和 `JQDATA_PWD` 读取。
2. **极速读取器 (`ams/core/history_datafeed.py`)**:
   - 实现 `HistoryDataFeed` 类（继承自 `BaseDataFeed`）。
   - 初始化时一次性将本地离线 CSV 文件加载到 Pandas 内存。
   - 实现 `get_data(date)` 方法，返回指定日期当天的数据快照（DataFrame切片）。
   - **绝对红线**：禁止在此类中发起任何网络请求，彻底杜绝未来函数泄漏（Look-ahead Bias）。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **依赖隔离**：`jqdatasdk` 只在 ETL 脚本中被 `import`。核心框架层（`ams/core/`）完全不需要知道 JQData 的存在。
- **数据结构约定**：`HistoryDataFeed.get_data()` 返回的标准数据结构需统一定义为 Pandas DataFrame，列名要求清晰标准化（如 `ticker`, `close`, `volume`, `premium_rate`, `is_st`, `is_redeemed` 等），为下游 `CBRotationStrategy` 提供一致性输入。
- **性能优化**：`HistoryDataFeed` 初始化时使用 Pandas `read_csv` 并按日期设置好 Index，以保证 `get_data` 切片操作在 O(1) 或极短时间内完成。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: JQData 离线数据同步**
  - **Given** 正确的环境变量 `JQDATA_USER` 和 `JQDATA_PWD`
  - **When** 运行 `scripts/jqdata_sync_cb.py` 并指定时间区间
  - **Then** 脚本能成功连接 JQData 并生成本地包含完整因子列的 CSV 文件。

- **Scenario 2: DataFeed 历史数据切片**
  - **Given** 一个预先准备好的本地假测试 CSV 数据文件
  - **When** 实例化 `HistoryDataFeed` 并调用 `get_data('2024-02-05')`
  - **Then** 返回的 DataFrame 只包含 '2024-02-05' 当天的数据，绝不能包含 2月6日及以后的数据，如果没有数据则返回空 DataFrame。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **核心质量风险**：未来函数泄漏（读到了明天的数据）与 JQData SDK 滥用。
- **Mocking 要求**：
  - 在单元测试 `test_jqdata_sync_cb.py` 中，必须通过 `unittest.mock` 完全 Mock 掉 `jqdatasdk` 的网络调用（`auth`, `get_price` 等），验证数据的组装和保存逻辑是否正确。**严禁在跑 CI 时进行真实的 JQData 登录。**
- **DataFeed 测试**：
  - 在 `test_history_datafeed.py` 中，使用一个手动构建的、只有几行数据的微型假 CSV（Mock CSV）进行测试，验证切片的正确性。

## 6. Framework Modifications (框架防篡改声明)
- 允许创建/修改 `ams/core/history_datafeed.py`。
- 允许创建 `scripts/jqdata_sync_cb.py`。

## 7. Hardcoded Content (硬编码内容)
- None