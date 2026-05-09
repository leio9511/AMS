---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: Sensitivity Sanity Validation Cost Reduction and Preflight Stabilization

## 1. Context & Problem (业务背景与核心痛点)
AMS 当前已经显著推进了 Preflight Stabilization 工作：
- 依赖分层已建立
- path-contract / validation / main runtime / ignore-manifest 等关键历史 bucket 已被逐步修复
- 当前 GitHub CI preflight 在现有 quarantine 配置下是绿色的

但 Phase 4（#6）要求的终态不是“带着临时 quarantine 也能绿”，而是：
*在 clean non-root 环境里，preflight 能自然跑完并自然绿色。*

最新验证显示，历史 ignore list 里的大多数测试文件已经不再是实际 blocker。把这些历史 ignore 移除后，真正暴露出来的尾段稳定性问题集中在：
- `tests/validation/test_sensitivity_sanity.py`

该文件的症状并不是普通 assertion failure：
- 单个 sensitivity case（`test_stop_loss_sensitivity` / `test_tp_pos_sensitivity` / `test_tp_intra_sensitivity`）都能单独跑通
- 每个 case 大约需要 60–80 秒
- 这些 case 放到 full preflight 尾段后，会显著拉长执行时间并造成 preflight 无法稳定自然收尾

进一步代码审查表明，这个文件当前的成本模型明显偏重：
- 每个 sensitivity test 都通过 `subprocess.run(...)` 启动完整 `main_runner.py` CLI 子进程
- 每个 test 都重新读取同一份 golden baseline config
- 前 3 个 sensitivity tests 都会重复跑 baseline + perturbed case
- 整个文件本质上在重复支付相同的重型 backtest/CLI 启动成本

这说明当前问题更像是：
*测试结构本身低效、重复做重活，导致它不再适合作为主 preflight 路径中的稳定 contract test。*

本 PRD 的目标不是更改 AMS 交易逻辑，而是：
- 保留 sensitivity sanity 的产品级验证价值
- 显著降低此测试文件的执行成本与不稳定性
- 使它重新适合作为主 preflight 路径的一部分
- 为后续清空 ignore list、关闭 Phase 4 创造条件

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements
1. `tests/validation/test_sensitivity_sanity.py` 必须继续验证以下核心 contract：
   - 改变 `sl` 会影响 summary 结果
   - 改变 `tp_pos` 会影响 summary 结果
   - 改变 `tp_intra` 会影响 summary 结果
2. 文件中当前的 sensitivity checks 必须从“重复完整 CLI backtest”结构优化为“共享公共重计算结果 / 明显减少重复执行”的结构。
3. 在不损害 contract 真实性的前提下，测试必须尽量复用：
   - baseline config 读取
   - baseline run 结果
   - 通用比较逻辑
4. 如果可以在不牺牲 contract 价值的前提下减少 CLI 子进程依赖，则应优先减少或消除 `subprocess.run(main_runner.py ...)` 的重复使用。
5. 若保留 CLI 路径验证，则只允许保留最小必要的 CLI-level surface；不得继续让每个 sensitivity dimension 都完整重复一轮高成本 CLI flow。
6. 优化后，这个测试文件必须能够在主 preflight 路径中稳定运行，而不再成为 Phase 4 natural-green 的执行稳定性 blocker。

### 2.2 Non-Functional Requirements
1. 本次修复不得改变 AMS 主策略逻辑、回测语义或参数意义；目标是测试结构优化，不是业务行为改写。
2. 测试仍须 deterministic，继续依赖 repo-owned stable golden asset 或等价稳定 fixture，不得引入环境耦合。
3. 测试必须保持 reviewable：未来维护者应能清楚看出 sensitivity contract 在验证什么，而不是被过度抽象后失去语义可读性。
4. 优化后的测试文件运行成本必须显著低于当前版本，至少不应继续表现为“每个 case 约一分钟量级并在 full preflight 尾段形成稳定性问题”。

