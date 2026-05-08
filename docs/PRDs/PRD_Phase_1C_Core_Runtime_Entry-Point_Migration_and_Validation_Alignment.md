---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Phase 1C Core Runtime Entry-Point Migration and Validation Alignment

## 1. Context & Problem (业务背景与核心痛点)
AMS 的 path-contract work 已完成前两个阶段：
- Phase 1A：定义 path vocabulary、resolution precedence、deployment relation 与禁止的 host-layout assumptions
- Phase 1B：建立 centralized path resolver helper layer，编码 `CLI > ENV > AMS-owned config > project-local default` precedence，补上 fail-fast 与 anti-regression guard，并完成代表性入口接线

截至当前，AMS 已具备统一路径 contract 的机制层基础，GitHub Preflight 也已经重新回到绿色状态，说明 helper layer 本身与首批 contract-focused tests 已经成立。

但 Issue #1 作为 root-cause ticket 仍未完全关闭，原因也很明确：
- 仍有核心 runtime entry points、validators、ETL 路径入口和部分 validation / fixture / golden surface 尚未全面迁到新的 contract
- repo 中仍可找到 legacy `/root/projects/AMS/...`、`/root/.openclaw/...`、`.openclaw/workspace/...` 假设残留
- 当前绿色 CI 主要证明“机制层已经成立”，还不能证明“所有关键入口都已经被 contract 接管”

换句话说，Phase 1B 解决的是“规则已变成公共机制”，而 Phase 1C 要解决的是“系统真正开始按这套机制运行”。

因此，Phase 1C 的核心任务不是再设计 contract，而是以 Phase 1A/1B 为上游基线，把核心运行入口、验证入口和关键遗留路径逐步迁到统一 resolver contract 上，并让 validation / smoke / golden checks 以产品 contract 为准，而不是继续受宿主布局历史包袱影响。

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements
1. 必须将关键 core runtime entry points 迁移到 Phase 1B 已建立的 path resolver contract 上，不得继续在这些入口中保留独立 ad hoc 路径规则。
2. 必须迁移以下高优先级系统区域：
   - `main_runner.py` 及其相关数据路径入口
   - provider/config path entry points
   - validator 路径入口
   - ETL output / input / report / cache 默认路径入口
   - validation / smoke / golden / path-consistency 检查的路径假设
3. 对 repo-owned stable assets，必须统一使用 repo-relative / package-owned 语义；不得继续把 fixture、golden、baseline metadata 或 repo 文档资产锚定到 `/root/...` 或其他宿主绝对路径。
4. 对 mutable research/backtest data，必须统一通过 Phase 1B resolver 解析；不得在入口层重新实现 precedence 或保留 root-bound 默认值。
5. 对 runtime outputs/state，必须统一通过 Phase 1B resolver 解析；不得要求 `.openclaw/workspace/...` 存在才能完成核心运行、报告生成或缓存写入。
6. 必须处理仍残留在关键入口与关键测试中的 `/root/projects/AMS/...`、`/root/.openclaw/...`、`.openclaw/workspace/...` 假设，使其迁移、替换或被 contract-aware fixture/setup 吸收。
7. 必须让 validation / smoke / golden / path-consistency 检查验证的是 path contract 本身，而不是特定宿主布局是否存在。
8. 必须保留并扩展 anti-regression guard，确保新的入口迁移完成后，root-only 假设不会通过其他模块回流。

### 2.2 Non-Functional Requirements
1. Phase 1C 迁移后的 AMS 必须在 clean non-root 环境中通过关键验证流程。
2. 新路径行为必须可审计：reviewer 能从入口行为与测试结果判断路径来自 repo contract、resolver precedence 或 runtime output contract，而不是隐式布局运气。
3. 迁移应优先收敛关键路径入口，不得借机扩散为无边界的 I/O 大改造。
4. 迁移必须遵守 Phase 1A/1B 已锁定的 vocabulary、precedence 和禁止假设，Phase 1C 不得重新解释或改写这些 contract。

