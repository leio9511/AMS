status: closed

# PR-001: Implement Fundamental Data Fetcher

## 1. Objective
Create a reliable fundamental data fetcher to retrieve authentic PE-TTM (`市盈率-动态`) and Total Market Cap (`总市值`) for A-shares using AKShare, replacing the need for hardcoded stubs.

## 2. Scope & Implementation Details
- Create `finance_fetcher.py` in `/root/.openclaw/workspace/AMS`.
- Implement `fetch_fundamental_data()` using `akshare.stock_a_indicator_lg()` or a similar robust AKShare endpoint.
- Ensure the returned DataFrame contains '代码' (Stock Code), '市盈率-动态', and '总市值'.
- Add basic caching or error handling to mitigate network instability.

## 3. TDD & Acceptance Criteria
- Create `tests/test_finance_fetcher.py`.
- Write a test asserting `fetch_fundamental_data()` returns a DataFrame with the required columns.
- Write a test asserting that the '市盈率-动态' values are NOT all identical (e.g., `len(df['市盈率-动态'].unique()) > 1`), proving the data is authentic and not a hardcoded stub.
