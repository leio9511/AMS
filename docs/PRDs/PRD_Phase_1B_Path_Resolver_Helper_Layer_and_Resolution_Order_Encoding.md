---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Phase 1B Path Resolver Helper Layer and Resolution Order Encoding

## 1. Context & Problem (业务背景与核心痛点)
AMS 的 Phase 1A 已完成：路径 vocabulary、path classes、resolution precedence、以及禁止的 host-layout assumptions 已被正式定义并审计通过。

Phase 1A 明确了三类路径对象：
- repo-owned stable assets
- mutable research/backtest data
- runtime outputs/state

同时明确了以下约束：
- repo-owned stable assets 必须按 repo-relative / package-owned 语义解析
- mutable research/backtest data 必须按 `CLI > ENV > AMS-owned config > project-local default` 解析
- runtime outputs/state 也必须按 `CLI > ENV > AMS-owned config > project-local default` 解析，支持显式 override，且在 non-root 环境可写
- AMS 不得依赖 `/root/projects/AMS/...`、`/root/.openclaw/...`、`.openclaw/workspace/...` 等宿主布局假设

但当前问题是：这些规则虽然已经在文档层被定义，却还没有成为一套统一、可复用、可验证的代码级机制。

这带来以下风险：
1. 各模块继续各自解析路径，导致 precedence 行为不一致。
2. 后续迁移 `main_runner.py`、ETL、validator、report/cache 路径时，会退化成字符串替换与局部 patch。
3. validation / smoke 可能继续通过机器布局碰巧成立，而不是验证真实 contract。
4. CI 可能再次出现“看起来绿了，但 contract 仍然错误”的伪绿色信号。

因此，Phase 1B 的任务不是直接完成全量入口迁移，而是先建立统一的 path resolver helper layer，把 Phase 1A 定义的 contract 变成 AMS 的公共运行机制，为后续 Phase 1C 的入口迁移提供稳定底座。

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements
1. 必须建立 centralized path helper / resolver layer，使 path contract 不再散落于各模块中重复实现。
2. 必须提供 repo root / repo-relative resolver，用于 repo-owned stable assets。
3. 必须提供 mutable research/backtest data resolver，并严格编码以下 precedence：
   - `CLI > ENV > AMS-owned config > project-local default`
4. 必须提供 runtime outputs/state resolver，并严格编码以下 precedence：
   - `CLI > ENV > AMS-owned config > project-local default`
5. 对 mutable research/backtest data 与 runtime outputs/state，若高优先级来源值非法，系统必须 fail-fast，而不是静默回退到低优先级来源。
6. resolver 必须支持显式 absolute path 作为 override，但不得把历史 `/root/...` 路径行为重新包装成默认 contract。
7. helper layer 必须为后续核心入口接入提供明确接口边界，至少覆盖：
   - main runtime entry point
   - provider/config path entry points
   - ETL output / cache / report 路径入口
   - validation / smoke contract-aware setup helpers（如需要）
8. 必须存在自动化 anti-regression guard，用于发现重新引入 `/root/projects/AMS/...`、`/root/.openclaw/...`、`.openclaw/workspace/...` 依赖的回归。

### 2.2 Non-Functional Requirements
1. Path resolver 行为必须在 clean non-root 环境中可验证。
2. helper layer 必须可审计：reviewer 能清楚判断每个 resolver 负责哪类 path class，以及 precedence 如何裁决。
3. 默认值语义必须稳定，不得依赖 cwd、OpenClaw workspace、调用方外部目录布局、或偶然存在的宿主目录。
4. 设计必须优先支持后续 Phase 1C 迁移，避免 1B 自己成为新的 ad hoc compatibility layer。

### 2.3 Scope Boundaries
Phase 1B 负责：
- centralized helper layer
- resolution precedence 编码
- failure semantics（非法高优先级输入 fail-fast）
- contract-focused tests / guards
- 必要的少量入口接线，用于证明 helper layer 可被核心系统消费