### 2.3 Scope Boundaries
Phase 1C 负责：
- core runtime entry-point migration
- validation / smoke / golden / path-consistency alignment
- 关键 legacy path 假设清理
- 在 clean non-root 环境中证明 contract 已被核心入口消费

Phase 1C 不负责：
- 重写 AMS 整体 I/O 架构
- 扩展到与 path contract 无关的产品功能开发
- 解决所有历史技术债
- 进入后续更高阶段的部署拓扑、CI/CD 增强或数据域治理新议题

### 2.4 User Stories
- 作为 AMS 运行者，我希望主运行入口和 ETL / validator / report 路径都遵守同一套 contract，这样系统不会因为换一台机器或换成 non-root runner 就失效。
- 作为 CI / witness 环境维护者，我希望 validation / smoke / golden 检查只在真实 contract 漂移时失败，而不是继续因为 `/root/...` 布局不存在而误报。
- 作为后续维护者，我希望关键入口都已接入统一 resolver，这样新增能力时不必再在入口里复制一套路径常识。
- 作为架构审阅者，我希望能明确看出哪些遗留 root-path 假设已经被真正迁移掉，哪些只是被测试掩盖。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Core Design Decision
Phase 1C 明确承接既有分层：
- Phase 1A：Vocabulary + Contract Definition
- Phase 1B：Centralized Helper Layer + Resolution Order Encoding
- Phase 1C：Core Runtime Entry-Point Migration + Validation Alignment

因此本阶段的首要原则是：
*不再重新设计 contract，而是要求关键运行入口全面消费既有 contract。*

### 3.2 Migration Principle
每一个被纳入 1C 的入口，都必须从“入口自己决定路径规则”迁移到“入口调用统一 resolver 并服从 path class semantics”。

Phase 1C 不允许出现以下伪迁移：
- 入口只是换了个函数名，但内部仍保留本地 precedence 分支
- 用 wrapper 或兼容层继续默认指向 `/root/projects/AMS/...`
- validation 表面改绿，但仍在以宿主绝对路径存在性作为判断依据
- runtime outputs 通过偶然可写目录成功，而不是通过 AMS contract 成功

### 3.3 Entry-Point Migration Matrix
Phase 1C 不按“所有入口一起迁”执行，而按明确的入口矩阵分批 cutover。每个入口必须定义：
- 当前耦合问题
- 目标 resolver API / contract
- 预期外部行为
- 负向守卫
- 回滚落点

本阶段授权的入口矩阵如下：

#### Wave 1 — Main Runtime + Provider Config
1. **`main_runner.py`**
   - 当前耦合问题：仍保留入口层数据路径推断与默认值拼接风险
   - 目标 contract：
     - mutable research/backtest data → `resolve_mutable_data_path(...)`
     - runtime outputs/state → `resolve_runtime_output_path(...)`
   - 预期外部行为：
     - 在不同 cwd、non-root runner、无 `.openclaw/workspace` 条件下，主运行入口仍能稳定解析输入/输出路径
   - 负向守卫：
     - 若重新依赖 `/root/projects/AMS/...` 或 cwd，则 smoke / integration tests 失败
   - 回滚落点：
     - 仅回滚 `main_runner.py` 的 resolver 接线，不回滚 resolver contract 本身

2. **`ams/utils/provider_config.py` 及其直接消费面**
   - 当前耦合问题：已部分接入 resolver，但仍需要完成对 provider dataset / metrics path 的统一接管
   - 目标 contract：
     - provider dataset / metrics path 统一经 resolver 与 project-local default 语义得到
   - 预期外部行为：
     - provider config 在 clean non-root 环境与不同 cwd 下解析结果稳定一致
   - 负向守卫：
     - 若 provider config 回退到 root-bound 默认路径，contract tests 失败
   - 回滚落点：
     - 限定在 provider config entry wiring

