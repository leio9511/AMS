---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Introduce_Early_GitHub_CI_for_Preflight_as_a_Soft_Gate

## 1. Context & Problem (业务背景与核心痛点)
`AMS` 当前已经完成了 preflight stabilization EPIC（#3）中的一部分前置治理：

- 已识别并拆分了 preflight 相关的关键治理问题：
  - `#1` 非 root 环境路径硬编码问题
  - `#2` preflight / test dependency contract 不完整问题
- 本地 `preflight.sh` 当前可以在作者机器上跑绿；
- 项目内已经存在与 preflight 稳定化直接相关的 PRD/治理资产，例如：
  - `PRD_Config-Driven_Preflight_Ignore_List_for_Debt_Quarantine.md`
  - `PRD_Fix_CI_Preflight_Script_Auto_Discovery.md`

但这还不等于 AMS 已经拥有一个可信的 GitHub CI gate。

当前真正的缺口是：

1. **preflight 仍主要是本地 gate**
   - 现在的绿灯主要发生在已有机器状态、已有依赖、已有本地上下文之上；
   - 它尚未在 clean GitHub runner 上形成可共享、可重复、可观察的事实面。

2. **本地绿并不能证明 CI 绿**
   - clean runner 会暴露本地环境掩盖的问题，包括：
     - 缺失或不完整的 preflight dependency contract；
     - `/root/...` 或其他 machine-local path 假设；
     - provider/test fixture 的环境耦合；
     - 本地已安装依赖造成的假成功；
     - CI 与本地 preflight 语义分叉。

3. **AMS 当前最危险的 Phase 2 假象是“soft gate = 先接上一个会报红的 workflow 就算完成”**
   - 如果 workflow 主要在 clean runner 上报 `ModuleNotFoundError` / `ImportError` / 明显的 bootstrap 缺口，虽然 technically “CI 跑起来了”，但它产生的是高噪音、低价值的报警面；
   - 这种红灯不能有效支持 failure audit，因为它首先暴露的是 dependency contract 没立住，而不是仓库真实的代码/测试债。

因此，本 PRD 的目标不是“让 AMS 的 GitHub CI 立即 true green”，也不是“先把所有历史 preflight 问题一口气修完”，而是：

> **把 AMS 的 GitHub Actions 建成一个真实执行 `bash preflight.sh`、结果传播准确、对 clean runner 问题可观察、且其大部分 correctness 可由本地 contract tests 验证的 soft-gate CI surface。**

同时，本 PRD 必须明确：

- `soft gate ≠ fake green`
- CI 必须运行仓库真实 gate，而不是另一套近似命令链
- Phase 2 可以接受 truthful red，但不接受主要由模糊 dependency contract 导致的低价值噪音红

本 PRD 不覆盖：

- preflight 历史 failure 的 true-green 全量修复
- 将 GitHub Actions 升级为 required merge gate
- issue sync / PR auto-generation / GitHub adapter infra
- 将所有 provider optional dependency 一次性重构完毕
- AMS 更广义的部署/CD/Windows 节点管理主题（那属于其他 PRD 范畴）

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须在 AMS 仓库内新增 GitHub Actions workflow**
   - workflow 文件必须位于 `.github/workflows/` 下；
   - 初版只处理 AMS preflight soft gate，不混入其他 unrelated CI/CD concerns。

2. **workflow 必须自动触发**
   - 至少支持：
     - `push`
     - `pull_request`

3. **workflow 必须执行真实 preflight 入口**
   - CI job 必须调用真实的：
     - `bash preflight.sh`
   - 不允许用一组“看起来差不多”的散装命令替代仓库 gate 入口。

4. **workflow 必须在 clean GitHub-hosted runner 上运行**
   - 初版使用 GitHub-hosted runner 即可；
   - 其目标是暴露 machine-local success condition 之外的问题。

