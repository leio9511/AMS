---
Affected_Projects: [AMS]
Related_Issue: ISSUE-1165
---

# PRD: Modernize AMS Deployment Script and Fix Models Sync (v8 - Final)

## 1. Context & Problem
AMS 2.0 deployment is currently brittle and non-atomic. Hardcoded paths caused missing packages, and current error handling is insufficient for high-availability production. We must adopt an industrial-grade "Resilient Atomic Swap" pattern.

## 2. Requirements & User Stories
1.  **US 1 (Comprehensive Sync)**: Use `.release_ignore` for inclusive rsync.
2.  **US 2 (True Atomic Swap)**: Implementation must ensure that the target directory is either 100% updated or 100% restored to the previous state.
3.  **US 3 (Pre-flight Guardrail)**: Stop if a prior `.old` directory exists to protect the last known good backup.
4.  **US 4 (Fault Tolerance)**: Use a `trap` mechanism to automate restoration if the swap fails mid-process.

## 3. Architecture & Technical Strategy
*   **Safety Policy**: `set -euo pipefail`.
*   **Error Recovery**: Define an `on_error` function triggered by `trap ERR`. It must verify if the target directory is missing and the `.old` exists, then `mv` it back to restore service.
*   **Lifecycle**:
    1. Pre-check: Ensure no stale `.old` directory exists.
    2. Staging: Sync to `.tmp` using absolute path exclusion rules.
    3. Backup: Create tarball from live.
    4. Swap Start: Move live to `.old`.
    5. Swap End: Move staged to live.
    6. Finalize: Remove `.old`.

## 4. Acceptance Criteria
*   **AC 1**: Deployment successfully syncs `ams/models/` without manual path listing.
*   **AC 2**: If the final `mv` fails, the script automatically restores the previous production directory from the `.old` state.
*   **AC 3**: Tarball backup is always created before any directory removal.

## 5. Overall Test Strategy & Quality Goal
*   **Verification**: Execute deployment and confirm `~/.openclaw/skills/ams/models/config.py` exists.

## 6. Framework Modifications
- `/root/projects/AMS/deploy.sh` (Refactor)
- `/root/projects/AMS/.release_ignore` (New)

## 7. Hardcoded Content (Anti-Hallucination)

### Final .release_ignore:
```text
.git/
.gitignore
.pytest_cache/
tests/
__pycache__/
*.pyc
*.log
docs/PRDs/
.sdlc_runs/
run_backtest_script.py
turnover_test.py
run_precision_backtest.py
debug_trace*.py
append_experience.py
update_issue_exp.py
run_commit.py
```

### Resilient Atomic Implementation for deploy.sh:
```bash
set -euo pipefail

TMP_DIR="${DEST_SKILL_DIR}.tmp"
OLD_DIR="${DEST_SKILL_DIR}.old"

on_error() {
    echo "CRITICAL: Deployment failed. Initiating automated recovery..."
    if [ ! -d "$DEST_SKILL_DIR" ] && [ -d "$OLD_DIR" ]; then
        mv "$OLD_DIR" "$DEST_SKILL_DIR"
        echo "RESTORED: Production directory recovered from backup."
    fi
}
trap on_error ERR

# 1. Validation
if [ -d "$OLD_DIR" ]; then
    echo "FATAL: Stale backup directory found at $OLD_DIR. Recover manually."
    exit 1
fi

# 2. Staging
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"
rsync -avh --delete --exclude-from="$SRC_DIR/.release_ignore" "$SRC_DIR/" "$TMP_DIR/"

# 3. Swap and Backup
if [ -d "$DEST_SKILL_DIR" ]; then
    BACKUP_FILE="${BACKUP_DIR}/ams_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
    tar -czf "$BACKUP_FILE" -C "$(dirname "$DEST_SKILL_DIR")" "$(basename "$DEST_SKILL_DIR")"
    mv "$DEST_SKILL_DIR" "$OLD_DIR"
fi

mv "$TMP_DIR" "$DEST_SKILL_DIR"
rm -rf "$OLD_DIR"
```
