---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Preflight Ignore Manifest Logic and Audit-Mode Contract

## 1. Context & Problem (业务背景与核心痛点)
AMS 的 preflight 体系已经逐步从本地脆弱检查演进为 GitHub CI 上的可观测质量门。随着 `ignore_tests.json` 被引入，当前系统已经具备一套 quarantine 机制：当某些测试暂时不应阻塞 preflight 时，系统会读取 ignore manifest 并把对应测试通过 `--ignore=...` 传给 pytest。

但在针对 `NO_IGNORE` / full-failure witness 的审计流程中，团队需要临时清空 `ignore_tests.json`，以暴露完整 failure surface。这个操作本身是合理且必要的；问题在于，当前有 3 个 ignore-manifest 自测试把“当前 seed quarantine list 的具体内容”写死成长期真理：
- `tests/test_preflight_ignore_manifest.py::test_seed_manifest_matches_current_known_failure_surface`
- `tests/test_preflight_ignore_manifest.py::test_helper_builds_ordered_pytest_ignore_args_from_seed_manifest`
- `tests/test_preflight_ignore_manifest.py::test_helper_cli_emits_ordered_pytest_ignore_args_from_seed_manifest`

结果是：当 `ignore_tests.json` 被清空时，CI 会因为这 3 个测试失败而报红，即使真实产品 failure surface 已经变化，甚至即使被历史 quarantine 的测试已经重新变绿。

这说明当前问题不是产品行为出错，而是测试把“某个阶段的治理状态”误写成了“永久 contract”。后续 AMS 很可能会逐步缩短 ignore list，甚至在某些阶段完全清空它；因此 ignore-manifest 相关测试不能假定该文件的内容恒定不变。

本 PRD 的目标是把 ignore-manifest 自测试重构为“manifest 处理逻辑 contract”测试，而不是“固定 seed 内容 contract”测试，使 AMS 能够：
- 正常读取非空 ignore list 并正确构造 pytest ignore 参数
- 正确处理空 list
- 正确处理 manifest 缺失或字段缺失
- 在 full-failure audit 中不制造人为红噪音

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements
1. AMS 必须把 ignore-manifest 的 contract 定义为“处理逻辑 contract”，而不是“固定文件内容 contract”。
2. 当 `ignore_tests.json` 存在且 `pytest` 列表非空时，preflight helper 必须按 manifest 顺序生成对应的 `--ignore=<path>` 参数。
3. 当 `ignore_tests.json` 存在但 `pytest` 列表为空时，preflight helper 必须返回空 ignore 参数列表；preflight 不应忽略任何测试。
4. 当 `ignore_tests.json` 缺失，或 manifest 中缺失 `pytest` 字段时，系统必须有明确、稳定、可测试的行为。该 PRD 规定该行为等价于“空 ignore list”，即：不忽略任何测试。
5. ignore-manifest 相关测试必须基于可控 fixture / 临时 manifest 输入验证处理逻辑，不得直接把仓库当前真实 `ignore_tests.json` 的内容写死为测试常量。
6. 现有 3 个失败测试必须被重构或替换，使其覆盖以下情形：
   - 非空 manifest
   - 空 manifest
   - manifest 缺失或字段缺失
7. `NO_IGNORE` / full-failure audit 场景下，CI 不得再因为 ignore-manifest 自测试而制造假失败；若 preflight 报红，必须来自真实 failure surface，而不是 quarantine seed 自测试。
8. preflight CLI / helper 层若存在多入口（例如 Python helper 与 shell / CLI 消费路径），这些入口必须对上述三种 manifest 状态表现一致。

### 2.2 Non-Functional Requirements
1. 修复必须尽量小刀，避免把 #11 扩散成大规模 preflight 重写。
2. 测试必须 deterministic，不依赖调用者 cwd、外部环境变量残留、仓库当前真实 ignore list 内容、或历史 quarantine 长度。
3. 设计必须允许未来逐步缩短 ignore list，直到完全清空，而无需同步修改测试中的硬编码列表常量。
4. 设计必须使未来的 full-failure audit 可解释：审计结果中若出现红测，应对应真实产品 / 测试 failure，而不是 ignore seed 自测试噪音。