5. **必须使用已验证的 preflight dependency contract，再接 workflow**
   - 本 PRD 不要求最终把 AMS 全仓库依赖体系设计完；
   - 但要求 CI bootstrap 必须直接依赖当前仓库内**已通过 clean-environment 验证**的 preflight/test dependency baseline；
   - 当前基线文件明确为：
     - `requirements-test.txt`
   - 不得继续依赖作者机器上手工残留的包状态；
   - 如未来要进一步瘦身或重构依赖分层，那属于后续优化，不影响本 Phase 2 基线的确定性。

6. **workflow 允许 minimal bootstrap，但其边界必须被明确约束**
   - bootstrap 的目的仅限于让 clean runner 具备执行当前仓库 `preflight.sh` 的前提；
   - bootstrap 必须安装当前仓库内已验证的 preflight/test dependency baseline：
     - `requirements-test.txt`
   - bootstrap 不得变成另一套独立 gate；
   - bootstrap 不得通过条件跳过、吞错、环境短路或假成功包装掩盖真实问题。

7. **workflow 初期必须作为 soft gate 使用**
   - 其结果必须可见、可重复、可用于 Phase 3 failure audit；
   - 本阶段不要求其成为 required merge blocker；
   - 但也不允许通过 `continue-on-error` 或等效 masking 伪造成功。

8. **必须显式定义分层验收策略**
   - 本 PRD 的 correctness 必须分为：
     - 本地 workflow contract/static validation
     - 本地语义级验证
     - 真实 GitHub witness 验证
   - 不得把 live GitHub run 作为每轮 coder loop 的唯一主验证手段。

9. **必须把 Phase 2 的“有信息量失败”定义清楚**
   - Phase 2 允许 truthful failure；
   - 但 CI 首轮失败不应主要由“缺基础依赖、完全没有 dependency contract、明显 root-only path 爆炸”构成；
   - 这些前置噪音必须至少收敛到让 GitHub run 能进入对仓库真实 preflight/test surface 有信息量的失败面。

### Non-Functional Requirements

1. **执行语义必须真实**
   - GitHub CI 的核心 gate 必须与开发者本地使用的 `preflight.sh` 保持一致。

2. **观测语义必须真实**
   - `bash preflight.sh` 成功 → CI job 成功；
   - `bash preflight.sh` 失败 → CI job 失败；
   - 禁止隐藏真实失败。

3. **第一版必须最小化 blast radius**
   - 优先新增 workflow、最小依赖 contract、最小 supporting tests；
   - 不在此 PR 中混入大量 true-green 修复。

4. **Phase 2 可以接受 truthful red，但不能接受 fake green**
   - 本阶段的价值是建立 observability surface，而不是美化状态灯。

### User Stories

- **As an AMS maintainer**, I want GitHub Actions to execute the real `preflight.sh` on clean runners so I can see failures my local machine may hide.
- **As an architect**, I want Phase 2 correctness to be defined in terms of truthful workflow behavior and observability, not fake greenness.
- **As a reviewer**, I want most correctness evidence to come from repo-local contract tests rather than from slow live GitHub-only validation.
- **As an operator**, I want the CI signal to avoid low-value dependency-noise red and surface failures that are actually useful for subsequent backlog formation.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用 **workflow-contract-first + validated dependency baseline + layered acceptance** 策略。

### 3.1 核心设计原则

1. **GitHub Actions 是 execution surface，不是业务逻辑容器**
   - workflow 负责触发、runner 初始化、最小 bootstrap、调用真实 gate；
   - `preflight.sh` 仍是 AMS 仓库级统一 gate 的权威入口。

2. **soft gate ≠ fake green**
   - “soft” 指 merge policy 尚未将该 workflow 设为 required blocker；
   - 不允许用 `continue-on-error`、吞错、伪成功、假日志来包装红灯。

3. **先立 dependency contract，再看 preflight 真实问题**
   - 本 PRD 不要求一次性完成 AMS 全依赖治理；
   - 但必须至少明确 `preflight.sh` 的最小依赖面，否则 GitHub CI 只会产生低价值报警。

