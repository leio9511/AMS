status: closed

# PR-001: Implement QMT FastAPI Bridge Server

## 1. Objective
Create the standalone Windows FastAPI server script (`qmt_bridge_server.py`) to expose miniQMT capabilities via REST endpoints.

## 2. Scope & Implementation Details
- Create `qmt_bridge_server.py` in the AMS workspace.
- Initialize a FastAPI application.
- Implement a health check endpoint `/api/health`.
- The server will be manually deployed to the Windows node later.

## 3. TDD & Acceptance Criteria
- Add a pytest unit test `test_qmt_bridge_server.py` using `fastapi.testclient.TestClient`.
- Test that `/api/health` returns status code 200 and expected JSON payload.
- CI must pass.