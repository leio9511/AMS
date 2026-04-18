---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix_Redemption_Logic_PiT_Compliance

## 1. Context & Problem (业务背景与核心痛点)
在 ISSUE-1142 的实现中，Coder 虽然完成了大部分去 Mock 化工作，但在“强赎状态（is_redeemed）”判定上采取了简化的退市日（delist_date）逻辑。这违反了 Point-in-Time (PiT) 原则，引入了未来函数隐患：策略只能在转债退市当天识别强赎，而无法在公告发出后的第一时刻避险，这会导致回测收益率虚高且无法真实模拟风险规避。

## 2. Requirements & User Stories (需求定义)
1. **接入真实公告数据**：必须查询聚宽 `finance.CCB_CALL`（可转债强赎公告表）获取真实的公告日（pub_date）。
2. **严防未来函数**：判定逻辑必须修改为：`当前日期 >= 公告日` 且 `当前日期 < 退市日` 即视为 `is_redeemed = True`。
3. **数据一致性**：确保新接入的强赎逻辑能正确集成进现有的原子化写入流程，并通过 `CBDataValidator` 校验。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
目标模块: `scripts/jqdata_sync_cb.py`

**技术实现路径：**
1. **数据拉取**：
   - 使用 `jqdatasdk.finance.run_query` 查询 `finance.CCB_CALL` 表。
   - 提取 `code`（转债代码）, `pub_date`（公告日期）, `delisting_date`（退市日期）。
2. **逻辑修复**：
   - **防御性数据预处理**：由于 `finance.CCB_CALL` 是事件级数据（单标的可能对应多条记录），必须先对其按 `ticker` 分组，提取每个标的的最早 `pub_date` 和对应的 `delisting_date`，防止 Left Join 时产生笛卡尔积导致数据行数爆炸。
   - **原子化备份策略**：在执行最终 CSV 覆盖前，脚本必须自动检查并创建备份（如 `data/cb_history_factors.csv.bak`），确保高危修改可回滚。
   - **属性广播关联**：将预处理后的强赎属性与主 OHLCV 数据表进行 Left Join（**仅按 ticker 关联属性，禁止按 date 关联**，以确保属性广播到全时间轴）。
   - **判定公式**：对比每一行的 `date` 与关联到的 `pub_date` 及 `delisting_date`，标记所有满足 `date >= pub_date` 且 `date < delisting_date` 的行。
3. **容错处理**：
   - 对于查询不到强赎公告的转债，默认 `is_redeemed = False`。
   - 确保日期格式统一（Pandas datetime64）。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 强赎避险测试 (PiT 验证)**
  - **Given** 某转债 A 在 2024-04-01 发布强赎公告，2024-04-30 正式退市
  - **When** 运行同步脚本拉取 2024-04-05 的数据
  - **Then** `is_redeemed` 字段必须为 `True`（修复前此处为 False）。
- **Scenario 2: 原子性与校验验证**
  - **Given** 修复后的脚本
  - **When** 执行数据同步并由 `CBDataValidator` 扫描
  - **Then** 校验应顺利通过，且 `data/cb_history_factors.csv` 被正确原子替换。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **回归测试**：运行全量 `preflight.sh`。
- **数据抽样**：手动选取 2 只已知在回测区间内发生强赎的标的，在 CSV 中抽查公告日后、退市日前的时间点，验证 `is_redeemed` 的布尔值是否符合预期。
- **变更前后对比报告**：脚本执行完毕后，必须在日志中输出本次修复影响的总行数（被标记为 `is_redeemed=True` 的新增记录数），作为数据变更的审计轨迹。

## 6. Framework Modifications (框架防篡改声明)
- 无。仅修复业务逻辑脚本。

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: 针对 ISSUE-1142 留下的未来函数漏洞进行专项修复，将强赎逻辑从“退市日判定”升级为“公告日判定”。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 凡是本需求涉及需要精确输出的字符串（如字段名、文件路径、公式逻辑），**PM 必须在此处使用 Markdown 代码块一字不落地定义清楚**，Coder 必须且只能从本章节进行 Copy-Paste，绝对禁止对以下内容进行任何改写或二次加工。

- **目标字段名 (硬编码，禁止改动)**:
```python
"is_redeemed"  # 列名必须精确匹配，大小写敏感
```

- **目标存储路径 (硬编码，禁止改动)**:
```
data/cb_history_factors.csv
```

- **PiT 强赎判定公式 (精确逻辑)**:
```python
# 满足以下条件即标记为 is_redeemed = True:
(date >= pub_date) AND (date < delisting_date)
# 其中 pub_date 和 delisting_date 均来自 finance.CCB_CALL 表
```

- **审计日志格式 (硬编码，禁止改动)**:
```python
"[AUDIT] Redemption records marked True: {} out of {} total rows"
```

- **JQData Finance Table Schema (精确表名和字段)**:
```python
"finance.CCB_CALL"  # 表名必须精确
"code"               # 字段名：转债代码
"pub_date"           # 字段名：强赎公告日
"delisting_date"      # 字段名：正式退市日
```
