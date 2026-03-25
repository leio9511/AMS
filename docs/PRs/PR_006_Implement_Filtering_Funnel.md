# PR-006: Spike - Investigate AkShare APIs for Filtering Funnel

## Goal
Perform an API exploration spike to find and verify the exact `akshare` functions and data fields needed to support the 6-layer "Crystal Fly Swatter" filtering funnel. 

**IMPORTANT**: Do NOT implement the full filtering logic. This is strictly a spike to prove that the required data can be fetched and to identify the correct API endpoints.

## Scope
- Create a new test script: `AMS/scripts/spike_akshare_apis.py`

## Requirements for the Coder
1. **Target**: Write a small script (`AMS/scripts/spike_akshare_apis.py`) that uses `akshare` to fetch A-share financial data.
2. **Data Fields to Verify**: You need to find the `akshare` functions that provide data for the 6-layer funnel (as defined in `AMS/docs/PRD_M6_Crystal_Fly_Swatter.md`):
   - YTD Return (今年大跌 / Year-to-Date Return)
   - PE/PB History & Percentile (PE-TTM Historical Percentile)
   - Forward PE (e.g., 2026 forecast PE)
   - Net Profit Growth Forecast (Forward Net Profit Growth)
   - Balance Sheet metrics (Current Ratio, Debt-to-Asset Ratio)
   - Cash Flow metrics (Operating Cash Flow)
   - Industry classification (for Macro Gate filtering)
3. **Execution**: The script should fetch a small sample of data (e.g., for a single stock or a small subset) and print it to prove the fields are available.
4. **Documentation**: Add comments in the script detailing which `akshare` function corresponds to which required field.
5. **DO NOT** build the actual filtering pipeline, loops, or complex logic. Keep it simple and focused on API discovery.

## Acceptance Criteria (AC)
1. `AMS/scripts/spike_akshare_apis.py` exists and runs successfully without timing out.
2. The script prints a sample of the data required for the 6 layers of the funnel.
3. The correct `akshare` endpoints and field names are clearly identified and mapped to the PRD requirements in the script's comments or output.

## Anti-Patterns (Forensic Post-Mortem Rules)
- DO NOT mix API exploration with full implementation. This caused a timeout previously.
- DO NOT attempt to write the final `crystal_fly_swatter.py` script yet.
- DO NOT build the 6-layer funnel logic. Just fetch the raw data fields to prove they exist.