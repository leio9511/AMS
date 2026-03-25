# PRD-1009: AMS Architecture Standardization & Import Cleanup

## 1. Problem Statement
The AMS module currently suffers from structural and import logic chaos, particularly surrounding `qmt_client.py` and `test_qmt_client.py`.
There is duplication of the `qmt_client.py` file (in root `AMS/` and `AMS/scripts/`), which causes Coder agents to face impossible "ghost" tasks due to path ambiguity. The `test_qmt_client.py` file has messy implicit import structures (`from qmt_client ...` vs `from scripts.qmt_client ...`), breaking CI/CD tests and confusing LLMs executing TDD.

## 2. Objective
1. Clean up duplicate files and establish a single source of truth for `qmt_client.py` within the `AMS` project.
2. Refactor `test_qmt_client.py` to use correct, absolute/relative Python import paths (e.g., adding parent directories to `sys.path` cleanly, or converting to an installable package).
3. Generate a `README.md` (or `BEST_PRACTICES.md`) at the root of `AMS/` documenting the correct directory structure and import standards, ensuring future LLM modifications do not clutter the project.

## 3. Scope of Work
- **File De-duplication**: Analyze the two `qmt_client.py` files. Keep the most up-to-date version (likely `AMS/scripts/qmt_client.py`) and delete any redundant legacy versions at the `AMS/` root.
- **Import Refactoring**: Modify `AMS/tests/test_qmt_client.py` and any other scripts (like `pilot_stock_radar.py`) to import `QMTClient` using a unified and clean standard path. Ensure tests run successfully without any `ImportError`.
- **Documentation**: Create `AMS/BEST_PRACTICES.md` (or `AMS/README.md`) outlining:
  - The purpose of `scripts/` vs `tests/`.
  - The standard way to import internal modules (e.g., `from scripts.module import Class` with proper `__init__.py` behavior).
  - A strict rule preventing files from being dumped in the root of `AMS/` without justification.

## 4. TDD & Acceptance Criteria
- `pytest AMS/tests/test_qmt_client.py` runs and passes successfully.
- `ls AMS/qmt_client.py` should return `No such file or directory` (only the `scripts/` version should exist).
- `AMS/README.md` or `AMS/BEST_PRACTICES.md` must be created and populated with clear structural rules.