4. **大部分 correctness 必须本地可重复验证**
   - workflow contract 的主验证层必须是 repo 内本地自动化测试；
   - GitHub run 是低频 witness，不是高频主测试。

5. **CI 不得分叉出第二套 gate**
   - CI 必须运行 `bash preflight.sh`；
   - 不得把 preflight 拆成一组“差不多”的命令替代真实入口。

### 3.2 与现有 AMS 治理资产的关系

本 PRD 与以下现有 AMS 治理资产存在明确衔接关系：

- `#1` / 非 root path portability：
  - 目标不是要求该 issue 在本 PRD 内完全关闭；
  - 而是要求 path 问题至少收敛到不让 CI 首轮只产生无意义爆炸。

- `#2` / preflight dependency contract：
  - 这是本 PRD 的明确前置；
  - 该前置当前已经有仓库内已验证基线：`requirements-test.txt`；
  - issue 记录已经说明这套分层 requirements 在 clean environment 中成功跑通 `bash preflight.sh`；
  - 因此，本 PRD 的 workflow bootstrap 应直接依赖这份已验证基线，而不是重新发明新的未验证 contract。

- `PRD_Config-Driven_Preflight_Ignore_List_for_Debt_Quarantine.md`：
  - 该机制允许 AMS 在存在已知债务时恢复可控 gate surface；
  - GitHub CI 应当运行的是当前仓库真实 preflight 语义，包括其已审计的 quarantine contract，而不是绕过它。

- `PRD_Fix_CI_Preflight_Script_Auto_Discovery.md`：
  - 该 PRD 解决的是 preflight 内部 test surface discovery 正确性；
  - 本 PRD 解决的是把真实 gate 暴露到 GitHub Actions 上，二者互补但不混写。

### 3.3 目标文件与修改范围

本 PRD 允许修改：

- `AMS/.github/workflows/preflight.yml`（新增）
- 与 preflight 最小依赖 contract 直接相关的依赖文件（新增或修改）
- 为 workflow contract / semantics 服务的最小本地测试文件（新增或修改）
- 如必要，用于最小 runner bootstrap 的 supporting 文件（新增或修改）

本 PRD 不授权：

- 把大量 true-green 修复混进同一个 PR
- 直接配置 GitHub required status checks / branch protection
- 重写 AMS 全部依赖体系
- 将部署、Windows 节点同步、agent heartbeat 调度等议题混入本需求

### 3.4 Workflow 合同

第一版 workflow 必须满足以下 contract：

1. 文件位于：
   - `.github/workflows/preflight.yml`

2. 触发条件至少包括：
   - `push`
   - `pull_request`

3. workflow 必须包含以下固定职责步骤，且顺序语义清晰可辨：
   - checkout repository
   - setup Python runtime
   - install `requirements-test.txt`
   - run `bash preflight.sh`

4. 关于 minimal preflight dependency bootstrap 的约束：
   - 其目的仅限于让 clean GitHub runner 具备运行当前仓库 `preflight.sh` 的最小依赖；
   - 它必须安装仓库内当前已验证的 preflight/test dependency baseline：
     - `requirements-test.txt`
   - 它不得偷偷把 true-green 修复塞进 bootstrap 逻辑；
   - 它不得通过条件跳过或环境短路改变 `preflight.sh` 作为统一 gate 的语义。

5. workflow 不得：
   - 把 preflight 拆成另一套独立命令链并替代真实入口；
   - 使用 `continue-on-error` 掩盖 preflight 真实失败；
   - 通过硬编码 success path、空命令、伪造日志或条件跳过把 soft gate 伪装成绿灯；
   - 把“soft gate”实现成“总是成功但附带说明”的假 gate。

