---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Phase 1A Path Contract Vocabulary and Resolution Model

## 1. Context & Problem (业务背景与核心痛点)
AMS 当前在路径语义和路径解析上缺少明确、可移植、可验证的产品级 contract，导致同一套代码、测试和验证规则在不同宿主环境下表现不一致。GitHub issue #1 与 #9 的最新讨论已经确认：这不是几处 `/root/...` 硬编码的局部缺陷，而是一个更底层的设计问题。

当前主要症状包括：
- repo 资产、研究数据、运行时输出三类路径对象被混用，缺少正式 vocabulary
- 部分代码与测试默认依赖 `/root/projects/AMS/...` 与 `/root/.openclaw/...`
- validation / golden / smoke 检查部分是在验证某台机器的目录布局，而不是验证 AMS 自身的产品 contract
- clean CI runner、non-root 环境、未来容器化环境会暴露伪失败，污染 CI 信号

issue #1 已被重新定义为 root-cause ticket：AMS 缺少 cross-environment path contract 与 environment abstraction。issue #9 则被明确为 validation 层对该问题的下游暴露：只有在 Phase 1A 先定义 vocabulary 与 contract 后，后续 validation 修复才不会退化成“把 CI patch 绿”。

因此，Phase 1A 的目标不是直接修代码，而是先产出一份可执行、可审计的路径语义与解析规则定义，作为后续 Phase 1B（helper layer / precedence）与 Phase 1C（core entry points migration / validation alignment）的上游设计基线。

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements
1. 必须正式定义 AMS 中三类路径对象的 vocabulary，并明确其边界：
   - repo-owned stable assets
   - mutable research/backtest data
   - runtime outputs/state
2. 必须为每一类路径对象定义 canonical resolution rule，而不是允许模块各自 ad hoc 决定。
3. 必须定义 AMS 允许依赖的输入来源与 precedence 原则，至少覆盖：CLI、environment variables、AMS-owned config、project-local default。
4. 必须明确 `project-local default` 的规范含义：除非本 PRD 后续阶段另行定义例外 contract，否则其含义一律为 *anchored at AMS repo root / package root* 的 project-owned default path，而不是 cwd-relative，也不是调用方进程工作目录相对，更不是 config 文件所在目录相对。
5. 必须明确 AMS 不允许依赖的宿主布局假设，至少包括：
   - `/root/projects/AMS/...`
   - `/root/.openclaw/...`
   - `.openclaw/workspace/...` 为 AMS runtime contract 的组成部分
6. 必须定义“repo-relative only”适用范围，确保 repo-owned stable assets 不会被误导向宿主绝对路径或部署目录。
7. 必须定义 runtime outputs/state 的基本约束：可 override、可在 non-root 环境写入、不依赖 OpenClaw workspace 才能工作。
8. 必须定义 runtime outputs/state 的统一 precedence 与冲突行为：默认按 CLI > ENV > AMS-owned config > project-local default 解析；高优先级覆盖低优先级；非法高优先级输入必须 fail-fast，而不是静默回退到低优先级。
9. 必须定义 deployment-relative / deployment-sensitive / deployment-independent 三种语义边界，明确哪些路径允许随部署位置变化，哪些只允许通过显式配置变化，哪些不得被部署位置重新锚定。
10. 必须为后续 Phase 1B/1C 提供清晰边界，使 helper API 与 migration scope 能从本 PRD 直接导出。
11. 必须为 issue #9 的 validation 对齐提供可验证 contract，使 validation/golden/path-consistency/smoke 检查能验证产品规则，而不是机器布局。
12. 必须定义 legacy absolute-path 的兼容与弃用方向，防止历史 `/root/...` 类隐式依赖被误当成长期 contract。

