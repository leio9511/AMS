# PRD: AMS Core Engine & Legacy Archive (ISSUE-1102)

## 1. Overview
Restructure the AMS project directory and implement the core `EventEngine` to transition from procedural scripts to an event-driven architecture.

## 2. Goals
- Restructure directories for EDA.
- Implement a stateless `EventEngine` for decoupling data providers from strategies.
- Archive legacy scripts to `legacy_scripts/`.

## 3. Scope
- **Files to create**: `engine/event_engine.py`, `engine/__init__.py`.
- **Files to move**: Move all `*.py` in root (except `main_runner.py`, `deploy_to_windows.py`, `verify_*\.py`) to `legacy_scripts/`.
- **Affected_Projects**: [AMS]

## 4. Technical Requirements
- `EventEngine` must support `register`, `unregister`, and `put` (emit) events.
- Thread-safe event queue.
- No heavy dependencies.

## 5. Rollback Plan
- Use `git checkout master` or the latest stable commit hash recorded in `STATE.md`.
- `deploy.sh` backups previous versions before installation.

## 6. Parameter Storage
- Configuration parameters (if any) should reside in `config/ams_config.json`.

## 7. Hardcoded Content
- None permitted.

## 8. CI/CD
- Must pass `preflight.sh`.
