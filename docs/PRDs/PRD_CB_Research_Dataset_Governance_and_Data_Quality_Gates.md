---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: CB_Research_Dataset_Governance_and_Data_Quality_Gates

## 1. Context & Problem (业务背景与核心痛点)
AMS 2.0 已完成统一回测入口、Validation Framework MVP 与第一版 golden regression，理论上正接近 `Phase 2: Live QMT Integration`。

但当前 CB research/backtest dataset 仍存在一个会直接污染研究结论的 blocking issue：**正式研究数据路径不唯一、关键字段存在静默默认值污染、现有 validator 只有 schema/field-level 校验，没有 dataset-level semantic gate。**

当前已复核到的事实包括：
1. AMS 文档声明的 canonical path 是 `/root/projects/AMS/data/cb_history_factors.csv`，但 `main_runner.py` 默认仍曾指向 `/root/.openclaw/workspace/data/cb_history_factors.csv`，造成正式研究与实际默认消费对象不一致。
2. `etl/jqdata_sync_cb.py` 仍对关键字段使用静默默认值兜底，例如：
   - premium 拉取失败 -> `0.0`
   - merge 后 `fillna(0.0)`
   - `is_st` -> `fillna(False)`
   - redemption 拉取失败/异常 -> `False`
3. 现有 `ams.validators.cb_data_validator` 只能判断“结构是否合法”，不能判断“整张研究数据在金融语义上是否已经塌缩为默认值世界”。
4. 这类污染会直接影响：
   - CB 双低排序
   - ST 过滤
   - 强赎过滤
   - 参数搜索
   - 资金曲线与研究结论

因此，本 PRD 的目标不是“再补几个 test”，而是建立 **AMS 正式 CB research/backtest dataset 的唯一数据治理合同**，把以下四件事同时钉死：
- 唯一 canonical path
- 关键字段 fail-fast
- dataset-level semantic validation
- atomic promotion / rollback

这是进入 AMS Phase 2 前必须完成的数据质量门。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. AMS 正式 CB research/backtest dataset 的唯一 canonical path 必须固定为：
   - `/root/projects/AMS/data/cb_history_factors.csv`
2. `main_runner.py` 默认必须消费该 canonical path，不再默认消费任何 workspace 副本路径。
3. 本 PRD 不允许引入第二条正式 canonical research path，也不允许把“未来外置数据根目录”作为本次实现的另一条可选落点。
4. `etl/jqdata_sync_cb.py` 必须在关键字段语义异常时 fail-fast，禁止静默默认值成功产出正式研究数据。
5. 关键字段范围固定为：
   - `premium_rate`
   - `is_st`
   - `is_redeemed`
   - `underlying_ticker`
6. 正式 research dataset 必须通过两层质量门后才能覆盖 canonical dataset：
   - schema / field-level validation
   - dataset-level statistical / semantic validation
7. Golden dataset 与 fixture dataset 必须与 research dataset 分层治理，不得混为同一职责。
8. 本 PRD 不授权自动刷新 golden snapshot；如需刷新，必须在 research dataset 修复并通过 gate 后作为显式后续动作执行。

### Non-Functional Requirements
1. 质量门必须可自动运行，不能依赖人工 spot-check。
2. 数据异常时必须 fail-fast，不允许 silently wrong。
3. Promotion 必须是原子化的；失败时 canonical dataset 必须保持旧版本不变或被自动恢复。
4. 所有阈值、基线与 promotion/rollback 规则必须是定量合同，而不是模糊原则。
5. 本方案必须保持低爆炸半径，只治理 AMS 当前 CB research dataset 生产链，不扩散成半套数据平台重构。

### Boundaries
- **In Scope**:
  - `main_runner.py` 默认 research path 修正
  - `etl/jqdata_sync_cb.py` 的 fail-fast 与 promotion gate
  - `ams.validators.cb_data_validator.py` 与新增 dataset-level semantic validator
  - canonical dataset metrics/manifest
  - promotion / rollback 合同
  - 文档更新（ROADMAP / ARCHITECTURE）