### 2.2 Non-Functional Requirements
1. 设计必须跨环境可移植：local dev、GitHub CI、witness runner、non-root 用户、未来容器化环境均适用。
2. 设计必须可审计：术语、边界、禁止假设、resolution precedence 必须写清楚，避免下游自由发挥。
3. 设计必须收敛概念歧义，尤其不得继续让“canonical dataset”同时指代稳定测试资产与可变研究数据。
4. 设计必须允许后续加 anti-regression guard，防止 `/root/...` 或 `.openclaw/workspace` 依赖重新渗入。

### 2.3 Explicit Scope Boundary
Phase 1A 仅负责 vocabulary、path classes、resolution contract、host-layout assumptions 的产品级定义。

Phase 1A 不负责：
- 实现 helper functions
- 批量改造现有模块
- 直接修复 validation / smoke / golden tests
- 全量 I/O 架构重写
- 与本问题无关的 tech debt 清理

### 2.4 User Stories
- 作为 AMS 开发者，我希望 repo 内稳定资产始终用 repo-relative 语义解析，这样 fixture / golden / baseline 校验不会依赖某台机器路径。
- 作为 AMS 运行者，我希望研究/回测数据路径能通过 CLI、env、config 明确控制，这样系统不会偷偷依赖 `/root/projects/AMS/...`。
- 作为 CI / witness 环境维护者，我希望 validation 与 smoke 只在真实 contract 漂移时失败，而不是因为 runner 不是 root 布局。
- 作为后续 Planner / Coder，我希望看到一份明确 vocabulary 与 precedence 的 PRD，这样 helper API 和迁移范围不需要靠临场猜测。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Core Design Decision
本 PRD 采纳 issue #1 / #9 最新讨论的结论：先定义 path vocabulary 与 contract，再实现 helper 和迁移代码。设计顺序固定为：
- Phase 1A：Vocabulary + Contract Definition
- Phase 1B：Centralized Helper Layer + Resolution Order Encoding
- Phase 1C：Core Runtime Entry Points Migration + Validation Alignment

### 3.2 Path Classes and Semantics

#### A. Repo-Owned Stable Assets
定义：随仓库或正式打包产物交付、需要版本控制、需要在 CI 中可复现的稳定资产。

典型示例：
- `tests/fixtures/...`
- `tests/golden/...`
- baseline metadata
- 属于 repo / package contract 的文档资产

语义要求：
- repo-owned or package-owned
- versioned
- expected stable
- CI-reproducible
- runtime 不应修改源资产
- deployment-independent

resolution rule：
- repo-relative / package-owned only
- project-local default 若适用，锚定 repo root / package root
- 不允许依赖宿主绝对路径
- 不允许以 OpenClaw workspace 作为解析前提
- 不允许因 skill 安装目录、Windows 安装目录或其他部署位置而改变 contract 语义

#### B. Mutable Research/Backtest Data
定义：会随研究、同步、回测过程变化的数据输入，不应伪装为 immutable canonical asset。

典型示例：
- provider-synced research datasets
- backtest input datasets
- 随研究演化的 sidecar metrics / derived inputs

语义要求：
- mutable
- not inherently CI-reproducible unless explicitly provisioned
- 可能不纳入 repo 版本控制
- 允许随环境 / operator 配置变化
- deployment-sensitive but configuration-controlled

resolution rule：
- CLI > ENV > AMS-owned config > project-local default
- project-local default 若使用，锚定 repo root / package root，而不是 cwd
- 允许显式 absolute path 作为 operator override
- 不允许以 `/root/projects/AMS/...` 作为默认 contract
- 不允许继续使用“canonical dataset”作为该类路径的总称
- 不允许因“程序安装到了某处”而隐式改写数据输入位置；部署差异只能通过显式配置 contract 进入

#### C. Runtime Outputs/State
定义：运行时生成的输出、缓存、日志、临时文件或其他 stateful artifacts。

典型示例：
- reports
- cache
- temp outputs
- execution logs

语义要求：
- runtime-managed
- writable in non-root environment
- overrideable
- not source-controlled contract assets
- deployment-relative allowed