6. workflow 的成功/失败语义必须与 `preflight.sh` 一致：
   - `bash preflight.sh` exit 0 → CI job success
   - `bash preflight.sh` non-zero exit → CI job failure

### 3.5 Dependency Contract Strategy

AMS 的分层 requirements baseline 已经存在，并且 issue #2 记录了 clean-environment witness：安装 test baseline 后，`bash preflight.sh` 成功跑通。

当前仓库内已存在：

- `requirements.txt`
- `requirements-test.txt`
- `requirements-providers.txt`
- `requirements-bridge.txt`

其中，本 PRD 对 GitHub preflight workflow 的明确要求是：

1. **workflow bootstrap 必须安装 `requirements-test.txt`**
   - 这是当前 AMS 仓库中已验证、可复现、足以运行 `preflight.sh` 的 baseline contract；
   - Phase 2 不再把依赖文件名留作开放问题。

2. **`requirements-test.txt` 在本 PRD 中的角色是“当前有效基线”，不是“长期最优终局”**
   - 该文件当前仍然偏胖，因为现有 pytest/preflight collection 会拉入 provider / bridge 邻近依赖；
   - 这是一个后续可优化问题，但不再是 GitHub CI bootstrap blocker。

3. **workflow 不得绕开 `requirements-test.txt` 自行拼装另一套隐式安装清单**
   - 不允许在 workflow 中手写一串散装 `pip install xxx yyy zzz` 来替代仓库内 dependency contract；
   - 这样会制造“repo contract”和“CI contract”的双轨漂移。

4. **本 PRD 不要求立即完成 AMS 的最终依赖分层设计**
   - `requirements-providers.txt` / `requirements-bridge.txt` 的进一步瘦身与职责重整，可以在后续 issue 中继续推进；
   - 但 Phase 2 当前必须以 `requirements-test.txt` 作为确定性 bootstrap 基线。

5. **本 PRD 的依赖 contract 成功标准已经从“待定义”升级为“已验证可用”**
   - 目标不再是抽象讨论最小依赖应该是什么；
   - 目标是让 GitHub runner 复用现有已验证 baseline，真实运行 `preflight.sh`。

### 3.6 分层验收定义（本 PRD 的关键 correctness contract）

#### Layer A — Local Static / Contract Validation
这是主验证层，必须稳定、快速、可重复，不依赖 live GitHub。

验证内容包括：

- workflow 文件存在；
- workflow YAML 结构满足约定；
- `push` / `pull_request` 触发器存在；
- preflight job 存在；
- 核心执行命令是 `bash preflight.sh`；
- workflow 未使用 `continue-on-error` 掩盖真实失败；
- workflow 包含 required runtime/bootstrap steps；
- workflow 使用明确的 preflight dependency bootstrap，而不是隐式环境假设。

落地约束：

- 这一层必须通过仓库内本地自动化测试落地；
- 推荐以 Python/pytest contract tests 读取并断言 `.github/workflows/preflight.yml` 的结构与关键字段；
- 可补充少量 supporting shell assertions，但不得替代结构级 contract tests。

#### Layer B — Local Behavior / Semantics Validation
这一层验证 workflow 语义，而不依赖真实 GitHub runner。

验证内容包括：

- workflow 的目标确实是仓库真实 gate；
- preflight 成败如何映射到 CI job 成败；
- bootstrap 未改变 `preflight.sh` 的统一入口语义；
- workflow 没有变成第二套独立 gate。

#### Layer C — External GitHub Witness
这是低频真实见证层。

验证内容包括：

- workflow pushed to GitHub 后，GitHub Actions 产生真实 run；
- 该 run 进入可见终态（success / failure）；
- 该结果可在 GitHub UI / API 被观察到。

约束：

- 这一层是 witness，不是每轮 coder-loop 的唯一 gate；
- 不得把整个 PRD 的 correctness 仅定义成“live GitHub 必须每次都跑”；
- 这层允许较慢、具外部依赖，但必须低频使用。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Preflight workflow file exists in the repository**
  - **Given** the AMS Phase 2 implementation branch
  - **When** the repository tree is inspected
  - **Then** a workflow file exists at `.github/workflows/preflight.yml`

