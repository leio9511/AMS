---
Affected_Projects: [AMS]
---

# PRD: Phase4_CI_CD_Topology_and_Agent_Integration

## 1. Context & Problem (业务背景与核心痛点)
ISSUE-1105. This is the final phase of the AMS v2.0 Epic. We have a robust EventEngine (Phase 1), a Windows-based Pre-market ETL script (Phase 2), and clean strategy implementations (Phase 3). However, the system is entirely manual. The Windows scripts (`finance_batch_etl.py` and `server.py`) still require manual copying to the Windows node. Furthermore, the Linux agent side (strategies and engine) needs to be formally integrated into the OpenClaw Agent runtime so that it can be triggered automatically via OpenClaw's `HEARTBEAT.md` (for low-frequency summaries) and system cron/background jobs (for high-frequency market hours monitoring).

## 2. Requirements & User Stories (需求定义)
- **Functional Requirements:**
  - Write a CD deployment script (`deploy_to_windows.py`) that uses `paramiko` to upload `windows_bridge/finance_batch_etl.py` and `windows_bridge/server.py` to the Windows node (`43.134.76.215`), specifically to `C:/Users/Administrator/Desktop/AMS/`.
  - The script must restart the background `server.py` process on Windows automatically.
  - Create a primary Linux runner script `main_runner.py` that initializes the `EventEngine`, the `TickGateway`, instantiates all three strategies (`ETFArbStrategy`, `ConvertibleBondStrategy`, `CrystalFlyStrategy`), calls `start()` on them, and calls `gateway.poll_once(engine)`.
  - Update OpenClaw's `HEARTBEAT.md` (in the global workspace) to include instructions for the Agent to run `main_runner.py` every morning at 09:15 and every afternoon at 15:30 to summarize the output.
- **Non-Functional Requirements:**
  - Idempotent deployment: Running `deploy_to_windows.py` multiple times should safely overwrite and restart without leaving zombie Python processes on Windows.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **CI/CD Layer**:
  - `deploy_to_windows.py` uses `paramiko.SFTPClient` to upload files.
  - Process management on Windows uses WMI: `wmic process where "commandline like '%server.py%' and name='python.exe'" call terminate` to kill old servers, then `wmic process call create ...` to start the new one in the background.
- **Agentic Integration Layer**:
  - `main_runner.py` is a short-lived script. It does NOT contain a `while True` loop. It sets up the strategies, pulls one tick snapshot, processes events, and exits. 
  - To achieve continuous monitoring during market hours, OpenClaw's native `exec` tool with `background: true` or a system-level cron will be used externally. The `HEARTBEAT.md` update provides the LLM instructions on how to interpret the outputs.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Automated Windows Deployment**
  - **Given** modified scripts in `windows_bridge/`
  - **When** `deploy_to_windows.py` is executed
  - **Then** the files are successfully copied to the Windows node and the `server.py` process is restarted without errors.
- **Scenario 2: Main Runner Execution**
  - **Given** the event engine and strategies are in place
  - **When** `main_runner.py` is executed
  - **Then** it successfully instantiates all strategies, calls `start()`, processes one cycle of `gateway.poll_once()`, and exits cleanly with exit code 0.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Mocking Deployment**: Test the `deploy_to_windows.py` using paramiko mocks in `tests/test_deploy_to_windows.py` to ensure correct WMI commands are issued.
- **Runner E2E**: Test `main_runner.py` by mocking the `gateway.poll_once` to ensure it successfully ties the strategies to the engine without actual network calls.

## 6. Framework Modifications (框架防篡改声明)
- `/root/.openclaw/workspace/HEARTBEAT.md` (Global Workspace)

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。

- **Windows Deployment Target Path (For `deploy_to_windows.py`)**:
```python
WINDOWS_TARGET_DIR = 'C:/Users/Administrator/Desktop/AMS'
```

- **Windows Restart Commands (For `deploy_to_windows.py`)**:
```python
KILL_CMD = 'wmic process where "commandline like \'%server.py%\' and name=\'python.exe\'" call terminate'
START_CMD = 'wmic process call create "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe C:\\Users\\Administrator\\Desktop\\AMS\\server.py"'
```

- **Heartbeat Addition (For `/root/.openclaw/workspace/HEARTBEAT.md`)**:
```markdown
## AMS 2.0 Agentic Integration (09:15 AM & 15:30 PM UTC+8)
- **Condition**: If the current time is around 09:15 or 15:30 GMT+8, and the AMS scan hasn't been run for this window.
- **Action**: Execute `python3 /root/.openclaw/workspace/projects/AMS/main_runner.py`. Parse the output signals from the ETF, Convertible Bond, and Crystal Fly strategies, and summarize actionable trading insights for the Boss.
```