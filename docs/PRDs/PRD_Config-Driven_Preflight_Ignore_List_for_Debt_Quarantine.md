---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Config-Driven Preflight Ignore List for Debt Quarantine

## 1. Context & Problem (业务背景与核心痛点)
`AMS` 当前的 `preflight.sh` 被一批已知 failing tests 卡住，导致项目在当前状态下很难稳定地把 preflight 作为本地 gate 使用。

我们已经做过一次本地临时实验，通过暂时取消 fail-fast，拿到了一个较完整的 failure surface。实验结果表明，AMS 当前不是“失败面未知”，而是已经有一组**明确可列举的 failing test files**。

当前已知 failing test files 为：

- `tests/test_data_source.py`
- `tests/test_execution_arbitration.py`
- `tests/test_execution_semantics_stop_loss.py`
- `tests/test_finance_fetcher.py`
- `tests/test_main_runner.py`
- `tests/test_main_runner_smoke.py`
- `tests/test_order_semantics_e2e.py`
- `tests/validation/test_golden_integrity.py`
- `tests/validation/test_path_consistency.py`
- `tests/validation/test_smoke.py`

当前 `pytest` 结果摘要：
- 27 failed
- 349 passed
- 4 skipped

这说明现在最缺的不是继续人工 hack `preflight.sh`，而是一个更正式、可测试、可审计的**debt quarantine 机制**，使得：

- preflight 可以在债务存在时恢复为一个明确的“quarantine green”状态；
- 被隔离的 failing files 作为显式数据面存在；
- 后续可以再逐批修复并清零该 debt list。

因此，本 PRD 的目标是：

> **为 AMS 引入一个 config-driven 的 preflight ignore list 机制，把当前已知 failing tests 从脚本内临时绕过逻辑，转为外部可测试、可审计、可清零的数据面。**

本 PRD 不覆盖：
- 后续逐批修复被隔离的 failing files
- 最终 true-green 恢复
- GitHub CI 接入
- 其他更广泛的 test architecture 重构

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **preflight 必须支持外部 ignore list 配置文件**
   - `preflight.sh` 必须从一个外部 JSON 文件读取当前被隔离的测试清单。

2. **ignore list 必须 fail-closed**
   - 如果配置文件缺失、语法错误、格式错误或结构不合法，preflight 必须失败，而不是静默继续。

3. **ignore list 必须支持按测试类型分组**
   - 至少支持：
     - `pytest`
   - 如果未来 AMS 还需要其他测试类型，可以再扩展，但本 PRD至少要把 pytest 这条主线做清楚。

4. **本 PRD 必须给出当前已知 failing files 的精确 seed manifest**
   - 不允许只给一个示例配置。
   - 必须把当前 AMS 已知 failing file 清单精确写入初始 `ignore_tests.json` contract。

5. **preflight 必须在 ignore list 非空时恢复为“quarantine green”**
   - 当 ignore list 非空时，preflight 允许跳过配置中列出的 failing files。
   - 这个通过状态是 debt-quarantine green，而不是最终 true green。

6. **必须支持 ignore list 最终清零**
   - 该机制的存在目的是临时隔离 debt，而不是永久保留白名单。
   - 后续阶段必须能够把它逐步清空。

### User Stories

- **As an AMS maintainer**, when a known set of failing tests prevents preflight from being useful, I want a config-driven quarantine list so I can recover a controlled green gate state.
- **As an architect**, I want the quarantine mechanism to live in data rather than hidden shell logic so the debt is visible and governable.
- **As a reviewer**, I want the preflight behavior under non-empty vs empty ignore list to be black-box testable.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用**配置驱动的 debt quarantine**，但该配置不是“方便绕过失败测试的白名单”，而是一个**严格校验、fail-closed、可清零的 quarantine manifest contract**。

### 3.1 设计原则

1. **把 bypass 从 shell 分支逻辑里拿出来，放到外部数据面**
   - `preflight.sh` 只消费 `ignore_tests.json`。
   - 不再把当前债务隔离策略硬编码在脚本里。

2. **把“假绿”变成显式 contract**
   - non-empty ignore list → quarantine green
   - canonical empty ignore list → full normal preflight

3. **fail-closed**
   - ignore 配置坏了，gate 必须失败。