resolution rule：
- CLI > ENV > AMS-owned config > project-local default
- project-local default 若使用，表示 AMS 自定义的 project-owned default；实现可在后续阶段将其映射到 deployment-relative runtime base，但不得借宿主工具布局偷渡
- 支持显式 override
- 高优先级覆盖低优先级
- 若高优先级来源值非法，必须 fail-fast，不得静默回退
- 不依赖 `.openclaw/workspace/...` 才能运行
- 默认策略可 deployment-relative，但必须是 AMS 自身定义的 runtime contract，而不是由 OpenClaw skill 路径、Windows 安装目录或调用方 cwd 隐式决定

### 3.3 Vocabulary Decision on “Canonical Dataset” and Project-Local Default
“canonical dataset” 在当前语境中已过载，曾被同时用于：
1. 稳定测试 / golden / fixture 资产
2. 可变研究 / 回测输入数据

该术语在 Phase 1A 中不得再作为跨类别总称使用。后续设计、实现、验证与文档必须改用明确 path class vocabulary。

若下游必须保留历史兼容命名，则仅允许在明确注释其所属 path class 的前提下保留局部兼容层，不得在新 contract 中继续使用模糊总称。

同时，`project-local default` 在本 PRD 中是一个规范化术语，其默认含义固定为：
- 相对于 AMS repo root / package root 解析
- 不相对于调用进程当前工作目录解析
- 不相对于任意外部工具工作目录解析
- 不相对于配置文件物理位置解析，除非未来另立明确 contract

也就是说，`project-local default` 是 *project-owned semantic anchor*，不是“谁调用就跟谁走”的模糊默认值。

### 3.4 Deployment Relation Model

为支持 AMS 同时部署到 OpenClaw skill 环境、Windows 端或其他宿主，本 PRD 明确区分三种语义：

1. **Deployment-independent**
   - 适用于 repo-owned stable assets
   - 其 contract 不因部署位置变化而变化
   - skill 安装目录、Windows 安装目录、OpenClaw workspace 或调用方 cwd 都不得成为其语义锚点

2. **Deployment-sensitive but explicit**
   - 适用于 mutable research/backtest data
   - 其数据位置可以因部署环境不同而不同
   - 但变化只能通过 CLI / ENV / AMS-owned config 等显式 contract 输入
   - 不允许把“安装在哪里”偷渡成“默认就去旁边找数据”

3. **Deployment-relative allowed**
   - 适用于 runtime outputs/state
   - 其默认落点可以与部署环境相关
   - 但该关系必须是 AMS 自己定义的 runtime contract，而不是对特定宿主工具目录布局的依赖
   - 因此“部署相关”不等于“OpenClaw 专属”或“Windows 专属”，而是指在不同部署目标中允许存在不同 runtime base

### 3.5 Allowed and Prohibited Host Assumptions

#### Allowed assumptions
AMS 可以依赖：
- 自身 repository / package layout（仅限 repo-owned stable assets 与 project-owned defaults）
- explicit CLI arguments
- environment variables
- AMS-owned configuration
- 本 PRD 定义的 project-local defaults
- 本 PRD 定义的 deployment-relative runtime contract

#### Prohibited assumptions
AMS 不得依赖：
- `/root/projects/AMS/...` 为固定 repo 路径
- `/root/.openclaw/...` 为固定 state/home 路径
- `.openclaw/workspace/...` 必须存在
- “由 OpenClaw 调用 AMS” 等价于 “AMS 可以把 OpenClaw workspace 当成自身 contract 的一部分”
- “部署到 skill 目录下” 等价于 “所有路径都应该相对 skill 安装目录解析”
- “部署到 Windows 端” 等价于 “repo-owned stable assets 可直接改为安装目录相对”
- validation 通过验证某个宿主目录是否存在来替代验证产品 contract