- **Out of Scope**:
  - 正式 research dataset 外置到 repo 之外的数据根目录
  - QMT live execution broker
  - 新策略开发
  - walk-forward 体系扩展
  - golden snapshot 刷新执行本身

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Unique Canonical Research Path
本次 PRD 只允许一个正式落点：
- **唯一 canonical research dataset**: `/root/projects/AMS/data/cb_history_factors.csv`

本次实现必须把以下路径视为 legacy source / legacy contamination source，而不是正式默认研究数据源：
- `/root/.openclaw/workspace/data/cb_history_factors.csv`

未来若要把正式 research dataset 外置到 repo 外部目录，应新开后续 issue/PRD 处理。本次绝不允许双轨并存。

### 3.2 Dataset Role Separation
本次必须明确并固化三层数据角色：
1. **Research / Backtest Dataset**
   - 用于正式研究、参数搜索、回测结论生产
   - 唯一路径：`/root/projects/AMS/data/cb_history_factors.csv`
   - 必须追求真实，不允许 mock/default 值污染
2. **Golden Dataset**
   - 用于 regression / UAT / CI 回归
   - 可为显式冻结快照，但不承担正式研究数据职责
3. **Fixture Dataset**
   - 用于 deterministic logic-trigger tests
   - 重点是触发逻辑，不以市场真实性为第一目标

### 3.3 Two-Layer Validation Contract
#### Layer 1: Schema / Field-Level Validation
目标：保证结构合法。
最低要求：
- 列存在
- 类型正确
- `close > 0`
- `premium_rate` 值域合法
- `is_st` / `is_redeemed` 为布尔类型

#### Layer 2: Dataset-Level Statistical / Semantic Validation
目标：保证研究语义可信。
对候选 canonical research dataset，必须一次性计算并校验下列硬门槛：

1. **Minimum row count**
   - `row_count >= 50000`

2. **Underlying ticker coverage**
   - `underlying_ticker_nonnull_ratio >= 0.99`

3. **Premium-rate non-default gate**
   - `premium_rate_nonzero_ratio >= 0.95`
   - `premium_rate_zero_ratio <= 0.05`

4. **ST event-presence gate**
   - `is_st_true_count >= 1`

5. **Redemption event-presence gate**
   - `is_redeemed_true_count >= 1`

6. **No full-default-column gate**
   - `premium_rate` 不得整列为 `0.0`
   - `is_st` 不得整列为 `False`
   - `is_redeemed` 不得整列为 `False`

### 3.4 Baseline Comparison Contract
候选数据集必须与“当前 canonical dataset 的 metrics baseline”比较。唯一基线文件固定为：
- `/root/projects/AMS/data/cb_history_factors.metrics.json`

该 metrics baseline 必须至少记录：
- `row_count`
- `underlying_ticker_nonnull_ratio`
- `premium_rate_nonzero_ratio`
- `premium_rate_zero_ratio`
- `is_st_true_count`
- `is_redeemed_true_count`
- `generated_at`
- `source_lineage`

在当前 canonical dataset 已存在的前提下，候选数据还必须通过以下 drift guardrail：
1. `row_count_drop_ratio <= 0.20`
   - 即候选数据行数不得比当前 canonical dataset 下降超过 20%
2. `premium_rate_nonzero_ratio_drop <= 0.10`
   - 即候选数据的 `premium_rate_nonzero_ratio` 不得比当前 baseline 下降超过 0.10 的绝对值
3. 若当前 baseline 中 `is_st_true_count > 0`，则候选数据的 `is_st_true_count` 不得为 `0`
4. 若当前 baseline 中 `is_redeemed_true_count > 0`，则候选数据的 `is_redeemed_true_count` 不得为 `0`

### 3.5 Atomic Promotion / Rollback Contract
本次必须引入固定的候选文件与 promotion 规则。

固定文件：
- 候选 CSV：`/root/projects/AMS/data/cb_history_factors.csv.tmp`
- 候选 metrics：`/root/projects/AMS/data/cb_history_factors.metrics.json.tmp`
- 备份 CSV：`/root/projects/AMS/data/cb_history_factors.csv.bak`
- 备份 metrics：`/root/projects/AMS/data/cb_history_factors.metrics.json.bak`

Promotion 合同：
1. ETL 先生成候选 CSV 与候选 metrics
2. 对候选 CSV 执行 Layer 1 + Layer 2 校验
3. 若任一质量门失败：
   - 直接退出非零
   - canonical dataset 与 canonical metrics 保持不变