4. **结构化数据必须由结构化解析器处理**
   - `preflight.sh` 不得使用 `grep` / `sed` / `awk` / 字符串 split 等 shell 文本技巧直接解析 JSON。
   - `ignore_tests.json` 的读取、结构校验、语义校验必须委托给 Python 3 标准库 JSON 解析路径完成。
   - shell 只负责 orchestration；结构化 manifest 的解释权属于确定性的 Python helper / inline Python validation step。

### 3.2 `ignore_tests.json` 合同结构

本 PRD 定义的唯一合法 manifest 形态为：

```json
{
  "pytest": [
    "tests/test_data_source.py",
    "tests/test_execution_arbitration.py",
    "tests/test_execution_semantics_stop_loss.py",
    "tests/test_finance_fetcher.py",
    "tests/test_main_runner.py",
    "tests/test_main_runner_smoke.py",
    "tests/test_order_semantics_e2e.py",
    "tests/validation/test_golden_integrity.py",
    "tests/validation/test_path_consistency.py",
    "tests/validation/test_smoke.py"
  ]
}
```

约束如下：

- 顶层必须是 JSON object；
- 顶层必须且只能包含当前已定义的测试类型键；本 PRD 当前唯一允许的键为 `pytest`；
- `pytest` 的值必须是数组；
- 数组元素必须全部为字符串；
- 空 manifest 的唯一合法形态为：

```json
{
  "pytest": []
}
```

- `{}`、缺失 `pytest` 键、`null`、空字符串、对象或其他变体均不属于合法空态。

### 3.3 `ignore_tests.json` 语义校验规则

对 `pytest` 数组中的每个 entry，必须同时满足以下约束：

1. 必须是 repo-relative path；
2. 必须位于 `tests/` 目录下；
3. 必须指向当前仓库中真实存在的文件；
4. 必须是 `.py` 测试文件；
5. 不允许重复 entry；
6. 不允许 absolute path；
7. 不允许 `..` 或其他目录逃逸；
8. 不允许 glob、目录路径或通配式测试选择器；
9. 任一 entry 违反上述任一规则时，preflight 必须 fail-closed。

这意味着本方案校验的不只是“JSON 能否 parse”，还包括 manifest 是否仍然语义有效、没有 stale debt、没有越界豁免。

### 3.4 `preflight.sh` 行为

- `preflight.sh` 在运行 `pytest` 前，必须先通过 Python 3 标准库 JSON 解析路径读取并校验 `ignore_tests.json`；
- 若 manifest 结构非法或语义非法，preflight 必须立即失败，不得退化为“继续跑完整 pytest”或“静默忽略坏配置”；
- 当 `ignore_tests.json` 为合法非空 manifest 时，`pytest` 调用应通过逐项构造 `--ignore=<file>` 参数忽略其中列出的测试文件；
- 当 `ignore_tests.json` 等于 canonical empty manifest（即 `{"pytest": []}`）时，恢复完整 pytest test surface；
- `preflight.sh` 不得自行在 shell 中解析 JSON 文本内容。

### 3.5 目标修改点

本 PRD 允许修改：
- `AMS/preflight.sh`
- `AMS/ignore_tests.json`（新增）
- 用于 manifest 解析/校验的最小辅助实现（新增，若需要）
- 与 ignore 行为直接相关的最小验证测试文件（新增）

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Non-empty ignore list produces debt-quarantine green**
  - **Given** a valid non-empty `ignore_tests.json`
  - **When** `preflight.sh` is executed
  - **Then** the tests listed in the JSON are ignored via constructed `pytest --ignore` arguments
  - **And** preflight completes successfully

- **Scenario 2: Canonical empty ignore list restores full preflight**
  - **Given** `ignore_tests.json` equals exactly the canonical empty manifest
  - **When** `preflight.sh` is executed
  - **Then** it runs the full normal pytest test surface

- **Scenario 3: Missing ignore configuration fails closed**
  - **Given** `ignore_tests.json` is missing
  - **When** `preflight.sh` is executed
  - **Then** preflight fails instead of silently bypassing the configuration problem

- **Scenario 4: Malformed ignore configuration fails closed**
  - **Given** `ignore_tests.json` is malformed JSON or violates the required top-level structure
  - **When** `preflight.sh` is executed
  - **Then** preflight fails instead of silently bypassing the configuration problem