### 3.6 Legacy Absolute-Path Compatibility and Deprecation Direction
为避免历史行为被误当成长期 contract，本 PRD 明确：
- 对 **repo-owned stable assets**，不提供 legacy absolute-path contract；该类路径必须迁移到 repo-relative / package-owned 语义
- 对 **mutable research/backtest data**，允许显式提供 absolute path，但其语义仅为 operator override，不得被当作默认 contract
- 对 **runtime outputs/state**，允许显式 absolute path override，但其语义同样是 override，而不是对 `/root/...` 或其他宿主布局的固化背书
- 任何历史上依赖 `/root/projects/AMS/...`、`/root/.openclaw/...`、`.openclaw/workspace/...` 的隐式路径行为，只允许在 Phase 1B/1C 中被识别、迁移、隔离或弃用，不允许被重新包装成正式 contract

### 3.7 Required Downstream Interface Responsibilities
Phase 1A 不实现 helper，但必须授权后续 Phase 1B 按以下责任边界落地：
- repo root resolver
- repo-relative path resolver
- mutable research/backtest data resolver with precedence encoding
- runtime output/state resolver with override support
- contract-aware validation/smoke path setup helpers（如需要）

注意：本 PRD 不锁死具体函数名，但 helper 责任必须能一一映射到上述 path classes 和 resolution rules。

### 3.8 Impact on Existing System Areas
后续 Phase 1B/1C 必须优先影响以下系统区域：
- core runtime entry points（例如主运行入口、provider config 入口、validator 路径入口）
- ETL output / report / cache 默认路径处理
- validation / golden / path-consistency / smoke checks
- 文档中仍然宣称 root-only layout 的说明

### 3.9 Trade-off
本设计刻意把“先定义 vocabulary”放在“先绿 CI”之前，代价是 Phase 1A 本身不会立即带来代码层收益。

接受该代价的原因是：如果跳过 Phase 1A，后续极易退化为字符串替换和局部 patch，造成概念继续混乱，最终需要二次返工。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

### 4.1 Phase 1A Document-Level Acceptance

- **Scenario 1: Path classes are explicitly distinguishable and normatively anchored**
  - **Given** 一位 reviewer 或下游执行者依据本 PRD 审阅 AMS 路径 contract
  - **When** 其逐条比对某个路径对象的定义、允许输入来源、deployment relation 与禁止假设
  - **Then** 其能够无需依赖口头解释，将该对象唯一归入 repo-owned stable assets、mutable research/backtest data 或 runtime outputs/state 之一，并确定其是否属于 deployment-independent、deployment-sensitive but explicit 或 deployment-relative allowed

- **Scenario 2: Repo-owned stable assets have a single contract**
  - **Given** 某个 fixture、golden snapshot 或 baseline metadata 属于 repo-owned stable assets
  - **When** 下游依据本 PRD 设计实现或验证逻辑
  - **Then** 该资产必须按 repo-relative 规则解析，且不会被要求依赖 `/root/...` 或 `.openclaw/workspace/...`

- **Scenario 3: Mutable research/backtest data follows explicit precedence**
  - **Given** 某个研究/回测数据路径需要被解析
  - **When** 同时存在 CLI、environment variables、AMS-owned config 与 project-local default 候选来源
  - **Then** 下游必须按 CLI > ENV > AMS-owned config > project-local default 的顺序解析，而不是 ad hoc 选择

- **Scenario 4: Runtime outputs/state follow explicit precedence and do not depend on OpenClaw workspace**
  - **Given** AMS 在 non-root 环境或 clean CI runner 中运行
  - **When** 系统需要解析并生成 reports、cache、logs 或其他 runtime outputs/state
  - **Then** 路径 contract 必须按 CLI > ENV > AMS-owned config > project-local default 的顺序裁决，且允许系统在不依赖 `.openclaw/workspace/...` 的情况下完成运行，并支持显式 override

- **Scenario 5: Validation is anchored to product contract rather than machine layout**
  - **Given** 下游需要修复或重写 validation / golden / path-consistency / smoke 检查
  - **When** 其依据本 PRD 定义验证目标
  - **Then** 测试必须验证 path contract 本身，而不是通过假设 `/root/projects/AMS/...` 存在来判定正确性

