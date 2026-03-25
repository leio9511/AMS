status: closed

# PR-001: Bulk Quote Endpoint and Client Wrapper

## 1. Objective
Add a new `/api/bulk_quote` endpoint to the QMT bridge server and a corresponding `get_full_tick` method to the QMT client to fetch full market tick data.

## 2. Scope & Implementation Details
- **`qmt_bridge_server.py`**: Add `/api/bulk_quote` endpoint. This endpoint will internally call `xtdata.get_full_tick()` and return the raw JSON dictionary.
- **`qmt_client.py`**: Add `get_full_tick()` method to `QMTClient` which sends a request to `/api/bulk_quote`.

## 3. TDD & Acceptance Criteria
- **Test**: Update `tests/test_qmt_client.py` to include a mocked test for `get_full_tick()`.
- **Acceptance Criteria**: The client method successfully returns a mocked JSON dictionary from the bridge server, passing the CI test.
