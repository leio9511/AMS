# PR-005: Data Source Integration for Layer 0

## Goal
Find a suitable Python library (e.g., AkShare or Tushare) and write a simple test script to prove it can fetch the required financial data fields for a single stock (e.g., 平安银行).

## Scope
- `AMS/scripts/test_data_source.py`

## Contracts
- The script must use either `akshare` or `tushare` (preferably `akshare` as it does not strictly require paid tokens for basic data).
- The script must define a function or main block that targets a single stock symbol (e.g., `000001` or `sz000001` for Ping An Bank).
- The script must attempt to fetch the fields defined in Layer 0: YTD Return, PE/PB History, Forward PE, Net Profit Growth Forecast, Balance Sheet metrics (Current Ratio, Debt-to-Asset), Cash Flow metrics (Operating Cash Flow), and Industry classification.
- Output MUST be a simple print to stdout showing the fetched data structure/dictionary for the single stock.

## Acceptance Criteria (AC)
1. The script `AMS/scripts/test_data_source.py` exists and is executable.
2. Running the script successfully prints out the required financial data fields (or as many as the library provides) for the target stock without crashing.
3. The chosen library is clearly documented in the script as the designated Layer 0 data source.

## Anti-Patterns (尸检报告/避坑指南)
- DO NOT attempt to build the full 6-layer funnel in this PR; this is strictly a Layer 0 data acquisition proof-of-concept.
- DO NOT loop through all A-share stocks; strictly limit the test to a single stock to avoid rate limits or long execution times.
- DO NOT hallucinate API methods. Consult the actual documentation of the chosen library (e.g., akshare) to ensure the endpoints exist.