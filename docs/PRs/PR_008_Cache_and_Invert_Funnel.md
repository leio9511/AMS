# PR-008: Cache-Enhanced Inverted Funnel

## Goal
Transform the "Crystal Fly Swatter" script into an industrial-grade data pipeline using an Inverted Funnel (Fast filters first) and Multi-Tier Caching.

## Scope
- `AMS/scripts/crystal_fly_swatter.py`
- `AMS/cache/` (New directory)

## Phase 1: Fast/Static Filter (Batch Operations)
Coder must implement logic to filter the bulk of stocks BEFORE any expensive API calls:
1. **Industry Gate**: Use cached `cache/industry_map.json`. (Layer 5 logic).
2. **Financial Health Gate**: Use `cache/financials.json` with a 30-day TTL. (Layer 2 logic).
3. **Contrarian Drop Gate**: Use a single bulk spot market API call for YTD return calculation. (Layer 4 logic).

## Phase 2: Slow/Dynamic Filter (Point Operations)
Only surviving stocks (<500) proceed to these gates:
1. **Valuation Percentile Gate**: Use `cache/pe_history/<stock_code>.csv` with a 7-day TTL. (Layer 3 logic).
2. **Forward Profit Gate**: Real-time fetch via `ak.stock_profit_forecast_ths` with strict timeouts/retries. (Layer 1 & 3 logic).

## Acceptance Criteria
1. The script `scripts/crystal_fly_swatter.py` correctly handles cache misses (re-fetching) and expired TTLs.
2. The `cache/` directory is automatically created if missing.
3. The funnel order is strictly followed: Phase 1 (Batch) -> Phase 2 (Point).
4. The script is tested against a large proxy list to verify that >90% of stocks are dropped in Phase 1 without calling Phase 2 APIs.

## MANDATORY FILE I/O POLICY
- DO NOT use shell commands (`echo`, `cat`, `sed`, `awk`) to read, create, or modify file contents.
- Use ONLY native `read`, `write`, and `edit` tools for all file operations.
- Ensure all cache JSON/CSV structures are valid and handled with standard libraries.