4. 若通过全部质量门：
   - 先备份当前 canonical dataset 与 canonical metrics
   - 再使用原子替换（`os.replace` 级别语义）覆盖 canonical 文件
5. 若 promotion 过程中任一替换步骤失败：
   - 立即使用 `.bak` 恢复旧 canonical dataset 与旧 metrics
   - 返回非零退出码

### 3.6 Integration Points
本次授权修改的主文件：
- `main_runner.py`
- `etl/jqdata_sync_cb.py`
- `ams/validators/cb_data_validator.py`
- 新增 dataset-level semantic validator / metrics helper（若需要）
- `docs/ROADMAP.md`
- `docs/architecture/ARCHITECTURE.md`

### 3.7 Deliberate Restraint
本次不做：
- repo 外正式数据根目录迁移
- 任意多版本数据湖/仓库治理
- golden snapshot 自动刷新
- 新 engine / new strategy 设计

本次只解决一件事：
- **把 AMS 正式 CB research dataset 的唯一路径、质量门与 promotion 机制焊死。**

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Default CLI uses the unique canonical research path**
  - **Given** AMS 项目中存在正式 canonical research dataset `/root/projects/AMS/data/cb_history_factors.csv`
  - **When** 不显式传入 `--data-path` 执行 `main_runner.py`
  - **Then** 系统必须默认消费 `/root/projects/AMS/data/cb_history_factors.csv`
  - **And** 不再默认消费 `/root/.openclaw/workspace/data/cb_history_factors.csv`

- **Scenario 2: Candidate dataset with collapsed premium_rate is rejected**
  - **Given** 一个候选 dataset 满足 `premium_rate_nonzero_ratio < 0.95`
  - **When** 运行正式 research dataset validation
  - **Then** 校验必须失败
  - **And** canonical dataset 不得被覆盖

- **Scenario 3: Candidate dataset with zero ST/redemption events is rejected**
  - **Given** 一个候选 dataset 满足 `is_st_true_count = 0` 或 `is_redeemed_true_count = 0`
  - **When** 运行正式 research dataset validation
  - **Then** 校验必须失败
  - **And** canonical dataset 不得被覆盖

- **Scenario 4: Candidate dataset below minimum scale is rejected**
  - **Given** 一个候选 dataset 满足 `row_count < 50000`
  - **When** 执行正式 promotion 流程
  - **Then** ETL 必须返回非零退出码
  - **And** canonical dataset 保持旧版本不变

- **Scenario 5: Drift regression blocks abnormal shrinkage**
  - **Given** 当前 canonical metrics baseline 已存在
  - **And** 候选 dataset 的 `row_count_drop_ratio > 0.20` 或 `premium_rate_nonzero_ratio_drop > 0.10`
  - **When** 执行正式 promotion 流程
  - **Then** 系统必须拒绝本次 promotion
  - **And** 不得覆盖 canonical dataset

- **Scenario 6: Valid candidate dataset is atomically promoted**
  - **Given** 候选 dataset 同时通过 Layer 1、Layer 2 与 baseline drift checks
  - **When** 执行正式 promotion 流程
  - **Then** `/root/projects/AMS/data/cb_history_factors.csv` 必须被原子替换为新版本
  - **And** `/root/projects/AMS/data/cb_history_factors.metrics.json` 必须同步更新
  - **And** `.bak` 文件必须保留可恢复的旧版本

- **Scenario 7: Failed promotion restores previous canonical state**
  - **Given** 新候选数据已通过校验但 promotion 原子替换中途失败
  - **When** 系统执行 rollback
  - **Then** canonical dataset 必须恢复为旧版本
  - **And** 返回非零退出码

- **Scenario 8: Phase 2 gate is explicit in documentation**
  - **Given** AMS 正准备进入 Phase 2
  - **When** 检查 `docs/ROADMAP.md` 与 `docs/architecture/ARCHITECTURE.md`
  - **Then** 文档必须明确：只有在 `ISSUE-1142` 收口后，才允许进入 Phase 2

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
最大的风险不是 ETL 崩溃，而是 **结构合法但语义失真的研究数据被成功 promotion 成正式 canonical dataset**。