- **Scenario 2: Workflow auto-triggers on push and pull request**
  - **Given** the committed preflight workflow
  - **When** the workflow definition is inspected as data
  - **Then** it declares `push` and `pull_request` triggers

- **Scenario 3: Workflow executes the real AMS preflight gate**
  - **Given** the committed preflight workflow
  - **When** the workflow job definition is inspected
  - **Then** the workflow invokes `bash preflight.sh`
  - **And** it does not replace the repository preflight gate with a fake equivalent command chain

- **Scenario 4: Workflow installs the validated preflight dependency contract before gate execution**
  - **Given** the committed preflight workflow and its supporting dependency contract
  - **When** the bootstrap step is inspected
  - **Then** it installs `requirements-test.txt`
  - **And** it does not rely on undeclared machine-local packages
  - **And** it does not replace the repository dependency contract with an ad-hoc inline package list

- **Scenario 5: Soft gate preserves truthful failure semantics**
  - **Given** the committed preflight workflow
  - **When** the workflow job definition is inspected
  - **Then** it does not use `continue-on-error` or equivalent masking to convert a real preflight failure into a successful CI job

- **Scenario 6: Workflow contract is locally testable without live GitHub dependency**
  - **Given** the workflow file and supporting local tests
  - **When** local automated tests are executed
  - **Then** the workflow contract and execution semantics can be verified without requiring a live GitHub Actions run

- **Scenario 7: Real GitHub witness produces a visible workflow run**
  - **Given** the workflow has been pushed to GitHub
  - **When** a qualifying push or pull request event occurs
  - **Then** GitHub Actions creates a visible `Preflight` workflow run
  - **And** the run reaches a visible terminal result that can be inspected by humans

- **Scenario 8: Truthful CI red is acceptable in Phase 2 when it is informative**
  - **Given** a repository state where AMS still has remaining preflight debt on a clean runner
  - **When** the GitHub workflow runs
  - **Then** the workflow may fail
  - **And** that failure is treated as a valid observability signal rather than a Phase 2 design failure
  - **And** the failure should not primarily be caused by an undefined preflight dependency contract

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
本阶段最大的风险不是“GitHub CI 一开始会红”，而是：

1. 把 soft gate 做成 fake green；
2. 把 correctness 全压到 live GitHub witness，导致主循环 slow / flaky；
3. workflow 看起来存在，但没有真实执行 AMS 仓库级 preflight；
4. CI 首轮主要在报 dependency contract 缺失，而不是暴露仓库真实 preflight surface；
5. GitHub CI 与本地 `preflight.sh` 语义漂移，形成第二套 gate。

### Verification Strategy

#### A. Primary Automated Verification (must be local, stable, repeatable)
使用本地自动化测试验证：

- workflow 文件存在与路径正确；
- YAML / contract shape 正确；
- `push` / `pull_request` 触发器存在；
- 核心命令为 `bash preflight.sh`；
- 未使用 masking 语义掩盖失败；
- required runtime/bootstrap steps 存在；
- workflow 所依赖的 preflight dependency bootstrap 指向仓库内已验证的 `requirements-test.txt` baseline。

这部分必须作为 coder + preflight + reviewer 主循环的核心证据。

推荐落地方式：

- 新增最小 pytest contract tests，对 `.github/workflows/preflight.yml` 做结构级断言；
- 如有需要，对 dependency bootstrap 所引用的依赖文件存在性和可引用性做最小静态验证；
- 允许补充少量 black-box/supporting tests，但不得把主验证职责转移给 live GitHub API 或人工 UI 检查。

#### B. Secondary Behavioral Verification
验证 workflow 设计语义：

