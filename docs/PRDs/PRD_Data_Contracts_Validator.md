---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Data_Contracts_Validator

## 1. Context & Problem (业务背景与核心痛点)
为了防止上游数据源（JQData/AkShare）异常返回“脏数据”（NaN、极值）导致黄金数据集（Golden Dataset）被永久污染，必须建立独立的“数据熔断机制（Data Circuit Breaker）”。之前被驳回的方案将硬编码业务阈值耦合在了 Python 逻辑中，触犯了 Magic Numbers 反模式，且在验收标准中缺乏严格的报错模板防幻觉设定。我们需要遵循业界最佳实践，引入声明式 Schema 框架（Pandera）将检查引擎与具体规则解耦。

## 2. Requirements & User Stories (需求定义)
1. **引入声明式校验框架**：将 `pandera` 确立为项目的核心数据校验依赖。
2. **独立组件与规则解耦**：创建 `ams/validators/cb_data_validator.py`，使用 Pandera DataFrameSchema 声明业务规则，杜绝类内硬编码 `if/else` 阈值。
3. **两栖调用支持**：
   - **API 调用**：供 ETL 脚本校验临时 DataFrame。
   - **CLI 调用**：提供 `--csv` 参数，用于人工/CI 脚本对现存的 CSV 数据库进行巡检。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
目标模块: `ams/validators/cb_data_validator.py`

**技术实现路径：**
1. **Schema 声明 (基于 Pandera)**：
   在文件头部声明 `cb_schema = pa.DataFrameSchema(...)`，约束以下条件：
   - `ticker` (str): 非空
   - `date` (str/datetime): 非空
   - `close` (float): `> 0`, 非空
   - `premium_rate` (float): 在 `[-10.0, 100.0]` 之间, 非空
   - `is_st` (bool): 非空
   - `is_redeemed` (bool): 非空
2. **核心类设计**：
   `CBDataValidator` 类封装对 `cb_schema.validate(df)` 的调用。如果捕获到 `pa.errors.SchemaError`，需打印日志并返回 `False`。
3. **依赖注入**：
   由于 AMS 项目目前缺失统一的依赖管理，必须在项目根目录创建 `requirements.txt` 并写入 `pandera`。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 完美数据集通过校验**
  - **Given** 一个包含正确字段且无缺失值的 DataFrame
  - **When** 调用 `CBDataValidator.validate_dataframe`
  - **Then** 返回 `True`。
- **Scenario 2: 拦截脏数据并精准报错 (防幻觉检查)**
  - **Given** 一个 `premium_rate` 包含 NaN 的 DataFrame
  - **When** 调用验证接口
  - **Then** 返回 `False`。
  - **Then** 必须在终端和日志中输出由 Pandera 抛出的完整异常栈，且最后一行必须符合 Section 7 中的模板格式（包含 SchemaError 和具体行号）。
- **Scenario 3: 依赖文件生成**
  - **Given** 执行完毕的 Coder 会话
  - **When** 检查工作区
  - **Then** `requirements.txt` 必须存在且包含 `pandera`。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **TDD 单元测试**：新建 `tests/test_cb_data_validator.py`。
- 构造合法 DataFrame 断言通过。
- 构造 `close = -1`、`is_st = NaN` 等多种恶意 DataFrame，断言其被成功拦截。

## 6. Framework Modifications (框架防篡改声明)
- 无

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: 初始方案，被 Auditor 驳回（理由：缺失防幻觉报错模板，且触犯 Magic Numbers 反模式）。
- **v2.0**: 全面重构，引入 Pandera 进行声明式解耦，并在 Section 7 补齐日志契约。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、配置文件等），**PM 必须在此处使用 Markdown 代码块一字不落地定义清楚**。

- **`requirements.txt` 内容**:
```text
pandera>=0.20.0
```

- **报错日志预期格式 (必须暴露 Pandera 的 SchemaError 信息)**:
对于 Scenario 2 中失败的捕获，日志输出模块必须严格包含以下字符串（占位符部分可变）：
`"[DataContractViolation] Validation failed due to SchemaError: <pandera_error_message>"`