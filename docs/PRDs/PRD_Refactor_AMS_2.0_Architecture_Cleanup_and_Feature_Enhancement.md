---
Affected_Projects: [AMS]
Related_Issue: ISSUE-1160
---

# PRD: Refactor: AMS 2.0 Architecture Cleanup and Governance Alignment (Standardized)

## 1. Context & Problem
AMS 2.0 requires a clear separation between core logic, data production, and legacy tools. Current debt:
1.  **Structural Coupling**: Core 2.0 ETL scripts are mixed with legacy 1.0 files in `scripts/`.
2.  **Governance Confusion**: `SKILL.md` lacks explicit path resolution directives for the `DEVELOPMENT` stage.
3.  **Deployment Gap**: `deploy.sh` is not aligned with the refined 2.0 directory structure.

## 2. Requirements & User Stories

### Epic 1: Architecture Stratification
*   **US 1.1**: Establish `/root/projects/AMS/etl/` as the official domain for data production.
*   **US 1.2**: Relocate `scripts/jqdata_sync_cb.py` and `scripts/trigger_daily_etl.py` to `etl/`.
*   **US 1.3**: Update all associated test imports and documentation.

### Epic 2: Governance Alignment
*   **US 2.1**: Update the source `SKILL.md` to explicitly enforce workspace pathing during `DEVELOPMENT`.
*   **US 2.2**: Update `deploy.sh` to synchronize the `etl/` directory.

## 3. Architecture & Technical Strategy
*   **File Migration**: Use `git mv` to move `scripts/jqdata_sync_cb.py` and `scripts/trigger_daily_etl.py` to the new `etl/` directory.
*   **Import Fixes**: 
    - Update `tests/test_jqdata_sync_cb.py`, `tests/test_jqdata_sync_cb_logic.py`, `tests/test_jqdata_sync_cb_io.py` to import from `etl.jqdata_sync_cb`.
    - Update `tests/test_trigger_daily_etl.py` to import from `etl.trigger_daily_etl`.
*   **Rollback Strategy**: 
    1. **Git Level**: Any failure during SDLC allows for `git reset --hard` to the baseline commit.
    2. **Deployment Level**: `deploy.sh` already creates a timestamped tarball in `~/.openclaw/skills/ams_backups/`. If the runtime breaks, manual extraction of the latest backup to `~/.openclaw/skills/ams/` is required.

## 4. Acceptance Criteria
*   **AC 1**: ETL scripts exist in `etl/` and are absent from `scripts/`.
*   **AC 2**: Deployed `SKILL.md` contains the development-stage workspace pathing directive.
*   **AC 3**: All associated tests in `tests/` pass with updated import paths.

## 5. Overall Test Strategy & Quality Goal
*   **Import Audit**: Run `pytest tests/test_jqdata_sync_cb.py tests/test_jqdata_sync_cb_logic.py tests/test_jqdata_sync_cb_io.py tests/test_trigger_daily_etl.py` to ensure import resolution.
*   **Deployment Smoke Test**: Execute `./deploy.sh` and verify the physical presence of the `etl/` directory in the runtime environment.

## 6. Framework Modifications
- `/root/projects/AMS/scripts/jqdata_sync_cb.py` (Move)
- `/root/projects/AMS/scripts/trigger_daily_etl.py` (Move)
- `/root/projects/AMS/tests/test_jqdata_sync_cb.py` (Modify imports)
- `/root/projects/AMS/tests/test_jqdata_sync_cb_logic.py` (Modify imports)
- `/root/projects/AMS/tests/test_jqdata_sync_cb_io.py` (Modify imports)
- `/root/projects/AMS/tests/test_trigger_daily_etl.py` (Modify imports)
- `/root/projects/AMS/README.md` (Modify)
- `/root/projects/AMS/docs/architecture/ARCHITECTURE.md` (Modify)
- `/root/projects/AMS/SKILL.md` (Modify)
- `/root/projects/AMS/deploy.sh` (Modify)

## 7. Hardcoded Content (Anti-Hallucination)

### README.md Project Structure:
```markdown
## Project Structure
- `ams/`: Core Strategy, Runner, and Broker logic (Event-Driven).
- `etl/`: Data acquisition and processing pipelines (Production).
- `data/`: Standardized CSV datasets.
- `scripts/`: Legacy 1.0 scripts and experimental tools (Deprecated).
```

### SKILL.md Governance:
```markdown
# AMS Runbook & Governance
**MANDATORY:** Currently in DEVELOPMENT stage. All invocations MUST use the workspace path: `/root/projects/AMS/`. DO NOT use runtime paths until the stage is switched to PRODUCTION.
```

### deploy.sh Update (rsync section):
```bash
rsync -avh --delete "$SRC_DIR/ams/" "$DEST_SKILL_DIR/ams/"
rsync -avh --delete "$SRC_DIR/etl/" "$DEST_SKILL_DIR/etl/"
cp "$SRC_DIR/SKILL.md" "$DEST_SKILL_DIR/SKILL.md"
```