#### Wave 2 — Validator + ETL Entrypoints
3. **`ams/validators/cb_data_validator.py` 等 validator 路径入口**
   - 当前耦合问题：仍存在 legacy absolute default（如 baseline / metrics 路径）
   - 目标 contract：
     - repo-owned stable assets → repo-relative
     - mutable data / metrics inputs → resolver-controlled
   - 预期外部行为：
     - validator 在 clean non-root 环境中可读取所需 baseline / metrics，而不依赖 `/root/...`
   - 负向守卫：
     - 若 validator 默认路径仍指向 `/root/projects/AMS/...`，validator integration tests 失败
   - 回滚落点：
     - 仅回滚 validator path defaults，不回滚 Phase 1B precedence behavior

4. **`etl/jqdata_sync_cb.py` 及同类 ETL 路径入口**
   - 当前耦合问题：root-bound dataset / metrics 常量仍残留
   - 目标 contract：
     - ETL 输入输出路径统一通过 resolver 获取
   - 预期外部行为：
     - ETL 在 clean non-root 环境中可读写 contract 允许的位置
   - 负向守卫：
     - 若 ETL 仍依赖 `/root/projects/AMS/...` 或 `.openclaw/workspace/...`，ETL path tests / smoke 失败
   - 回滚落点：
     - 限定在 ETL entry wiring 与默认路径常量替换

#### Wave 3 — Validation / Fixture / Golden Alignment
5. **Fixture / smoke / order semantics / execution semantics tests**
   - 当前耦合问题：仍存在 `/root/projects/AMS/tests/fixtures/...` 绝对路径引用
   - 目标 contract：
     - fixtures 统一作为 repo-owned stable assets，以 repo-relative 解析
   - 预期外部行为：
     - 同一测试在不同宿主布局下行为一致
   - 负向守卫：
     - 若 fixture resolution 回退到 host absolute path，相关测试失败
   - 回滚落点：
     - 仅回滚对应 test setup / fixture setup 改动

6. **golden metadata / validation / path-consistency surface**
   - 当前耦合问题：golden metadata 仍可能残留 host-layout lineage 文本；验证面仍可能把机器布局当成功前提
   - 目标 contract：
     - golden / metadata / validation 仅验证产品 contract
   - 预期外部行为：
     - clean witness / CI 环境下，验证失败只由 contract drift 触发
   - 负向守卫：
     - 若验证逻辑重新依赖 `/root/...` 或 `.openclaw/workspace/...`，validation guard 失败
   - 回滚落点：
     - 限定在 metadata baseline / validation assertions 变更

### 3.4 Cutover Sequencing
Phase 1C 必须按 wave 顺序实施，不允许无序并行大迁移。

1. **Wave 1 完成条件**
   - `main_runner.py` 与 provider config entry points 完成 resolver cutover
   - 对应 contract-aware integration tests 与 smoke tests 通过
   - clean non-root witness flow 可稳定通过主运行入口验证

2. **Wave 2 启动前提**
   - Wave 1 已绿
   - validator / ETL 的现状耦合点已映射到入口矩阵中
   - 不允许在 Wave 1 未稳住前同时大规模改 ETL 与 validator

3. **Wave 2 完成条件**
   - validator 与授权 ETL 入口不再依赖 root-bound 默认路径
   - validator / ETL contract-aware integration tests 通过
   - clean non-root witness flow 增补 validator / ETL 覆盖后仍保持通过

4. **Wave 3 启动前提**
   - Wave 1 / 2 已绿
   - fixture / golden / metadata / validation surface 的迁移对象已列出清单

5. **Wave 3 完成条件**
   - fixtures / golden / metadata / validation surface 全部对齐 path contract
   - witness / preflight / smoke / validation 在 clean non-root 环境中稳定通过
   - host-layout anti-regression guards 保持有效