Phase 1B 不负责：
- 一次性迁完所有 core runtime entry points
- 全量 validation / smoke / ETL / backtest 流程重构
- 借题进行广义 I/O architecture rewrite
- 与 path contract 无关的技术债清理

### 2.4 User Stories
- 作为 AMS 开发者，我希望路径解析逻辑集中在公共 helper 层中，这样新模块不必继续自己猜默认路径和优先级。
- 作为 AMS 运行者，我希望 mutable data 和 runtime outputs 的路径来源可预测且可覆盖，这样我能清楚知道系统读写的是哪一层配置。
- 作为 CI / witness 环境维护者，我希望系统在 non-root 和 clean runner 下也能稳定运行，而不是依赖 root-only layout。
- 作为后续 Phase 1C 的执行者，我希望已有一套稳定 resolver contract，这样入口迁移只是“接入 contract”，而不是再次设计 contract。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Core Design Decision
Phase 1B 采纳 Phase 1A 已锁定的顺序：
- Phase 1A：Vocabulary + Contract Definition
- Phase 1B：Centralized Helper Layer + Resolution Order Encoding
- Phase 1C：Core Runtime Entry Points Migration + Validation Alignment

因此本阶段的目标不是扩散到全仓入口迁移，而是把 contract 固化为公共机制。

### 3.2 Required Resolver Responsibilities
本阶段必须落地一层 path resolver helper，责任边界至少包括：
- repo root resolver
- repo-relative path resolver
- mutable research/backtest data resolver
- runtime outputs/state resolver
- contract-aware validation/smoke setup helper（如现有验证层需要）

本 PRD 不锁死函数名，但要求这些责任能被明确映射到实现与测试中。

### 3.3 Resolver Semantics by Path Class

#### A. Repo-Owned Stable Assets
语义：
- deployment-independent
- repo-relative / package-owned only
- 不允许依赖宿主绝对路径
- 不允许被 OpenClaw workspace 或调用方 cwd 重锚定

Phase 1B 要求：
- 统一提供 repo root 与 repo-relative 解析能力
- 至少一条负向验证必须证明：若重新依赖 `/root/...` 等宿主路径，contract test 会失败

#### B. Mutable Research/Backtest Data
语义：
- configuration-controlled
- deployment-sensitive but explicit
- 可显式 absolute override
- 不得把历史 `/root/projects/AMS/...` 当成默认 contract

Phase 1B 要求：
- 明确编码 precedence：`CLI > ENV > AMS-owned config > project-local default`
- `project-local default` 必须锚定 AMS project root / package root，而不是 cwd
- 同一场景中若多层来源同时存在，resolver 必须按 contract 决定唯一结果
- 若最高优先级值非法，必须 fail-fast

#### C. Runtime Outputs/State
语义：
- runtime-managed
- writable in non-root environment
- overrideable
- deployment-relative allowed
- 不依赖 `.openclaw/workspace/...`

Phase 1B 要求：
- 明确编码 precedence：`CLI > ENV > AMS-owned config > project-local default`
- 显式 override 必须生效
- illegal high-priority input 必须 fail-fast
- 默认 runtime 行为必须由 AMS 自身 contract 决定，不能偷渡宿主工具目录布局

### 3.4 Provenance and Debuggability
本阶段建议 resolver 在内部或可观测接口上保留 resolution provenance 能力，即能够说明某个最终路径来自 CLI、ENV、config 或 default 哪一层。

该能力不是为了暴露实现细节，而是为了：
- 降低排查 precedence 错误的成本
- 提高 reviewer 对 contract 是否真实落地的可审计性
- 防止“结果对了但来源错了”的隐蔽漂移

若实现不暴露完整 provenance 对外接口，也必须至少在测试或调试层面证明 precedence 裁决是可追踪的。

### 3.5 Priority of Impacted System Areas
Phase 1B 应优先让以下区域可以消费 resolver，而不是各自保留独立路径规则：
1. main runtime entry point
2. provider / config path entry points
3. ETL output / report / cache 默认路径入口
4. validation / golden / path-consistency / smoke 的 contract-aware setup