### 2.3 Scope Boundaries
本 PRD 负责：
- `tests/validation/test_sensitivity_sanity.py` 的结构重构与成本优化
- 如有必要，为该测试引入轻量辅助函数/fixture
- 在必要范围内选择更合适的调用层（CLI vs in-process）以减少重复成本

本 PRD 不负责：
- 改动交易策略逻辑
- 改动 golden baseline 产品含义
- 大规模重写 `main_runner.py`
- 重写完整 validation framework
- 清理所有 remaining preflight performance 问题（本次聚焦此文件）

### 2.4 User Stories
- 作为 preflight 维护者，我希望 sensitivity sanity 验证继续存在，但不要再因为测试结构过重而让 full preflight 不稳定。
- 作为架构审阅者，我希望看到 sensitivity contract 仍被真实验证，而不是简单删除或降格成无意义 smoke。
- 作为 CI 使用者，我希望 Phase 4 的“natural green”不再被一个重复做重型回测的测试文件阻塞。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Core Design Decision
本次修复的核心判断是：
*当前 blocker 主要是测试成本模型，而不是产品逻辑错误。*

因此，本 PRD 选择优化：
- 重复 baseline 计算
- 重复 CLI 子进程启动
- 重复参数比较代码

而不是去修改 trading/backtest 核心业务逻辑。

### 3.2 Recommended Optimization Ladder
本 PRD 允许以下优化层级，按优先级从高到低实施：

#### Layer A — Shared baseline/result reuse (最低风险、优先)
- 把基准配置读取提取为共享 fixture/helper
- 把 baseline result / baseline summary 提取为共享 fixture
- 避免每个 sensitivity test 都重新跑一遍同样的 baseline case

#### Layer B — Parameterized sensitivity cases
- 将 `sl` / `tp_pos` / `tp_intra` 三个 sensitivity tests 重构为参数化测试，统一复用：
  - baseline summary
  - perturbation runner
  - metric comparison logic
- 保持失败信息对具体参数维度仍然可读

#### Layer C — Prefer in-process execution over repeated subprocess CLI runs (若可行则优先采用)
- 若可以在不降低 contract 真实性的前提下，直接调用 backtest/runtime 的进程内 API，则优先采用该方案
- 仅保留最小必要的 CLI-level validation surface
- 明确禁止“为了优化速度而完全放弃 sensitivity contract 的真实执行路径”

#### Layer D — Smaller dedicated stable fixture (仅在前 3 层不足时采用)
- 若共享 baseline + 参数化 + in-process 调用仍不足以把成本降到可接受范围，可引入更小、更专用的 sensitivity stable fixture
- 新 fixture 必须仍能稳定证明 `sl` / `tp_pos` / `tp_intra` 改变会引发 summary 差异
- 不允许用过于玩具化的数据集，让测试退化成对实现偶然性的假证明

### 3.3 Forbidden Anti-Patterns
本 PRD 明确禁止以下伪修复：
- 直接删除 `tests/validation/test_sensitivity_sanity.py`
- 把该文件长期加入 ignore list 并宣称问题解决
- 保留当前逐 case 重跑完整 baseline + perturbed CLI flow，只是轻微改名/改注释
- 为了降速而把 sensitivity contract 改成纯 mock/纯假数据逻辑，导致不再验证真实 execution path
- 通过放宽 assertion 让测试“更快过”，而不是从结构上减少重复重活

### 3.4 Targeted Surfaces
本 PRD 授权优先改动：
- `tests/validation/test_sensitivity_sanity.py`
- 必要时，与该测试直接配套的轻量 helper/fixture 代码
- 若必须，允许最小范围调整其调用的 runner entry surface，以支持进程内执行