### 3.5 Fixed Clean Non-Root Witness Flow
Phase 1C 必须定义固定 witness flow，作为完成证明的一部分。至少包括：
1. clean checkout
2. non-root user environment
3. 不预置 `/root/projects/AMS/...`
4. 不预置 `.openclaw/workspace/...`
5. 运行：
   - representative main runtime smoke
   - provider / validator / ETL contract-aware checks（按当前 wave 覆盖）
   - `bash preflight.sh --report-all`

若实现者不能在该固定 witness flow 下提供通过证据，则不得宣称对应 wave 完成。

### 3.6 Rollback Strategy
本阶段必须按 wave 提供 bounded rollback，而不是“全盘回退”。

- **Wave 1 rollback**：
  - 若 `main_runner` / provider config cutover 导致主运行入口失稳，仅回退对应入口接线改动，保留 resolver helper layer 与 precedence tests
- **Wave 2 rollback**：
  - 若 validator / ETL cutover 导致关键验证或 ETL 失稳，仅回退对应 validator / ETL entry wiring 与默认路径替换，保留已稳定的 Wave 1
- **Wave 3 rollback**：
  - 若 validation / metadata / fixture alignment 引入伪绿或破坏 golden 语义，仅回退相应 validation surface / metadata baseline 改动，不回退已经稳定的 runtime entry migration

回滚原则：
- 不回滚 Phase 1A/1B 的 contract 定义与 resolver 机制
- 仅回滚当前 wave 的入口接线或 validation alignment 改动
- 回滚后必须仍能通过上一稳定 wave 的 witness flow

### 3.7 Treatment by Path Class

#### Repo-Owned Stable Assets
Phase 1C 中属于 repo-owned stable assets 的对象必须：
- 使用 repo-relative / package-owned resolution
- 不得继续硬编码 `/root/projects/AMS/tests/...`
- 不得因 OpenClaw skill 布局、Windows 部署目录或调用 cwd 变化而改变语义

#### Mutable Research/Backtest Data
Phase 1C 中此类路径必须：
- 统一走 `resolve_mutable_data_path(...)` 或等效 contract-aware resolver
- 继续遵守 `CLI > ENV > AMS-owned config > project-local default`
- 不允许入口层重新实现一套 precedence

#### Runtime Outputs/State
Phase 1C 中此类路径必须：
- 统一走 `resolve_runtime_output_path(...)` 或等效 contract-aware resolver
- 支持显式 override
- 默认 runtime 行为必须可在 non-root 环境写入
- 不得对 `.openclaw/workspace/...` 形成运行依赖

### 3.8 Validation Alignment Strategy
Phase 1C 的 validation alignment 不是“把所有测试改到能过为止”，而是：
- 把测试断言锚到 path contract
- 把 fixture setup 锚到 repo-owned asset 规则
- 把 smoke / path-consistency / golden checks 锚到 resolver 行为
- 把宿主布局检测保留为 anti-regression negative check，而不是 success precondition

### 3.9 Legacy Residue Handling
当前 repo 中仍存在一些 root-only residue，包括但不限于：
- validator 默认路径
- ETL 模块中的 root-bound dataset / metrics 常量
- fixture / e2e / order semantics / execution semantics 测试中的绝对路径引用
- golden metadata 中残留的 host-layout lineage 文本

Phase 1C 必须把这些 residue 分为以下处理方式：
1. 直接迁移到 contract-aware resolver
2. 直接改为 repo-relative fixture resolution
3. 更新为 contract-aware metadata/golden 基线
4. 若确实保留兼容层，也必须显式标注其为兼容逻辑而非默认 contract

### 3.10 Trade-off
Phase 1C 会扩大影响面，因为它开始触达真正运行系统与验证表面，而不再局限于 helper 层。

