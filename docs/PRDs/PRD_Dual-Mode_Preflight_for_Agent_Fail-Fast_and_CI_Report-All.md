---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Dual-Mode Preflight for Agent Fail-Fast and CI Report-All

## 1. Context & Problem (业务背景与核心痛点)
`AMS` 已经在 EPIC #3（Preflight Stabilization → GitHub CI Gate for AMS）下完成了两类关键前置治理：

- 已引入 GitHub Actions preflight soft gate：`.github/workflows/preflight.yml` 真实调用 `bash preflight.sh`
- 已引入 config-driven debt quarantine：`preflight.sh` 通过 `ignore_tests.json` + `scripts/preflight_ignore_manifest.py` 校验并构造 `pytest --ignore=...` 参数

但 AMS 当前的 `preflight.sh` 仍然只有单一执行模式，本质上是：

1. Python 全局语法编译检查（`py_compile`）
2. ignore manifest contract 校验
3. 单次 `pytest "${PYTEST_IGNORE_ARGS[@]}"`

当前默认行为是合理的 fail-fast：
- 对 agent / SDLC / coder / reviewer 而言，输出短、行动点集中、token 成本低；
- 一旦前置条件（如 manifest contract）失败，立即停止也符合 gate 语义。

但对 GitHub CI / human audit 而言，当前模式存在两个问题：

1. **CI failure surface 暴露密度不足**
   - GitHub run 主要价值是做 shared failure surface；
   - 但当前 preflight 仍完全沿用 agent-facing 输出策略，失败信息更偏“快速阻断”，不够偏“审计与回溯”。

2. **AMS 的 preflight 结构与多-runner orchestrator 不同**
   - 它不是一长串相互独立的 top-level checks；
   - 真正的大 failure surface 基本都集中在 `pytest`；
   - 前两个步骤更像 hard prerequisites，而不是适合“失败后继续累计”的业务检查项。

因此，AMS 的 dual-mode preflight 目标不应机械照抄其他仓库的“顶层多 step 失败累积器”，而应围绕 AMS 当前结构做一个更瘦、更贴合现状的方案：

> **保持 `bash preflight.sh` 作为唯一权威 gate 入口；默认仍为 agent-facing fail-fast；显式提供一个 CI/human-audit-facing 的 `--report-all` 模式，但只对真正值得扩展 failure surface 的测试主面（即 pytest）增强可观测性，而不放松前置 gate 的 fail-fast 语义。**

本 PRD 不覆盖：
- 重新设计整个 AMS preflight 架构
- 新增第二套独立的 CI gate 命令链
- 将所有 preflight 子检查拆成独立 runner 并做大规模 orchestration
- 改变 `ignore_tests.json` 的 quarantine contract
- 修复当前所有 pytest 失败
- 将 GitHub Actions 升级为 required merge gate（那属于 EPIC #3 后续阶段）

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须保留 `bash preflight.sh` 作为唯一权威 gate 入口**
   - 本地、agent、SDLC、GitHub Actions 都继续通过同一个脚本进入 preflight；
   - 不允许额外发明一套与 `preflight.sh` 分叉的 report-only CI 命令链。

2. **必须支持两种显式模式**
   - 默认模式：fail-fast
   - 显式模式：report-all（例如 `bash preflight.sh --report-all`）

3. **默认模式必须保持向后兼容**
   - `bash preflight.sh` 的现有默认行为不能被破坏；
   - 现有本地开发 / SDLC / coder / reviewer 仍得到短而可执行的 fail-fast 输出。

4. **模式切换必须通过显式 flag 完成**
   - 例如 `--report-all`；
   - 不允许通过 GitHub 环境变量、CI 检测、主机名、魔法 auto-detect 等隐式切换。

5. **前置 gate 必须继续 hard fail-fast**
   - Python 全局语法编译检查失败时，preflight 必须立即失败；
   - ignore manifest contract 校验失败时，preflight 必须立即失败；
   - `--report-all` 不得把这些 prerequisite failure 伪装成“继续跑后续测试也无所谓”。

6. **两种模式必须共享同一套真实 pytest gate surface**
   - fail-fast 与 report-all 运行的仍是同一条 pytest 主路径；
   - 它们的区别只能是 failure reporting / observability policy，不是测试集合分叉。