注意：本阶段可以只选择少量代表性入口接线来证明 helper layer 有效，但必须保证接口设计足以支持后续扩展到其余入口。

### 3.6 Legacy Behavior Handling
历史上依赖以下路径的行为：
- `/root/projects/AMS/...`
- `/root/.openclaw/...`
- `.openclaw/workspace/...`

在本阶段中只能被：
- 识别
- 隔离
- 迁移
- 弃用

不得被重新描述为正式默认 contract。

如果某处需要临时兼容层，必须符合以下原则：
- 仅作为显式 override 或隔离 shim 存在
- 不能改变 path class 的语义边界
- 不能让后续 Phase 1C 误以为该兼容行为就是长期产品 contract

### 3.7 Trade-off
本设计刻意限制 1B 范围，不要求本阶段“一次迁完一切”，代价是某些 legacy entry point 仍会在 1C 才完成最终接入。

接受该代价的原因是：
- 如果 helper layer 尚未稳定就大规模迁移入口，会把旧混乱以新名字复制一遍
- 1B 的真正价值是先消除“每个模块都有自己的路径常识”
- 只有当 resolver 机制本身稳定可信，1C 的迁移才不会退化成批量 patch

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Repo-owned stable assets resolve repo-relatively regardless of host layout**
  - **Given** 某个 fixture、golden snapshot 或 baseline metadata 属于 repo-owned stable assets
  - **When** AMS 在不同宿主布局或 clean non-root 环境中解析该资产
  - **Then** 系统必须按 repo-relative / package-owned contract 解析该资产，而不是要求 `/root/...` 或 `.openclaw/workspace/...` 存在

- **Scenario 2: Mutable data precedence is deterministic and contract-compliant**
  - **Given** 同一个 mutable research/backtest data path 同时由 CLI、ENV、AMS-owned config 与 project-local default 提供候选值
  - **When** resolver 解析该数据路径
  - **Then** 最终结果必须严格按 `CLI > ENV > AMS-owned config > project-local default` 选定，且不存在 ad hoc 选择

- **Scenario 3: Invalid high-priority mutable data input fails fast**
  - **Given** 高优先级来源为 mutable research/backtest data 提供了非法路径值
  - **When** resolver 尝试解析该路径
  - **Then** 系统必须 fail-fast 并暴露 contract violation，而不是静默回退到低优先级来源

- **Scenario 4: Runtime outputs/state are writable without OpenClaw workspace dependency**
  - **Given** AMS 在 clean non-root 环境中运行，且 `.openclaw/workspace/...` 不存在
  - **When** 系统需要生成 reports、cache、logs 或其他 runtime outputs/state
  - **Then** 系统必须仍可按 contract 解析并创建可写路径，不得把 OpenClaw workspace 当作运行前提

- **Scenario 5: Runtime output precedence honors explicit override**
  - **Given** runtime outputs/state 同时存在 CLI、ENV、config 与 default 候选来源
  - **When** resolver 解析输出目录
  - **Then** 最终结果必须严格按 `CLI > ENV > AMS-owned config > project-local default` 选定，且显式 override 必须生效

- **Scenario 6: Project-local default is project-anchored rather than cwd-anchored**
  - **Given** 调用方从不同 cwd 启动 AMS，且未提供更高优先级路径来源
  - **When** resolver 使用 project-local default 解析 mutable data 或 runtime output 路径
  - **Then** 默认值必须锚定 AMS project root / package root，而不是跟随调用进程 cwd 漂移

- **Scenario 7: Reintroduction of host-layout coupling is automatically detectable**
  - **Given** 后续有人重新引入 `/root/projects/AMS/...`、`/root/.openclaw/...` 或 `.openclaw/workspace/...` 作为默认运行前提
  - **When** contract-focused tests、anti-regression guards、smoke 或 validation 运行
  - **Then** 自动化验证必须能稳定捕获该回归，而不是继续给出伪绿色信号