接受该代价的原因是：
- 如果停留在 1B，AMS 只是在“有一套 resolver”，但未必“真的按 resolver 运行”
- Issue #1 的 root cause 只有在关键入口迁移完成后，才可称为被实质解决
- validation alignment 若不做，CI 绿色仍可能只是局部信号，而不是系统性 contract 绿灯

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Main runtime behavior is stable across non-root environments after Wave 1 cutover**
  - **Given** `main_runner.py` 已完成本阶段授权的 cutover，且调用方在不同 cwd、non-root 环境中运行同一主流程
  - **When** 运行方不提供 root-only 布局且不提供 `.openclaw/workspace/...`
  - **Then** 主流程必须仍能稳定找到所需输入并生成 contract 允许的输出，且运行结果不因 cwd 或宿主布局变化而失效

- **Scenario 2: Provider configuration resolves datasets and metrics deterministically**
  - **Given** provider dataset / metrics path 同时存在 CLI、ENV、config 与 project-local default 候选来源
  - **When** AMS 在 clean non-root 环境中加载 provider configuration
  - **Then** 最终行为必须稳定符合已定义 precedence，且不要求 `/root/projects/AMS/...` 存在

- **Scenario 3: Validators run successfully without root-only defaults**
  - **Given** validator 需要读取 baseline、dataset 或 metrics 路径
  - **When** 在 clean non-root witness flow 中执行 validator 相关验证
  - **Then** 验证流程必须能够成功完成或给出与输入数据相关的真实失败，而不能因为默认路径指向 `/root/...` 而失败

- **Scenario 4: ETL flows read and write through contract-allowed locations**
  - **Given** ETL 需要读取输入数据并写出 metrics、reports 或其他运行输出
  - **When** 在 clean non-root 环境中执行授权范围内的 ETL smoke / integration flow
  - **Then** ETL 必须能够在 contract 允许的位置完成读写，而不依赖 `/root/projects/AMS/...` 或 `.openclaw/workspace/...`

- **Scenario 5: Repo-owned fixtures and golden assets remain portable**
  - **Given** 测试或运行流程需要访问 fixtures、golden snapshots 或 baseline metadata
  - **When** 这些流程在不同宿主布局或不同 cwd 下运行
  - **Then** 它们必须保持一致行为，并且不会因为缺失宿主绝对路径而失败

- **Scenario 6: Validation and smoke checks fail only on contract drift**
  - **Given** validation / smoke / path-consistency / golden checks 在 CI 或 clean witness 环境中运行
  - **When** path contract 保持成立
  - **Then** 这些检查必须通过；若失败，其原因必须对应真实 contract drift，而不是宿主布局差异

- **Scenario 7: Reintroduced host-layout coupling is externally detectable**
  - **Given** 后续有人重新把 `/root/projects/AMS/...`、`/root/.openclaw/...` 或 `.openclaw/workspace/...` 作为运行前提带回系统
  - **When** preflight、smoke、validation 或 contract guard 在 clean non-root witness flow 中运行
  - **Then** 自动化验证必须失败并暴露该耦合，而不是继续给出伪绿色信号

- **Scenario 8: Wave rollback preserves the previous stable witness result**
  - **Given** 某个 migration wave 的 cutover 导致核心入口或验证面失稳
  - **When** 系统按本 PRD 定义的 wave rollback 方案回退该 wave 改动
  - **Then** 上一个稳定 wave 的 witness flow 必须能够重新通过，且无需回滚整个 path resolver contract

- **Scenario 9: Phase 1C completion is proven by the fixed witness flow**
  - **Given** 实现者宣称 Phase 1C 已完成
  - **When** reviewer 运行本 PRD 规定的 fixed clean non-root witness flow
  - **Then** 该 flow 必须在授权范围内稳定通过，并证明 main runtime、provider、validator、ETL、fixture/golden/validation surface 已按 contract 运行

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 Core Quality Risk
Phase 1C 最大风险不是改动面大，而是出现以下“伪完成”：
- helper 存在，但关键入口没真正接上
- 测试改绿了，但只是把 root-only 路径换成另一种隐式路径
- validation 不再报 `/root/...`，却仍未验证 precedence / path class contract
- ETL / validator / smoke / fixture 各自保留一套局部路径逻辑
- CI 绿色只是因为当前 runner 碰巧满足若干未显性的布局前提

