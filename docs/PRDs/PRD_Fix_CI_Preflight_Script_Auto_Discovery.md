---
Affected_Projects: [AMS]
---

# PRD: Fix CI Preflight Script Auto-Discovery

## 1. Context & Problem (业务背景与核心痛点)
The `preflight.sh` script in the AMS project currently hardcodes the list of Python files to be syntax-checked (`python3 -m py_compile ...`) and the list of test files to be run (`pytest tests/test_...`). When the SDLC agent introduces new modules or test directories (e.g., `windows_bridge/tests/`), `preflight.sh` ignores them, leading to false negatives during CI validation and blocking PR progress. The script needs to be refactored to automatically discover and run all Python files and test suites.

## 2. Requirements & User Stories (需求定义)
- **Goal**: Refactor `preflight.sh` to use dynamic file discovery instead of hardcoded lists. Establish strict project boundaries for test files using `pytest.ini` and architecture documentation.
- **Scope**: 
  - Modifying `/root/.openclaw/workspace/projects/AMS/preflight.sh`
  - Creating `/root/.openclaw/workspace/projects/AMS/pytest.ini`
  - Modifying `/root/.openclaw/workspace/projects/AMS/BEST_PRACTICES.md`
- **Behavior**: 
  - Syntax check: Scan the entire project for all `.py` files (excluding hidden directories or `__pycache__`) and verify syntax.
  - Test runner: Run `pytest` with no arguments, relying entirely on a new `pytest.ini` configuration file to strictly restrict test discovery to the `tests/` and `windows_bridge/tests/` directories.
  - Implement silent-on-success and verbose-on-failure behavior, tracking the number of passed tests.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Target File**: `/root/.openclaw/workspace/projects/AMS/preflight.sh`, `/root/.openclaw/workspace/projects/AMS/pytest.ini`, `/root/.openclaw/workspace/projects/AMS/BEST_PRACTICES.md`
- **Technical Strategy**:
  - Create a `pytest.ini` at the project root to enforce `testpaths = tests windows_bridge/tests`. This provides tool-level strict boundaries.
  - Update `BEST_PRACTICES.md` to document the strict separation of test code and production code, forbidding tests inside `scripts/`, `legacy_prototypes/`, etc.
  - Adopt the `TOTAL_PASSED` tracking pattern from the `leio-sdlc` preflight script.
  - Use `find . -name "*.py" ... -print0 | xargs -0 python3 -m py_compile` for the global syntax check.
  - Use a simple `pytest >> "$LOG_FILE" 2>&1` for unit tests, letting `pytest.ini` handle the discovery constraints.
  - Preserve the log-extracting logic (`grep -iE -A 10 -B 2 ...`) for token optimization during failures.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Preflight success on clean code**
  - **Given** The workspace has clean, bug-free python code and passing tests
  - **When** `./preflight.sh` is executed
  - **Then** It exits with code 0 and reports the total number of test suites passed.

- **Scenario 2: Preflight catches a new test failure in a designated tests directory**
  - **Given** A failing test file is added to a recognized directory like `windows_bridge/tests/test_fail.py`
  - **When** `./preflight.sh` is executed
  - **Then** It automatically discovers the failing test within the valid directory, outputs the failure log segment, and exits with a non-zero code.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Quality Goal**: The script must remain POSIX-compliant bash. Ensure error outputs are cleanly truncated to avoid blowing up the LLM context window.

## 6. Framework Modifications (框架防篡改声明)
- `/root/.openclaw/workspace/projects/AMS/preflight.sh` (Authorized for full rewrite)
- `/root/.openclaw/workspace/projects/AMS/pytest.ini` (Authorized for creation)
- `/root/.openclaw/workspace/projects/AMS/BEST_PRACTICES.md` (Authorized for modification)

## 7. Hardcoded Content (硬编码内容)
### Exact Text Replacements:
- **Bash snippet to be used inside `preflight.sh` for token-optimized failure logging**:
```bash
if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ PREFLIGHT FAILED (Exit Code: $EXIT_CODE)!"
    echo "=== ERROR DETAILS (Extracting relevant logs to save tokens) ==="
    if grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback|❌" "$LOG_FILE" | head -n 50; then
        :
    else
        tail -n 50 "$LOG_FILE"
    fi
    echo "==============================================================="
    echo "Please fix the code above to pass the preflight gate."
    exit $EXIT_CODE
fi
```
- **Bash snippet to be used inside `preflight.sh` for global syntax check**:
```bash
find . -name "*.py" -not -path "*/\.*" -not -path "*/__pycache__/*" -not -path "*/docs/*" -print0 | xargs -0 python3 -m py_compile > "$LOG_FILE" 2>&1
```
- **Content for `pytest.ini`**:
```ini
[pytest]
testpaths =
    tests
    windows_bridge/tests
```