- **Scenario 8: A representative core entry point can consume the resolver layer**
  - **Given** 一个代表性的核心入口需要解析 repo assets、mutable data 或 runtime outputs
  - **When** 该入口接入 Phase 1B resolver layer
  - **Then** 它必须通过公共 contract 解析路径，而不是继续内置独立的 ad hoc 路径规则

- **Scenario 9: Completion proof requires automated evidence rather than verbal assurance**
  - **Given** 实现者宣称 Phase 1B 已完成
  - **When** reviewer 审查交付结果
  - **Then** 必须能看到自动化证据证明 repo-relative behavior、precedence behavior、fail-fast behavior 与 anti-regression behavior 已被验证，而不是仅有人工说明

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 Core Quality Risk
本阶段最大风险不是 helper API 起名不好，而是：
- contract 看似落地，实际上仍然散落在各模块中
- precedence 名义上统一，实际不同入口行为不一致
- 测试只验证 happy path，没有验证错误 precedence 或 root-only regression
- helper layer 只是给旧逻辑套了个新名字，导致 1C 迁移时再次返工

### 5.2 Verification Philosophy
Phase 1B 的完成证明必须优先回答以下问题：
1. path contract 是否已从文档规则变成公共代码机制？
2. precedence 是否被自动化验证，而不是靠 reviewer 信任？
3. fail-fast 与 anti-regression 行为是否真实存在？
4. helper layer 是否已被至少一个代表性入口消费，证明它不是“没人用的工具箱”？

### 5.3 Recommended Test Structure
1. **Contract-focused unit tests**
   - 验证 repo root / repo-relative 解析行为
   - 验证 mutable data precedence
   - 验证 runtime output precedence
   - 验证非法高优先级输入 fail-fast

2. **Temp-controlled / fixture-controlled tests**
   - 使用 temp dir、fixture dir、mocked env/config 来源
   - 禁止依赖真实 `/root/...` 目录或 `.openclaw/workspace/...` 作为成功前提

3. **Representative integration checks**
   - 选择少量关键入口，验证其已通过公共 resolver 消费路径 contract
   - 重点看入口是否摆脱 ad hoc path rules，而不是追求大而全的流程覆盖

4. **Negative / anti-regression checks**
   - 至少一类机制能检测重新引入 `/root/projects/AMS/...`
   - 至少一类机制能检测重新依赖 `/root/.openclaw/...`
   - 至少一类机制能检测重新依赖 `.openclaw/workspace/...`

### 5.4 Mocking / Environment Control Guidance
需要 mock 或显式控制的输入包括：
- CLI 参数
- environment variables
- AMS-owned config source
- temp output directories
- clean/non-root execution conditions

不应依赖：
- 调用方 cwd 偶然正确
- root-only layout 偶然存在
- OpenClaw workspace 恰好可写

### 5.5 Exit Criteria
只有在以下证据全部成立时，才可宣称 Phase 1B 完成：
1. 已存在 centralized helper/resolver layer，且责任边界清晰。
2. 已存在自动化测试覆盖 mutable data 与 runtime outputs 的 precedence。
3. 已存在自动化测试覆盖 invalid high-priority input fail-fast 行为。
4. 已存在自动化机制检测 `/root/...` 与 `.openclaw/workspace/...` 回归。
5. 已有至少一个代表性入口通过公共 resolver 消费路径 contract。
6. 相关验证能在 clean non-root 条件下稳定执行。

### 5.6 Quality Goal
本阶段最终质量目标不是“又过了几条测试”，而是：
- AMS 从此拥有统一路径解析机制
- reviewer 能客观判断路径行为是否符合 contract
- non-root / clean runner 成为一等支持对象
- Phase 1C 可以在既有 resolver 之上做迁移，而不是重新发明规则

## 6. Framework Modifications (框架防篡改声明)
- None

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial Phase 1B draft created from the completed Phase 1A path-contract discussion. The design centers Phase 1B on centralized resolvers, explicit precedence encoding, fail-fast semantics, and contract-focused verification, while deliberately deferring broad core-entry migration to Phase 1C.
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