- **Scenario 5: Duplicate ignored path fails closed**
  - **Given** a syntactically valid `ignore_tests.json` containing the same pytest file more than once
  - **When** `preflight.sh` is executed
  - **Then** preflight fails closed

- **Scenario 6: Nonexistent ignored path fails closed**
  - **Given** a syntactically valid `ignore_tests.json` containing a pytest path that does not exist in the repo
  - **When** `preflight.sh` is executed
  - **Then** preflight fails closed

- **Scenario 7: Out-of-scope ignored path fails closed**
  - **Given** a syntactically valid `ignore_tests.json` containing a path outside `tests/`, an absolute path, or a parent-traversing path
  - **When** `preflight.sh` is executed
  - **Then** preflight fails closed

- **Scenario 8: Seed manifest matches the current known AMS failure surface**
  - **Given** the current known AMS failing file inventory
  - **When** the initial `ignore_tests.json` is created
  - **Then** it contains that exact seed file set rather than a placeholder example

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
最大的风险不是隔离已知 failing files，而是把 quarantine 机制本身做成不透明、不可测试、不可清零、会 silently rot 的长期绕过。

### Verification Strategy

1. **Manifest structure tests**
   - 验证只接受规定顶层结构与规定键集。
   - 验证 canonical empty manifest 形态被唯一识别。

2. **Manifest semantic validation tests**
   - 验证 duplicate / nonexistent / out-of-scope / non-file / non-`.py` entry 都会 fail-closed。

3. **Config behavior tests**
   - 验证合法 non-empty ignore list 能恢复 preflight 为 quarantine green。
   - 验证 canonical empty ignore list 能恢复 full preflight。

4. **Fail-closed tests**
   - 验证配置缺失、损坏、结构不合法、语义不合法时 preflight 必须失败。

5. **Seed manifest verification**
   - 验证初始 `ignore_tests.json` 精确反映当前已知 AMS failure surface。

### Quality Goal
把 AMS 当前的 preflight debt 隔离逻辑从手工临时实验升级成一个**配置驱动、严格校验、可审计、可清零、不会 silently rot 的 quarantine 机制**。

## 6. Framework Modifications (框架防篡改声明)
- `AMS/preflight.sh`
- `AMS/ignore_tests.json`（新增）
- 用于 manifest 解析/校验的最小辅助实现（新增，若需要）
- 与 ignore 行为直接相关的最小验证测试（新增）

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: 通过一次本地临时非 fail-fast 实验拿到 AMS 当前较完整的 failing-file 清单。
- **v2.0 Revision Rationale**: 基于该清单，收缩为 config-driven preflight debt quarantine 方案，不在本 PRD 中处理后续 true-green 修复。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

- **`ignore_json_filename`**:
```text
ignore_tests.json
```

- **`ignore_json_seed`**:
```json
{
  "pytest": [
    "tests/test_data_source.py",
    "tests/test_execution_arbitration.py",
    "tests/test_execution_semantics_stop_loss.py",
    "tests/test_finance_fetcher.py",
    "tests/test_main_runner.py",
    "tests/test_main_runner_smoke.py",
    "tests/test_order_semantics_e2e.py",
    "tests/validation/test_golden_integrity.py",
    "tests/validation/test_path_consistency.py",
    "tests/validation/test_smoke.py"
  ]
}
```

- **`ignore_json_empty_seed`**:
```json
{
  "pytest": []
}
```

- **`manifest_parser_contract`**:
```text
preflight.sh must not parse ignore_tests.json with grep, sed, awk, or string splitting. JSON parsing and manifest validation must be performed through a deterministic Python 3 standard-library JSON path before pytest arguments are constructed.
```

- **`manifest_semantic_validation_rules`**:
```text
Each pytest ignore entry must be a unique repo-relative path to an existing .py test file under tests/. Absolute paths, parent-directory traversal, directories, globs, duplicate entries, and nonexistent files are invalid. Any invalid entry must cause preflight to fail closed.
```

- **`fail_closed_statement`**:
```text
If ignore_tests.json is missing, malformed, structurally invalid, or semantically invalid, preflight must fail closed.
```