### Testing Strategy
1. **Unit tests**
   - schema validator 继续覆盖字段级规则
   - dataset-level semantic validator 必须覆盖所有定量阈值判断
2. **ETL integration tests**
   - 模拟 premium/ST/redemption 缺失或塌缩，验证 fail-fast
   - 模拟正常候选数据，验证 promotion 成功
3. **Promotion / rollback tests**
   - 验证 `.tmp -> canonical` 原子替换
   - 验证中途失败时 `.bak` 恢复
4. **CLI integration tests**
   - 验证 `main_runner.py` 默认路径切换
5. **Docs gate tests**
   - 验证 Phase 2 blocker 文案存在

### Mocking Guidance
- 上游 JQData 调用可以 mock，用于构造异常覆盖率 / 缺失字段场景
- 但 semantic validator 的核心断言必须对真实 DataFrame / CSV 执行
- 不允许只做 schema happy-path 测试

### Quality Goal
收口标准不是“ETL 还能继续出文件”，而是：
- **AMS 不能再 silently 产出错误的 CB research/backtest dataset。**

## 6. Framework Modifications (框架防篡改声明)
- `main_runner.py`
- `etl/jqdata_sync_cb.py`
- `ams/validators/cb_data_validator.py`
- 新增 dataset-level semantic validator / metrics helper（如需要）
- `docs/ROADMAP.md`
- `docs/architecture/ARCHITECTURE.md`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 问题最初被理解为“去掉 mock 数据”，焦点主要落在字段补齐。
- **v1.1**: 讨论后确认 1142 的问题本体是 research/backtest dataset，而不是 golden dataset。
- **v1.2**: Auditor reject，指出 canonical path 双轨并存、semantic gate 缺少定量合同、promotion/rollback 不够写死。
- **v1.3**: 本版收紧为唯一 canonical path、唯一 baseline、唯一 promotion/rollback 合同，并写死全部关键 semantic gate 阈值。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **Unique canonical research dataset path**:
```text
/root/projects/AMS/data/cb_history_factors.csv
```

- **Legacy path that must not remain the default formal research source**:
```text
/root/.openclaw/workspace/data/cb_history_factors.csv
```

- **Canonical metrics baseline path**:
```text
/root/projects/AMS/data/cb_history_factors.metrics.json
```

- **Candidate CSV path**:
```text
/root/projects/AMS/data/cb_history_factors.csv.tmp
```

- **Candidate metrics path**:
```text
/root/projects/AMS/data/cb_history_factors.metrics.json.tmp
```

- **Backup CSV path**:
```text
/root/projects/AMS/data/cb_history_factors.csv.bak
```

- **Backup metrics path**:
```text
/root/projects/AMS/data/cb_history_factors.metrics.json.bak
```

- **Semantic gate thresholds**:
```json
{
  "row_count_min": 50000,
  "underlying_ticker_nonnull_ratio_min": 0.99,
  "premium_rate_nonzero_ratio_min": 0.95,
  "premium_rate_zero_ratio_max": 0.05,
  "is_st_true_count_min": 1,
  "is_redeemed_true_count_min": 1,
  "row_count_drop_ratio_max": 0.20,
  "premium_rate_nonzero_ratio_drop_max": 0.10
}
```

- **Phase 2 blocker statement**:
```text
ISSUE-1142 is a blocking issue for AMS Phase 2. AMS must not enter Live QMT Integration until /root/projects/AMS/data/cb_history_factors.csv is the unique canonical CB research/backtest dataset and the semantic quality gates defined in this PRD are enforced.
```

- **Semantic validation failure messages**:
```text
[DataSemanticViolation] premium_rate_nonzero_ratio below minimum threshold.
[DataSemanticViolation] is_st_true_count below minimum threshold.
[DataSemanticViolation] is_redeemed_true_count below minimum threshold.
[DataSemanticViolation] row_count below minimum threshold.
[DataSemanticViolation] candidate dataset collapsed into default-value world.
[DataDriftViolation] candidate dataset drift exceeded baseline guardrail.
[DataPromotionBlocked] Candidate research dataset failed validation. Canonical dataset remains unchanged.
[DataPromotionRollback] Atomic promotion failed. Canonical dataset restored from backup.
```