- `preflight.sh` success/failure 如何映射到 CI job success/failure；
- soft gate 定义在 merge policy 而非“伪造成功”；
- workflow 没有偷偷变成另一套独立 gate；
- dependency bootstrap 没有越权演化成“在 CI 里偷偷修仓库问题”。

#### C. External Witness Verification
低频执行真实 GitHub witness：

- push / PR 触发真实 workflow run；
- GitHub UI 可见 run；
- run 结果可观察。

这一层只做 witness，不做高频主验证。

### Mocking / Dependency Policy
- workflow contract tests 不应依赖 live GitHub API；
- 对 GitHub 本体的真实依赖只保留在 witness 层；
- 如需解析 workflow 文件，应优先做静态/结构级断言，而非 live execution；
- 本 PRD 不鼓励通过大量 mocking 伪装 GitHub runner 已经“相当于跑过 CI”；主价值仍然是 contract correctness + 真实 witness 分层。

### Quality Goal
本 PRD 的质量目标不是“让 AMS preflight 立刻 true green”，而是：

> **把 GitHub Actions 建成一个真实执行 `bash preflight.sh`、结果传播准确、对 clean runner 问题可观察、且其大部分正确性可由本地稳定 contract tests 验证的 soft-gate CI surface；同时避免让 CI 首轮主要沦为 dependency contract 缺失报警器。**

## 6. Framework Modifications (框架防篡改声明)
- `AMS/.github/workflows/preflight.yml`（新增）
- 与 preflight 最小依赖 contract 直接相关的依赖文件（新增或修改）
- 为 workflow contract / CI semantics 服务的最小测试文件（新增或修改）
- 如必要，用于最小 runner bootstrap 的 supporting 文件（新增或修改）

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 直接把“给 AMS 接上 GitHub Actions preflight workflow”当成 Phase 2 完成条件，隐含接受 CI 首轮大量 dependency noise。
- **Audit Rejection (v1.0)**: 这种写法会让 Phase 2 的 correctness 退化成“workflow 存在且跑起来”，却无法区分 truthful observability 与低价值环境噪音，也容易把 soft gate 做成 fake green 或空心 gate。
- **v2.0 Revision Rationale**: 改为 workflow-contract-first + validated dependency baseline + layered acceptance。直接复用 issue #2 中已完成 clean-environment 验证的 `requirements-test.txt` 作为 GitHub CI bootstrap 基线，再让 GitHub Actions 真实执行 `bash preflight.sh`，把大部分 correctness 收敛到本地稳定 contract tests，同时保留低频 GitHub witness 作为真实接线见证。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`workflow_relative_path`**:
```text
.github/workflows/preflight.yml
```

- **`workflow_gate_command`**:
```text
bash preflight.sh
```

- **`workflow_required_triggers`**:
```text
push
pull_request
```

- **`workflow_required_minimal_steps`**:
```text
checkout repository
setup Python runtime
install requirements-test.txt
run bash preflight.sh
```

- **`workflow_success_failure_mapping`**:
```text
bash preflight.sh exit 0 -> CI job success
bash preflight.sh non-zero exit -> CI job failure
```

- **`soft_gate_semantics_statement`**:
```text
Phase 2 soft gate means the GitHub Actions result is visible and truthful, but not yet configured as a required merge blocker.
```

- **`masking_prohibition_statement`**:
```text
Do not use continue-on-error or any equivalent masking mechanism to convert a real preflight failure into a successful CI result.
```

- **`local_contract_test_expectation`**:
```text
The primary correctness checks for this phase must be implemented as repository-local automated contract tests against .github/workflows/preflight.yml rather than as live GitHub-only verification.
```

- **`dependency_contract_statement`**:
```text
Before the workflow executes bash preflight.sh on a clean runner, it must install requirements-test.txt as the current repository-validated dependency baseline for the AMS preflight gate.
```

- **`workflow_dependency_install_command`**:
```text
pip install -r requirements-test.txt
```
