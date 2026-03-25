status: completed

# PR-002: Implement QMTClient for Linux AMS Core

## 1. Objective
Refactor the AMS engine to replace legacy data fetchers with a new `QMTClient` class that queries the Windows FastAPI bridge.

## 2. Scope & Implementation Details
- Create `qmt_client.py` on the Linux node.
- Create a `QMTClient` class.
- Implement methods that make HTTP requests to the Windows bridge IP (`43.134.76.215:8000`).
- Ensure it communicates cleanly.

## 3. TDD & Acceptance Criteria
- Add `test_qmt_client.py`.
- Use `responses` or `unittest.mock` to mock the FastAPI server's JSON responses (no real network connection).
- The test must verify that `QMTClient` sends requests with correct parameters and handles the mocked responses appropriately.
- CI must pass.