未经明确必要性证明，不应扩散到大量无关测试文件。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Stop-loss sensitivity remains provable after optimization**
  - **Given** 一个固定的 sensitivity baseline case
  - **When** `sl` 从 baseline 值变更为明确不同的 perturbation 值
  - **Then** 优化后的测试必须仍然证明 summary 结果发生变化，而不是退化为只验证函数是否可调用

- **Scenario 2: Take-profit position sensitivity remains provable after optimization**
  - **Given** 同一个固定的 sensitivity baseline case
  - **When** `tp_pos` 从 baseline 值变更为明确不同的 perturbation 值
  - **Then** 优化后的测试必须仍然证明 summary 结果发生变化

- **Scenario 3: Intra-bar take-profit sensitivity remains provable after optimization**
  - **Given** 同一个固定的 sensitivity baseline case
  - **When** `tp_intra` 从 baseline 值变更为明确不同的 perturbation 值
  - **Then** 优化后的测试必须仍然证明 summary 结果发生变化

- **Scenario 4: Optimized structure eliminates redundant baseline recomputation**
  - **Given** 优化后的 sensitivity sanity test file
  - **When** 审阅者检查测试结构与执行路径
  - **Then** 能明确看出 baseline 读取和/或 baseline 运行结果被复用，而不是每个 sensitivity dimension 完整重复一次同样的高成本计算

- **Scenario 5: Optimized file is stable in main preflight path**
  - **Given** 该测试文件重新纳入主 preflight 路径
  - **When** 在 clean non-root 环境中运行 `bash preflight.sh`
  - **Then** 该文件不得再表现为 tail-stage execution stability blocker

- **Scenario 6: Optimization does not alter business semantics**
  - **Given** 优化后的测试实现
  - **When** 审阅者比对其验证目标与原始 sensitivity intent
  - **Then** 该优化必须被理解为“结构降重”，而不是“放弃真实 sensitivity contract”

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
本需求的核心风险不是 correctness regression，而是“为了降低测试成本，误伤 contract 真实性”。

### 5.1 Quality Goal
- sensitivity contract 继续真实存在
- 运行成本显著下降
- full preflight 对该文件不再表现出尾段稳定性问题

### 5.2 Verification Strategy
1. **Focused test-file verification**
   - 单独运行 `tests/validation/test_sensitivity_sanity.py`
   - 验证所有 sensitivity cases 仍然通过
2. **Execution-cost sanity check**
   - 与当前版本相比，审阅者应能从结构和实际运行表现中判断重复 heavy work 已显著减少
3. **Preflight-path verification**
   - 在该文件被纳回主 preflight 路径后，运行 `bash preflight.sh`
   - 确认 preflight 不再在该文件尾段形成明显稳定性问题
4. **Contract-preservation review**
   - reviewer 必须明确确认：优化后的测试仍在验证真实 sensitivity contract，而不是降格成空洞 smoke

### 5.3 Mocking / Isolation Guidance
- 不推荐把 sensitivity contract 改成纯 mock
- 若采用 in-process 调用，可保留真实 golden/stable asset 输入，减少 CLI/process overhead
- 只有在前述方式仍不足时，才允许引入更小的 dedicated stable fixture

### 5.4 Smallest Meaningful Success Signal
- `tests/validation/test_sensitivity_sanity.py` 全绿
- 结构上能看出 baseline/result reuse
- 完整 preflight 不再因该文件而成为尾段稳定性 blocker

## 6. Framework Modifications (框架防篡改声明)
- 本 PRD 不授权修改 SDLC framework
- 仅授权修改 AMS 仓库内与 `tests/validation/test_sensitivity_sanity.py` 直接相关的测试与最小必要支持面

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft created after verifying that the historical ignore-list entries largely pass when unquarantined, while `tests/validation/test_sensitivity_sanity.py` emerges as the remaining practical Phase 4 blocker. Follow-up measurement showed each of the three heavy sensitivity cases passes independently but costs ~60–80 seconds, supporting a test-structure optimization strategy over a business-logic rewrite.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- None