7. **report-all 的增强重点必须落在 pytest failure observability 上**
   - 在 `--report-all` 下，pytest 仍应完整运行，并在输出末尾提供更适合 CI / human audit 使用的 failure summary；
   - summary 必须便于快速识别失败测试、构造 backlog、进行 failure audit。

8. **report-all 仍必须 truthful fail**
   - 只要 `pytest` 或任一前置 gate 失败，最终退出码必须非 0；
   - 不允许因收集了更多失败信息就把失败包装成 success。

9. **GitHub Actions preflight workflow 应切到 report-all 模式**
   - `.github/workflows/preflight.yml` 应调用 `bash preflight.sh --report-all`；
   - 本地 / agent / SDLC 默认仍调用 `bash preflight.sh`。

10. **日志策略必须继续兼顾 token discipline**
   - 默认 fail-fast 模式继续保持简洁；
   - report-all 模式可以更偏 CI/human audit，但仍需避免无限噪音输出。

### Non-Functional Requirements

1. **single gate 语义必须保持不变**
   - 不能因为引入 dual-mode 就制造第二套权威性来源。

2. **truthfulness 不得削弱**
   - fail-fast 与 report-all 都必须保持真实红/绿语义；
   - 不允许 fake green。

3. **方案必须贴合 AMS 现状，而非过度设计**
   - 不要求将 `preflight.sh` 重构为复杂的多-runner orchestration engine；
   - 只在当前结构最有收益的层面引入 dual-mode。

4. **blast radius 必须最小化**
   - 优先修改 `preflight.sh` 的参数解析、pytest 调用和 failure summary 行为；
   - 尽量减少对已有 quarantine contract 的扰动。

### User Stories

- **As an SDLC operator**, I want `bash preflight.sh` to remain fail-fast by default so agent loops stay compact and actionable.
- **As a maintainer**, I want GitHub CI to expose a richer pytest failure surface in one run so I can audit and split follow-up work faster.
- **As a reviewer**, I want both local and CI execution to stay on the same gate entrypoint so there is only one truth model.
- **As an architect**, I want AMS to adopt dual-mode preflight in a way that fits its current structure, rather than importing an overbuilt orchestration pattern from another repo.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
AMS 应采用 **single-gate / dual-output-policy** 的轻量方案，而不是“顶层所有步骤都可累计失败”的重型 orchestrator。

### 3.1 核心设计原则

1. **One gate, two modes, one truth model**
   - 唯一 gate 入口仍是 `bash preflight.sh`；
   - 两个模式共享同一个 truth surface。

2. **Hard prerequisites remain fail-fast**
   - `py_compile` 与 manifest contract validation 仍然是 preconditions；
   - 它们失败后继续跑 pytest 的信息价值很低，且会污染 failure semantics。

3. **Only expand observability where AMS actually needs it**
   - AMS 当前最大的 failure surface 是 pytest；
   - dual-mode 的主要价值应落在 pytest 输出与汇总方式，而不是把顶层 runner 变成复杂失败累积器。

4. **CI uses report-all; local/agent keeps fail-fast default**
   - 本地与 agent 路径重视短回路；
   - GitHub CI 重视 shared audit surface。

### 3.2 当前 AMS preflight 结构与设计含义

当前 `preflight.sh` 顺序为：

1. `find ... | xargs python3 -m py_compile`
2. `python3 scripts/preflight_ignore_manifest.py --manifest ignore_tests.json --repo-root ...`
3. `pytest "${PYTEST_IGNORE_ARGS[@]}"`

这意味着：
- 前两个步骤是 prerequisite checks；
- 第三个步骤才是主要质量面；
- 因此 dual-mode 不应要求“前两个失败后继续收集更多失败”，否则既不自然也没有太高信息价值。

### 3.3 推荐实现路径

1. **新增 mode 参数解析**
   - 默认 `MODE=fail-fast`
   - 显式 `--report-all` 切换到 `MODE=report-all`
   - 对未知参数 fail-closed

2. **保留前置 gate 的立即失败语义**
   - `py_compile` 失败：立即打印失败详情并退出
   - manifest helper 失败：立即打印失败详情并退出