### 2.3 Scope Boundaries
本 PRD 负责：
- ignore-manifest helper / CLI contract 的澄清
- `tests/test_preflight_ignore_manifest.py` 的重构
- 必要时为 helper/CLI 添加 manifest 路径注入能力，以支持 fixture-driven 测试
- 明确空 manifest / 缺失 manifest 的预期行为

本 PRD 不负责：
- 修改 execution semantics、path contract、main_runner、validator、ETL 等业务逻辑
- 重写整个 preflight framework
- 关闭或重构所有 quarantine 策略本身
- 改变 `ignore_tests.json` 的产品用途（仍然作为 quarantine 输入源）

### 2.4 User Stories
- 作为 preflight 维护者，我希望 ignore-manifest 测试验证的是“读取与转换逻辑”，而不是一份历史列表，这样我逐步缩短 ignore list 时不需要同步修测试常量。
- 作为 full-failure audit 执行者，我希望在清空 `ignore_tests.json` 后，CI 只暴露真实 failure surface，而不是被 ignore-manifest 自测试污染。
- 作为后续维护者，我希望看到清晰的 contract：manifest 非空、为空、缺失时系统分别如何处理。
- 作为审阅者，我希望从测试中直接看出 helper 与 CLI 对 manifest 逻辑的真实行为，而不是混入阶段性治理状态。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Core Design Decision
ignore-manifest 的稳定 contract 不应该是“当前仓库中有哪些测试被忽略”，而应该是“系统如何解析和消费 ignore manifest”。

因此，本次修复的核心决定是：
- 把“seed content assertion”降级为非核心 concern，甚至删除
- 把“manifest parsing + argument emission behavior”升级为真正的 contract

### 3.2 Targeted Surfaces
本 PRD 授权重点修改以下区域：
- `tests/test_preflight_ignore_manifest.py`
- 负责读取 `ignore_tests.json`、构造 pytest ignore 参数、或向 CLI 暴露这些参数的 helper / script
- 如有必要，与该 helper/CLI 配套的轻量测试支持代码

未经明确授权，不应扩散到其他 preflight failure bucket。

### 3.3 Required Behavioral Contract
本 PRD 固定如下行为：

#### Case A — manifest 非空
输入示例：
```json
{"pytest": ["tests/a.py", "tests/b.py"]}
```
预期：
- helper 返回：
  - `--ignore=tests/a.py`
  - `--ignore=tests/b.py`
- 顺序保持与 manifest 一致
- CLI / preflight 消费后实际忽略对应测试

#### Case B — manifest 存在但列表为空
输入示例：
```json
{"pytest": []}
```
预期：
- helper 返回空 ignore 参数列表
- CLI / preflight 不忽略任何测试
- 这属于合法状态，不应报错

#### Case C — manifest 缺失或 `pytest` 字段缺失
输入示例：
```json
{}
```
或 manifest 文件不存在

预期：
- 系统按“空 ignore list”处理
- helper 返回空 ignore 参数列表
- CLI / preflight 不忽略任何测试
- 这属于合法状态，不应为了缺失文件/字段而报错

### 3.4 Test Refactoring Strategy
当前 3 个失败测试的核心问题是：它们直接或间接断言真实 seed manifest 的具体内容。必须改成基于临时 fixture 的 contract tests。

建议测试重构方向如下：

1. 删除或重写“当前 seed manifest 必须等于历史固定列表”的断言
2. 用 `tmp_path` 或等效临时文件机制创建测试专用 manifest
3. 让 helper / CLI 支持注入 manifest 路径，避免测试必须读取仓库真实 `ignore_tests.json`
4. 将测试拆成以下逻辑面：
   - 非空 manifest → 生成有序 `--ignore=` 列表
   - 空 manifest → 生成空列表
   - manifest 缺失 / 字段缺失 → 生成空列表
5. 若当前 CLI/helper 无法接收自定义 manifest 路径，应优先通过最小可审计改动提供这一能力，而不是在测试中 monkeypatch 复杂全局状态

### 3.5 Backward Compatibility Policy
本 PRD 不要求改变 preflight 日常行为。

也就是说：
- 真实仓库里的 `ignore_tests.json` 若非空，日常 preflight 仍按原有 quarantine 机制工作
- 唯一变化是测试不再把这份真实文件的具体内容当成固定常量
- full-audit / `NO_IGNORE` 场景下，清空 manifest 不再导致 ignore-manifest 自测试误报

