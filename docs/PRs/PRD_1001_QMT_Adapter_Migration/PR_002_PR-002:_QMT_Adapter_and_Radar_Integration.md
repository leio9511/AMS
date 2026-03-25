status: closed

# PR-002: QMT Adapter and Radar Integration

## 1. Objective
Create an adapter function to map QMT tick data to the legacy AkShare DataFrame format, and update `pilot_stock_radar.py` to use the new `QMTClient` instead of `akshare`.

## 2. Scope & Implementation Details
- **`pilot_stock_radar.py`**: Implement a data adapter function that takes the JSON output of `QMTClient.get_full_tick()` and converts it into a Pandas DataFrame. The output DataFrame must have identical column names (e.g., `代码`, `最新价`, `成交量`, `总市值`, `市盈率-动态`) and types to the legacy `ak.stock_zh_a_spot_em()` output.
- **`pilot_stock_radar.py`**: Replace all calls to `ak.stock_zh_a_spot_em()` and `ak.stock_hk_spot_em()` with `QMTClient.get_full_tick()` piped through the adapter function.

## 3. TDD & Acceptance Criteria
- **Test**: Add a new unit test in `tests/test_data_source.py` (or a dedicated radar test file) that provides a mocked QMT JSON response and asserts that the resulting DataFrame has the correct columns and data types.
- **Acceptance Criteria**: The adapter accurately maps QMT fields to AkShare columns, the radar script executes successfully without `akshare`, and all tests pass.


> [Escalation] Tier 1 Reset triggered due to Coder failure or Arbitrator rejection.
