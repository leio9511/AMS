# PR-007: Implement Crystal Fly Swatter

## Goal
Implement the full 6-layer "Crystal Fly Swatter" filtering funnel for A-share financial data.

## Scope
- `AMS/scripts/crystal_fly_swatter.py`

## Acceptance Criteria (AC)
1. The script `AMS/scripts/crystal_fly_swatter.py` implements the full 6-layer funnel logic.
2. The script explicitly uses the following `akshare` functions discovered during the spike (PR-006):
   - `ak.stock_individual_info_em` (Layer 1: Industry Classification)
   - `ak.stock_zh_a_hist` (Layer 2: YTD Return & PE/PB History)
   - `ak.stock_profit_forecast_ths` (Layer 3: Forward PE & Profit Growth)
   - `ak.stock_financial_abstract_ths` (Layers 4 & 5: Balance Sheet metrics)
   - `ak.stock_financial_cash_ths` (Layers 4 & 5: Cash Flow metrics)
3. CRITICAL: The `ak.stock_profit_forecast_ths` API is known to hang/timeout. The Coder MUST implement strict timeouts and retries for all network calls, or process data in small, robust batches to prevent CI failures.
4. The script successfully executes and produces the filtered list of stocks without hanging indefinitely.

## Anti-Patterns (尸检报告/避坑指南)
- DO NOT use shell commands (e.g., `exec` with `echo`, `cat`, `sed`, `awk`) to read, create, or modify file contents. The Coder MUST adhere to the MANDATORY FILE I/O POLICY and use the native `read`, `write`, and `edit` tools for all file operations.
- DO NOT ignore network timeouts. Unbounded API calls (especially to `ak.stock_profit_forecast_ths`) will cause CI failures. Always wrap network calls with strict timeout and retry logic.