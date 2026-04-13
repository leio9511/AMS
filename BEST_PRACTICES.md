# AMS Architecture Best Practices

## 1. Directory Structure
To maintain a clean and scalable architecture, the AMS project strictly divides its core code and testing logic:

* **`scripts/`**: This directory is the single source of truth for all core executable code, modules, and business logic (e.g., `qmt_client.py`).
* **`tests/`**: This directory is dedicated exclusively to test files (e.g., `pytest` suites like `test_qmt_client.py`).

## 2. Import Standards
When importing internal modules, always use explicit paths referencing the `scripts` package to prevent ambiguity and `ImportError` issues.

**Correct Example:**
```python
from scripts.qmt_client import QMTClient
```

**Incorrect Example:**
```python
from qmt_client import QMTClient  # Implicit, ambiguous, breaks when run from different directories
```

## 3. Strict Root Rule
**NO NEW PYTHON IMPLEMENTATION FILES SHALL BE PLACED IN THE ROOT `AMS/` DIRECTORY.** 
All new `.py` files must be placed in `scripts/`, `tests/`, or another designated subdirectory unless there is an explicit, documented justification (e.g., a top-level runner or configuration script that absolutely requires it). This prevents structural chaos and import path collisions.

## 4. Test Boundaries
Strict separation of test code and production code is enforced. Tests must NOT be placed inside directories like `scripts/` or `legacy_prototypes/`. The `pytest.ini` file at the root acts as the source of truth for test boundaries, dynamically restricting test discovery to designated folders (e.g., `tests/`, `windows_bridge/tests/`).