3. **对 pytest 引入 dual-mode 行为差异**
   - `fail-fast` 模式：
     - 保持当前简洁 gate 体验；
     - 允许继续使用现有的默认 pytest 调用与日志截断策略。
   - `report-all` 模式：
     - 仍然运行同一条 pytest 主路径；
     - 但输出与摘要应更有利于 CI/human audit；
     - 目标是让 failure summary 明确暴露 failed tests / short summary info / 可用于 backlog formation 的信息。

4. **在 preflight 末尾提供 report-all 专属汇总**
   - 若 pytest 失败，`--report-all` 模式下必须输出一个确定性的结尾摘要块；
   - 该摘要块必须以固定起始行开始：
     - `=== REPORT-ALL SUMMARY ===`
   - 该摘要块必须至少包含以下固定前缀行：
     - `MODE: report-all`
     - `PYTEST RESULT:`
     - `FAILED TESTS:`
     - `SHORT SUMMARY INFO:`
   - 该摘要块必须以固定结束行结束：
     - `=== END REPORT-ALL SUMMARY ===`
   - `FAILED TESTS:` 下必须列出 pytest failure surface 中的 failed test node IDs 或 failed test file entries；
   - `SHORT SUMMARY INFO:` 下必须转录 pytest 的 short summary info 或等价的确定性失败摘要；
   - 该摘要块的目标是让人类与 agent 可稳定提取：
     - 当前模式是否为 report-all
     - pytest 总体结果是否失败
     - 哪些 tests failed
     - 失败摘要是否可直接用于 backlog formation

5. **GitHub Actions workflow 切换调用方式**
   - `.github/workflows/preflight.yml` 中将：
     - `bash preflight.sh`
   - 切为：
     - `bash preflight.sh --report-all`

### 3.4 允许修改的范围

本 PRD 允许修改：
- `/home/openclaw/projects/AMS/preflight.sh`
- `/home/openclaw/projects/AMS/.github/workflows/preflight.yml`
- 与 dual-mode contract 直接相关的最小测试文件
- 如确有必要，用于支撑参数解析或输出汇总的最小辅助脚本

本 PRD 不授权：
- 重新定义 `ignore_tests.json` contract
- 大规模重写 `scripts/preflight_ignore_manifest.py`
- 建立另一套并行 preflight 入口
- 对 pytest 测试集合做与模式绑定的分叉

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Default preflight remains fail-fast**
  - **Given** the AMS repository preflight entrypoint
  - **When** `bash preflight.sh` is executed without extra flags
  - **Then** preflight keeps the existing fail-fast behavior
  - **And** it exits non-zero on any failing prerequisite or pytest failure

- **Scenario 2: Unknown mode flags fail closed**
  - **Given** the AMS preflight entrypoint
  - **When** `bash preflight.sh --some-unknown-flag` is executed
  - **Then** preflight rejects the invocation instead of silently guessing intent
  - **And** it exits non-zero

- **Scenario 3: Syntax compile prerequisite still hard-fails in report-all mode**
  - **Given** a repository state with Python syntax compilation failure
  - **When** `bash preflight.sh --report-all` is executed
  - **Then** preflight fails immediately at the compile gate
  - **And** it does not pretend later pytest output is still meaningful

- **Scenario 4: Ignore manifest prerequisite still hard-fails in report-all mode**
  - **Given** an invalid `ignore_tests.json` or manifest-helper validation failure
  - **When** `bash preflight.sh --report-all` is executed
  - **Then** preflight fails immediately at the manifest contract gate
  - **And** it exits non-zero

- **Scenario 5: Report-all mode preserves the same pytest gate surface**
  - **Given** the same repository state and the same ignore manifest
  - **When** preflight is run in default mode and in `--report-all` mode
  - **Then** both modes execute the same underlying pytest gate surface
  - **And** the difference is limited to reporting / observability behavior rather than a different test set

- **Scenario 6: Report-all mode produces deterministic CI-audit summary**
  - **Given** a repository state where pytest has multiple failures
  - **When** `bash preflight.sh --report-all` is executed
  - **Then** pytest runs to completion as the main test surface
  - **And** the final output contains a summary block beginning with `=== REPORT-ALL SUMMARY ===`
  - **And** the summary block contains lines beginning with `MODE: report-all`, `PYTEST RESULT:`, `FAILED TESTS:`, and `SHORT SUMMARY INFO:`
  - **And** the summary block ends with `=== END REPORT-ALL SUMMARY ===`
  - **And** preflight exits non-zero