- **Scenario 6: The overloaded term “canonical dataset” is no longer used as a design shortcut**
  - **Given** 下游在编写实现、测试或文档
  - **When** 其需要描述路径相关资产
  - **Then** 其不得再用“canonical dataset”同时指代稳定 repo 资产与可变研究数据，而必须使用 path class vocabulary 或显式兼容说明

- **Scenario 7: The PRD is sufficient to derive downstream work partitioning and resolver behavior**
  - **Given** Planner 需要将本工作拆分到后续执行阶段
  - **When** 其基于本 PRD 进行分解
  - **Then** 其能够明确区分哪些属于 Phase 1B helper/resolution-order work，哪些属于 Phase 1C migration/validation-alignment work，并能确定 project-local default、deployment-relative runtime behavior 与 legacy absolute-path handling 的实现边界

### 4.2 Downstream Executability Acceptance

- **Scenario 8: A downstream implementer can prove completion with automated evidence**
  - **Given** 后续 Phase 1B/1C 已完成实现
  - **When** 实现者宣称本 PRD 已被正确落地
  - **Then** 其必须能提供自动化证据证明 repo-relative behavior、precedence behavior、runtime output behavior 与 validation contract behavior 均被验证，而不是仅提供人工说明

- **Scenario 9: Wrong precedence causes deterministic failure**
  - **Given** 同一个 mutable research/backtest data path 同时被 CLI、ENV、config 与 default 指定
  - **When** 实现未遵守 CLI > ENV > AMS-owned config > project-local default 的 precedence
  - **Then** 至少一条自动化测试必须稳定失败，并明确表明 precedence contract 被破坏

- **Scenario 10: Reintroduction of host-layout coupling is detectable**
  - **Given** 后续有人重新引入 `/root/projects/AMS/...`、`/root/.openclaw/...` 或 `.openclaw/workspace/...` 作为运行前提
  - **When** anti-regression guard、smoke、validation 或 contract-focused tests 运行
  - **Then** 自动化验证必须能稳定捕获该回归，而不是继续给出伪绿色信号

- **Scenario 11: Clean non-root execution remains first-class across deployment targets**
  - **Given** AMS 在 clean non-root runner、OpenClaw skill 环境或 Windows 等不同部署目标中执行核心运行与验证流程
  - **When** repo-owned assets、mutable data inputs 与 runtime outputs/state 同时参与运行
  - **Then** 系统必须能够在不借助 root-only layout 或 OpenClaw workspace 假设的前提下通过验证，且 repo-owned stable assets 不会因部署位置变化而改变语义

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 Core Quality Risk
最大风险不是 helper 写错，而是概念模型继续模糊，导致：
- repo assets / mutable data / runtime outputs 继续混用
- validation 继续锚定机器布局
- CI 绿色但 contract 仍然错误
- 后续 helper API 命名和边界发生二次返工
- 团队无法客观判断“已完成”还是“看起来差不多”

### 5.2 Verification Philosophy
本 PRD 的下游完成标准必须满足四层证据，缺一不可：
1. **Document evidence**：术语、边界、precedence、禁止假设与 phase 边界可被独立审阅。
2. **Implementation evidence**：关键入口与 resolver 已按 path class contract 落地，而不是局部 patch。
3. **Automated test evidence**：关键 contract 有自动化验证，且能在 CI 中稳定执行。
4. **Negative/failure evidence**：当 precedence 破坏、宿主耦合回归、runtime 重新依赖 OpenClaw workspace、或 deployment target 被错误地拿来重锚 repo-owned assets 时，自动化验证必须稳定失败。

换言之，下游不得以“人工读代码觉得没问题”作为完成证明，必须提供可重复执行的证据链。

### 5.3 Test Strategy
1. **Phase 1A verification**
   - 以文档审计与设计一致性为主
   - 验证 vocabulary、precedence、禁止假设、scope boundary、verification model 是否自洽且可用于派生实现计划
   - 不要求本阶段编写实现代码