### 3.6 Anti-Pattern Explicitly Forbidden
本 PRD 明确禁止以下伪修复：
- 仅删除这 3 个测试而不补上逻辑 contract 覆盖
- 保留对仓库真实 seed 内容的硬编码断言，只是把当前常量改成空列表
- 通过额外 if/else 把 `NO_IGNORE` branch 名称写死进业务逻辑
- 通过修改 CI workflow 绕过这 3 个测试，而不修复测试 contract 本身

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Non-empty manifest emits ordered ignore args**
  - **Given** 一个测试专用 ignore manifest，其中 `pytest` 列表包含两个或以上测试路径
  - **When** preflight helper / CLI 读取该 manifest 并构造 pytest ignore 参数
  - **Then** 输出必须包含按原顺序排列的 `--ignore=<path>` 参数列表

- **Scenario 2: Empty manifest means no ignored tests**
  - **Given** 一个测试专用 ignore manifest，其中 `pytest` 为 `[]`
  - **When** preflight helper / CLI 读取该 manifest
  - **Then** 输出必须为空 ignore 参数列表，且系统不报错

- **Scenario 3: Missing manifest behaves like empty manifest**
  - **Given** ignore manifest 文件不存在
  - **When** preflight helper / CLI 尝试读取 manifest
  - **Then** 系统必须按空 ignore list 处理，并返回空 ignore 参数列表，而不是失败

- **Scenario 4: Missing pytest field behaves like empty manifest**
  - **Given** 一个测试专用 manifest 文件存在，但其中不包含 `pytest` 字段
  - **When** preflight helper / CLI 读取该 manifest
  - **Then** 系统必须按空 ignore list 处理，并返回空 ignore 参数列表，而不是失败

- **Scenario 5: NO_IGNORE/full-audit no longer fails due to ignore-manifest self-tests**
  - **Given** 一个 full-failure audit 场景，仓库中的 `ignore_tests.json` 被清空
  - **When** GitHub CI 或本地 report-all preflight 运行
  - **Then** ignore-manifest 自测试不得因为“seed 列表不再等于历史固定内容”而失败

- **Scenario 6: Real seeded manifest still works in daily usage**
  - **Given** 仓库中的真实 `ignore_tests.json` 包含一个非空 `pytest` 列表
  - **When** 日常 preflight 运行
  - **Then** 系统仍必须正确构造并传递 ignore 参数，不得因本次修复破坏已有 quarantine 行为

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
本需求的核心质量风险不是业务逻辑，而是“测试把治理状态误写成产品 contract”。因此测试策略应围绕 helper/CLI 行为的输入输出 contract，而不是围绕某个历史文件快照。

### 5.1 Quality Goal
- ignore manifest 的逻辑处理在非空、空、缺失三种状态下都 deterministic
- full-audit 不再产生 ignore-manifest 假红
- 日常 quarantine 机制不被破坏

### 5.2 Verification Strategy
1. **Unit / focused tests**
   - 使用临时 manifest 文件验证 helper 输出
   - 覆盖非空、空、缺失、字段缺失
2. **CLI-level verification**
   - 若 helper 有 CLI 封装，则验证 CLI 层输出与 helper 一致
3. **Integration smoke**
   - 在本地至少运行相关测试文件
   - 若条件允许，使用 `NO_IGNORE` / 空 manifest 场景验证 report-all 不再因为这 3 个测试失败

### 5.3 Mocking Guidance
- 不需要 mock 真实业务模块
- 可使用 `tmp_path`、monkeypatch、或 manifest path injection 控制测试输入
- 尽量避免依赖仓库当前真实 `ignore_tests.json`

### 5.4 Success Signal
最小成功信号为：
- `tests/test_preflight_ignore_manifest.py` 全绿
- 在空 manifest / `NO_IGNORE` 场景下，这 3 个测试不再失败
- 非空 manifest 场景仍能正确输出 ignore 参数

## 6. Framework Modifications (框架防篡改声明)
- 本 PRD 不授权修改 SDLC 核心框架文件
- 仅授权修改 AMS 仓库内部与 preflight ignore manifest 相关的 helper、脚本与测试文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft created from issue #11 after confirming that `NO_IGNORE` branch CI no longer fails on the historical execution-semantics bucket (#10), but still fails on ignore-manifest self-tests. The design decision is to replace fixed seed-content assertions with fixture-driven manifest logic contract tests.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- None
