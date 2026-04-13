---
Affected_Projects: [AMS]
---

# PRD: Hotfix Auto Data Fetching Deployment

## 1. Context & Problem (业务背景与核心痛点)
The Auto Data Fetching feature (ISSUE-1114) correctly implemented the `daily_sync.py` and `bootstrap_data.py` scripts on the Linux side, but failed to update the deployment script `deploy_to_windows.py`. As a result, the new scripts are never uploaded to the Windows QMT node, leading to execution failures during the cron job (`File Not Found`). 
Additionally, the deployment script `deploy_to_windows.py` still uses relative paths and lacks the correct encoding handling for Windows WMI commands as discovered in a previous session (MEMORY.md). Finally, there is an inconsistency in fallback paths between `bootstrap_data.py` and `daily_sync.py` that needs to be unified.

## 2. Requirements & User Stories (需求定义)
- **Goal 1**: Update `deploy_to_windows.py` to upload the newly created `windows_bridge/daily_sync.py` and `windows_bridge/bootstrap_data.py` scripts to the Windows node.
- **Goal 2**: Refactor `deploy_to_windows.py` to use absolute paths based on `__file__` (to handle executions from different CWDs) and add `decode(errors='ignore')` for robustly handling WMI command outputs, as mandated by the `MEMORY.md` global rules.
- **Goal 3**: Unify the fallback paths for `xtdata` in `bootstrap_data.py` and `daily_sync.py` to a consistent directory (e.g., `C:\qmt\userdata_mini\datadir`).

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Deployment Script Fix**: Modify `deploy_to_windows.py`. Use `os.path.abspath(os.path.dirname(__file__))` to construct the absolute paths for the local files (`daily_sync.py`, `bootstrap_data.py`, `finance_batch_etl.py`, `server.py`). Add `daily_sync.py` and `bootstrap_data.py` to the SFTP upload loop. 
- **WMI Encoding Fix**: Change `stderr.read().decode().strip()` to `stderr.read().decode('gbk', errors='ignore').strip()` (or similar tolerant decoding) in `deploy_to_windows.py` to prevent `UnicodeDecodeError`.
- **Fallback Path Alignment**: Inspect `bootstrap_data.py` and `daily_sync.py`. Ensure that if `xtdata` datadir isn't found, both fallback to the exact same directory (`C:\qmt\userdata_mini\datadir`).

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Deployment completeness**
  - **Given** The updated `deploy_to_windows.py` script
  - **When** The script is executed
  - **Then** It successfully uploads `server.py`, `finance_batch_etl.py`, `daily_sync.py`, and `bootstrap_data.py` to the target Windows node.
- **Scenario 2: Absolute Path Execution**
  - **Given** The user is in an arbitrary directory (e.g. `/tmp`)
  - **When** Executing `python /root/.openclaw/workspace/projects/AMS/deploy_to_windows.py`
  - **Then** The script finds all source files without throwing `FileNotFoundError`.
- **Scenario 3: Fallback path consistency**
  - **Given** The Windows node lacks a properly configured `xtdata.data_dir` attribute
  - **When** Running either `daily_sync.py` or `bootstrap_data.py`
  - **Then** Both scripts attempt to fallback to identical `C:\qmt\userdata_mini\datadir` paths.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Test Strategy**: 
  - Execute `deploy_to_windows.py` locally and verify the logs show the upload of all 4 scripts. 
  - Verify that no `UnicodeDecodeError` is thrown during WMI command execution.
- **Quality Goal**: Ensure idempotent, robust deployment aligned with global `MEMORY.md` best practices.

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
- **Fallback Directory**: `C:\qmt\userdata_mini\datadir`