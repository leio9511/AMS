---
Affected_Projects: [AMS]
---

# PRD: Fix Duplicate Cron Job Registration in deploy.sh

## 1. Context & Problem (业务背景与核心痛点)
The `deploy.sh` script for the AMS project uses the `openclaw cron add --name "ams_ledger_backup"` command to register a disaster recovery cron job. However, the OpenClaw CLI generates a new UUID for each invocation, even if the name is identical. This causes duplicate cron jobs to stack up every time a deployment is triggered, resulting in redundant execution of the ledger backup script.

## 2. Requirements & User Stories (需求定义)
- **Goal**: Ensure that executing `deploy.sh` is idempotent regarding the cron job registration.
- **Scope**: Modify `/root/.openclaw/workspace/projects/AMS/deploy.sh` ONLY.
- **Behavior**: 
  - Before calling `openclaw cron add`, the script must query the OpenClaw CLI for existing cron jobs.
  - If a job named `ams_ledger_backup` exists, its UUID must be extracted and removed via `openclaw cron rm <UUID>`.
  - After cleanup (or if no such job exists), the script registers the new cron job.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Target File**: `/root/.openclaw/workspace/projects/AMS/deploy.sh`
- **Technical Strategy**:
  - We will use Bash shell scripting commands to fetch the JSON list of cron jobs.
  - We will parse the JSON string using `jq` to extract the ID of the `ams_ledger_backup` cron job safely and robustly.
  - We will remove the existing job if found, then proceed with the original cron addition logic.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1:** Registering cron job when no duplicate exists
  - **Given** The cron schedule currently does NOT have any job named `ams_ledger_backup`
  - **When** `deploy.sh` is executed
  - **Then** Exactly one `ams_ledger_backup` job should be created without any `openclaw cron rm` errors.

- **Scenario 2:** Registering cron job when a duplicate exists
  - **Given** The cron schedule already has one or more jobs named `ams_ledger_backup`
  - **When** `deploy.sh` is executed
  - **Then** The existing job(s) should be detected and removed, and exactly one new `ams_ledger_backup` job should remain.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Verification Strategy**:
  - The Coder must write a shell-based integration test or verify the behavior by directly executing `deploy.sh` multiple times locally.
  - The test should verify idempotency: running `deploy.sh` three times consecutively should still result in exactly 1 active `ams_ledger_backup` cron job.
- **Quality Goal**: Shell script syntax is correct, handles empty JSON returns gracefully, and uses robust JSON parsing (`jq`).

## 6. Framework Modifications (框架防篡改声明)
- None.

## 7. Hardcoded Content (硬编码内容)
### Exact Text Replacements:
- **Bash snippet to be injected into `deploy.sh` before the cron add command**:
```bash
# Remove ALL existing jobs with the same name to prevent duplicates
EXISTING_JOB_IDS=$(openclaw cron list --json | jq -r '.jobs[] | select(.name == "ams_ledger_backup") | .id')
for JOB_ID in $EXISTING_JOB_IDS; do
    if [ -n "$JOB_ID" ]; then
        echo "Removing existing ams_ledger_backup cron job: $JOB_ID"
        openclaw cron rm "$JOB_ID"
    fi
done
```