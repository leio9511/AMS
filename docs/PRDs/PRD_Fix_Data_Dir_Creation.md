---
Affected_Projects: [AMS]
Context_Workdir: /root/projects/AMS
---

# PRD: Fix_Data_Dir_Creation

## 1. Context & Problem (业务背景与核心痛点)
工作区迁移或在新环境克隆代码库后，由于空的 `data` 目录没有被 Git 追踪，直接运行 `preflight.sh` 或测试脚本时，`tests/test_jqdata_sync_cb.py` 内部调用的 `sync_cb_data()` 试图保存文件到 `data/cb_history_factors.csv`。由于父级 `data` 目录不存在，导致抛出 `OSError: Cannot save file into a non-existent directory: 'data'` 异常，进而导致 CI 测试阻断失败。

## 2. Requirements & User Stories (需求定义)
1. 增强本地数据持久化过程的鲁棒性。
2. 即使在没有任何预设数据目录的空白运行环境中，历史数据同步脚本也能自行创建必要的路径，并成功保存数据文件，保证测试和执行流的全绿通过。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
目标模块: `scripts/jqdata_sync_cb.py`。
- 在 `df.to_csv("data/cb_history_factors.csv", index=False)` 之前，增加路径检查和创建的防御性代码。
- 推荐实现方式：提取文件路径，使用 `os.makedirs` (利用 `exist_ok=True` 防止并发创建冲突) 先行创建父级目录，以确保后续持久化操作的安全性。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1:** 在干净无数据目录的环境下执行数据同步
  - **Given** 运行环境的工作目录下不存在 `data` 文件夹
  - **When** 运行或测试 `scripts/jqdata_sync_cb.py` 中的同步逻辑
  - **Then** 程序将自动创建 `data` 文件夹，并成功生成 `.csv` 文件，且不再抛出 `OSError` 异常。
  - **Then** 执行 `bash preflight.sh` 能够全绿通过。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **核心质量风险**：路径构建代码如果写死可能在跨平台下引发问题，需要利用 Python 内置的 `os.path` 库进行安全构建。
- **测试验证**：当前 `tests/test_jqdata_sync_cb.py` 已包含测试流。只需验证原先失败的 `preflight.sh` 能否在移除了 `data` 目录之后恢复通过状态（全绿）。

## 6. Framework Modifications (框架防篡改声明)
- 无框架修改。仅修改业务脚本 `scripts/jqdata_sync_cb.py`。

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: 初始方案，为 `jqdata_sync_cb.py` 加入目录创建容错机制。

---

## 7. Hardcoded Content (硬编码内容)
None