2. **Phase 1B verification guidance**
   - 使用 focused unit tests 验证 resolution precedence
   - 使用 temp-controlled / fixture-controlled setup 验证 mutable data 与 runtime output resolver
   - 必要时 mock environment/config inputs，避免依赖真实宿主布局
   - 对 repo-relative resolver 增加负向测试，确保其不会静默接受宿主绝对路径作为 contract 输入

3. **Phase 1C verification guidance**
   - 使用 black-box validation / smoke / golden tests 验证 contract-aware behavior
   - 在 clean non-root runner 中执行，证明系统不依赖 `/root/...` 或 `.openclaw/workspace/...`
   - 对 repo-owned stable assets 做 repo-relative anti-regression checks
   - 对 core runtime entry points、provider config 入口、validator 路径入口、ETL/report/cache 默认路径处理进行 contract-focused integration checks

### 5.4 Exit Criteria / Evidence Matrix
后续 Phase 1B/1C 只有在以下证据全部成立时，才可宣称本 PRD 已被正确完成：

1. **Repo-owned stable assets contract**
   - 自动化测试证明 fixture / golden / baseline metadata 在不同宿主布局下仍按 repo-relative 解析
   - 至少一条负向验证能够证明：若实现重新依赖 `/root/...` 或其他宿主绝对路径，则测试失败

2. **Mutable research/backtest data precedence contract**
   - 自动化测试覆盖 CLI、ENV、AMS-owned config、project-local default 四层来源
   - 自动化测试证明解析顺序严格为 CLI > ENV > AMS-owned config > project-local default
   - 若 precedence 被打乱，测试必须失败并暴露具体冲突层级

3. **Runtime outputs/state contract**
   - 自动化测试证明 runtime outputs/state 可在 clean non-root 环境中创建与写入
   - 自动化测试证明显式 override 生效
   - 自动化测试证明系统在不存在 `.openclaw/workspace/...` 的条件下仍可运行核心流程

4. **Validation contract alignment**
   - smoke / validation / golden / path-consistency 检查验证的是产品 contract，而不是某个宿主目录是否存在
   - 至少一条回归测试证明：若验证逻辑退回到依赖 root-only layout，则该测试失败

5. **Static / anti-regression guard**
   - 必须存在防回归机制，用于发现新引入的 `/root/projects/AMS/...`、`/root/.openclaw/...`、`.openclaw/workspace/...` 或“把部署目录错误用作 repo-owned asset 锚点”的 contract 依赖
   - 该机制可以是静态扫描、contract test、smoke guard 或其组合，但必须可自动运行

6. **Execution evidence packaging**
   - CI 或等效验证输出必须能向 reviewer 清楚展示：跑了哪些 contract tests、在哪种 clean/non-root 条件下跑、是否包含 failure-mode 验证
   - 若无法提供该证据包，则不得宣称本 PRD 的 downstream implementation 已完成

### 5.5 Mocking / Environment Control Guidance
- 需要 mock 或显式控制的输入主要是：environment variables、config source、temp output directories
- 不应依赖真实 `/root/...` 目录作为测试前提
- 不应依赖 OpenClaw workspace 目录存在与否来制造“成功”
- 对 precedence 测试，应在同一测试场景中同时设置多个候选来源，以验证覆盖关系而不是单源 happy path

### 5.6 Quality Goal
最终质量目标不是“先让几条测试过”，而是：
- path behavior 可被一致解释
- CI 信号只在真实 contract 漂移时失败
- non-root 与 clean runner 环境成为一等支持对象
- future containerization / relocation 不再被历史 root-only 假设卡死
- reviewer 能基于自动化证据而不是口头说明判断完成度

## 6. Framework Modifications (框架防篡改声明)
- None

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial Phase 1A draft created from issue #1 and issue #9 latest design discussion. The draft formalizes path vocabulary, resolution precedence, and prohibited host-layout assumptions.
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