### 5.2 Verification Philosophy
Phase 1C 的完成证明不能依赖白盒“看代码像是接上了 resolver”，而必须依赖固定 witness flow 下的外部行为证据。

因此验证必须回答四个黑盒问题：
1. 在 clean non-root 环境中，主运行入口是否还能稳定工作？
2. provider / validator / ETL 是否还能在 contract 允许的位置完成读写与验证？
3. fixtures / golden / validation surface 是否已经摆脱 host-layout 依赖？
4. 若 root-only coupling 回潮，fixed witness flow 与 anti-regression guards 是否会稳定打红？

### 5.3 Recommended Test Structure
1. **Wave-specific black-box integration tests**
   - Wave 1：主运行入口 + provider config
   - Wave 2：validator + 授权 ETL 入口
   - Wave 3：fixture / golden / metadata / validation surface
   - 每个 wave 都必须有对应的外部行为验证，而不是仅用内部实现断言收尾

2. **Fixed clean non-root witness flow**
   - 作为所有 wave 的统一完成证据
   - witness flow 必须固定且可重复执行

3. **Fixture / golden / metadata portability checks**
   - 验证 repo-owned stable assets 在不同 cwd / 宿主布局下仍保持一致行为
   - 验证 metadata / golden 不再把旧 host layout 当作 contract

4. **Negative / anti-regression checks**
   - 一旦重新引入 `/root/projects/AMS/...`、`/root/.openclaw/...` 或 `.openclaw/workspace/...` 作为运行前提，验证必须打红

### 5.4 Mocking / Environment Control Guidance
需要 mock 或显式控制的输入包括：
- CLI overrides
- environment variables
- AMS-owned config inputs
- temporary output directories
- fixture-controlled dataset / metrics / report locations

不应依赖：
- root-only host layout
- OpenClaw workspace 作为成功前提
- 当前工作目录碰巧正确
- 历史 golden metadata 中偶然残留的旧路径文本

### 5.5 Exit Criteria
只有在以下证据全部成立时，才可宣称 Phase 1C 完成：
1. Wave 1、Wave 2、Wave 3 已按本 PRD 的 sequencing 完成，且每个 wave 都有对应的固定外部行为验证通过。
2. fixed clean non-root witness flow 在最终状态下稳定通过。
3. main runtime / provider / validator / ETL / fixture / golden / validation surface 的授权范围内对象，均已在外部行为层面证明不再依赖 `/root/...` 或 `.openclaw/workspace/...`。
4. 若重新引入 host-layout coupling，negative / anti-regression 验证会稳定失败。
5. 若某个 wave 出现失稳，bounded rollback 能恢复到上一稳定 wave 的 witness flow 通过状态。

### 5.6 Quality Goal
本阶段最终质量目标是：
- AMS 的关键运行入口真正服从统一 path contract
- validation / smoke / golden 信号只在真实 contract 漂移时失败
- non-root / clean runner 成为一等运行与验证环境
- Issue #1 从“有统一设计 + helper”推进到“核心系统已按该设计运行”的实质完成状态

## 6. Framework Modifications (框架防篡改声明)
- None

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial Phase 1C draft created after confirming Phase 1B landing on `master`. This version frames 1C as the migration of core runtime entry points and validation surfaces onto the already-approved resolver contract, with explicit focus on eliminating remaining root-only path assumptions from key runtime and validation flows.
- **Audit Rejection (v1.0)**: Pending.
- **v2.0 Revision Rationale**: Pending.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

None
