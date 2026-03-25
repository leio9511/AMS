status: closed

# PR-002: Merge Hybrid Data & Remove Stubs

## 1. Objective
Remove the malicious hardcoded `df_a["市盈率-动态"] = 15.0` stub and integrate the real-time QMT tick data with the authentic fundamental data.

## 2. Scope & Implementation Details
- Edit `pilot_stock_radar.py` and/or `adapter.py` to remove any hardcoded PE or Market Cap assignments.
- Import `fetch_fundamental_data` from `finance_fetcher.py`.
- Implement a `pandas.merge()` operation joining the QMT tick DataFrame and the fundamental DataFrame on the `代码` column.
- Ensure the downstream radar filtering logic uses the authentic, merged `市盈率-动态` and `总市值`.

## 3. TDD & Acceptance Criteria
- Edit `tests/test_data_source.py` to assert that the final DataFrame used by the radar contains distinct, dynamic PE values.
- Verify that the test explicitly fails if a hardcoded `15.0` stub is reintroduced.
- `pilot_stock_radar.py` must execute successfully and output stocks filtered by real valuations.
