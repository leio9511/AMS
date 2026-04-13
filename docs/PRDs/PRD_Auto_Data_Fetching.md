---
Affected_Projects: [AMS]
---

# PRD: Auto Data Fetching & One-time Bootstrap

## 1. Context & Problem (业务背景与核心痛点)
Currently, AMS relies on manual data downloads in the QMT graphical client. When running MiniQMT (headless mode), there is no GUI to click "Download Data." Without up-to-date local data in QMT's `datadir`, AMS cannot accurately calculate fundamental indicators (like PE, PB) and cannot recognize new instrument codes. We need a one-time bootstrap script to initialize a new machine, and a daily automated sync mechanism before the market opens (08:05 AM) to keep the data fresh.

## 2. Requirements & User Stories (需求定义)
- **Goal 1 (Daily Sync)**: The system must automatically download the latest sector definitions and financial data (Capital, Balance, Income) every trading day at 08:05 AM, and then execute the ETL pipeline to update `fundamentals.json`.
- **Goal 2 (Bootstrap)**: The system must provide a one-time execution script to fetch all historical data (K-lines, ticks, financials) necessary for AMS operations on a completely fresh Windows QMT node.
- **Scope**:
  - `windows_bridge/bootstrap_data.py` (New: One-time init)
  - `windows_bridge/daily_sync.py` (New: Daily incremental fetch)
  - `scripts/trigger_daily_etl.py` (New: Local OpenClaw script to trigger SSH execution)
  - `deploy.sh` (Update: Register the 08:05 AM cron job)

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Windows Side (Data Fetchers)**:
  - We will create `bootstrap_data.py` which uses `xtquant.xtdata` to download full history (sector data, financial data for A-shares, ETFs, CBs).
  - We will create `daily_sync.py` to trigger `download_sector_data()` and `download_financial_data()` asynchronously. Since `xtquant` downloads in the background and lacks a synchronous callback for financial data, the script will use a robust **Polling with Timeout** mechanism (e.g., monitoring the `datadir` for file modification timestamps or size stabilization over a few seconds, with a maximum timeout) instead of a blind `time.sleep()`.
- **Linux Side (OpenClaw Orchestration)**:
  - We will add `trigger_daily_etl.py` locally in OpenClaw. This script uses `paramiko` to SSH into the Windows node, run `daily_sync.py` remotely, and immediately followed by executing `finance_batch_etl.py` **remotely on the Windows node** (e.g., `python C:\Users\Administrator\Desktop\AMS\finance_batch_etl.py`) to rebuild the `fundamentals.json` file. Do NOT run the ETL script locally on Linux.
- **Scheduling**:
  - `deploy.sh` will be updated to register an OpenClaw cron job named `ams_daily_data_sync` running at `5 8 * * 1-5`. It will use the exact same `jq` + `for` loop idempotent logic we established in ISSUE-1110.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: One-time Bootstrap Execution**
  - **Given** A fresh Windows QMT node with no downloaded data
  - **When** `python bootstrap_data.py` is executed
  - **Then** `xtdata` downloads sector and financial data without crashing, preparing the `datadir` for queries.

- **Scenario 2: Daily Cron Job Registration**
  - **Given** OpenClaw environment
  - **When** `deploy.sh` is executed
  - **Then** Exactly one `ams_daily_data_sync` job is registered at `5 8 * * 1-5`, and old duplicates are removed.

- **Scenario 3: Daily ETL Trigger Execution**
  - **Given** The OpenClaw scheduler triggers `trigger_daily_etl.py`
  - **When** The script runs
  - **Then** It successfully connects to Windows via SSH, runs `daily_sync.py` remotely, executes `finance_batch_etl.py` remotely on the Windows node, and logs the completion.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Test Strategy**:
  - Create a test script (`test_trigger_daily_etl.py`) or manually run `trigger_daily_etl.py` locally to verify the SSH execution flow.
  - Assert that `deploy.sh` successfully registers the new cron job idempotently.
- **Quality Goal**: Ensure robust SSH exception handling. Strictly avoid blind `time.sleep()` for I/O waits; use deterministic polling (e.g., file state or `xtdata` polling) on the Windows side to wait for async C++ downloads to finish before ETL starts.

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
### Exact Text Replacements:
- **Bash snippet to be injected into `deploy.sh` for the new cron job**:
```bash
# Register daily data sync & ETL cron job
EXISTING_SYNC_IDS=$(openclaw cron list --json | jq -r '.jobs[] | select(.name == "ams_daily_data_sync") | .id')
for JOB_ID in $EXISTING_SYNC_IDS; do
    if [ -n "$JOB_ID" ]; then
        echo "Removing existing ams_daily_data_sync cron job: $JOB_ID"
        openclaw cron rm "$JOB_ID"
    fi
done

echo "Registering ams_daily_data_sync cron job..."
openclaw cron add --name "ams_daily_data_sync" --cron "5 8 * * 1-5" --message "Execute \`python3 ~/.openclaw/skills/ams/scripts/trigger_daily_etl.py\`. Parse the JSON output and report the data sync status to the Boss."
```