- **Scenario 7: GitHub Actions uses report-all while local default remains unchanged**
  - **Given** the AMS GitHub Actions preflight workflow
  - **When** the workflow is inspected after this change
  - **Then** CI invokes `bash preflight.sh --report-all`
  - **And** the repository still supports local default execution via `bash preflight.sh`

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
最大的风险不是“加一个 flag”，而是把 AMS 的 preflight 双模式做成语义混乱：
- 要么把 prerequisite failure 也强行 report-all，导致 gate 失真；
- 要么引入第二套 pytest surface，导致 CI 与本地不再共享同一真相；
- 要么输出增强做得太重，反而把 token discipline 和可读性打坏。

### Verification Strategy

1. **CLI contract tests**
   - 验证默认无参为 fail-fast
   - 验证 `--report-all` 可被识别
   - 验证未知参数 fail-closed

2. **Prerequisite behavior tests**
   - 针对 `py_compile` failure 做最小黑盒验证，确认在 `--report-all` 下仍立即失败
   - 针对 manifest validation failure 做最小黑盒验证，确认在 `--report-all` 下仍立即失败

3. **Pytest reporting behavior tests**
   - 通过受控失败样例验证：
     - 默认模式保持原有 gate 体验
     - `--report-all` 模式下输出包含确定性的 summary block
     - summary block 的起止行与固定字段前缀可被黑盒断言
   - 如果需要 mock，应优先 mock pytest invocation/output surface，而不是真实篡改大批业务测试

4. **Workflow contract tests**
   - 以 repo-local 静态/文本级验证确保 `.github/workflows/preflight.yml` 调用的是 `bash preflight.sh --report-all`
   - 这类合同正确性不依赖每轮都打真实 GitHub witness

5. **Witness boundary and ownership contract**
   - **In scope / coder-owned**：repo-local verification、脚本级行为验证、最小黑盒合同测试、以及 workflow 文件的静态合同验证。
   - **Out of scope for coder completion**：`git push`、创建或更新远端 PR、点击 GitHub UI 手动触发流程、修改 branch protection / required checks、以及任何依赖 repo 外权限的 GitHub 管理动作。
   - **Live GitHub Actions witness** 仅作为 human/operator 可选的低频外部见证，不是 coder 完成条件，也不是 SDLC 自动闭环的必需项。
   - coder / reviewer / verifier 的完成不要求真实远端 GitHub run 已被触发、采集或通过；只要求 repo-local correctness evidence 完整成立。

6. **Minimal live validation guidance**
   - 本次 SDLC 的主要 correctness 应来自 repo-local contract tests 与脚本级行为验证；
   - 如需额外 witness，可在合并前后由 human/operator 低频触发一次真实 GitHub Actions run，观察 report-all 输出是否更有 backlog 价值；
   - 该 live witness 明确属于 SDLC automatic closure 之外的外部验收动作。

### Quality Goal
交付后的 AMS preflight 应满足：
- 默认模式仍适合 agent loop
- CI 模式更适合 failure audit
- 两者仍共享同一条真实 gate surface
- prerequisite 与 pytest reporting 的边界清晰、不混乱
- coder 的完成条件不依赖 repo 外权限或 live GitHub witness

## 6. Framework Modifications (框架防篡改声明)
- `/home/openclaw/projects/AMS/preflight.sh`
- `/home/openclaw/projects/AMS/.github/workflows/preflight.yml`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 初稿采用轻量 dual-mode 方案：single gate 不变，hard prerequisites 继续 fail-fast，仅增强 pytest 在 CI / human audit 场景下的 failure summary。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact CLI Flag Contract
- **Report-all mode flag**:
```text
--report-all
```

### Exact Workflow Invocation Contract
- **GitHub Actions preflight command**:
```text
bash preflight.sh --report-all
```

### Exact Report-All Summary Markers
- **Summary block start line**:
```text
=== REPORT-ALL SUMMARY ===
```

- **Summary block end line**:
```text
=== END REPORT-ALL SUMMARY ===
```

### Exact Report-All Summary Field Prefixes
- **Mode line prefix**:
```text
MODE: report-all
```

- **Pytest result line prefix**:
```text
PYTEST RESULT:
```

- **Failed tests section header**:
```text
FAILED TESTS:
```

- **Short summary info section header**:
```text
SHORT SUMMARY INFO:
```
