# PRD: M7 - Inverted Funnel & Multi-Tier Caching

## 1. Vision & Goal
The current "Crystal Fly Swatter" script (M6) successfully implements the 6-layer logic but is architecturally a "toy script." It hardcodes a 2-stock test list and fetches all data points synchronously. Running this against the entire A-share market (~5000 stocks) will result in massive API timeouts, rate-limiting, and CI failures.

The goal of M7 is to transform this script into an **industrial-grade data pipeline** capable of processing the entire A-share market daily. This will be achieved through **Funnel Inversion** (Fast/Static gates first, Slow/Dynamic gates last) and a **Multi-Tier Local Caching** system.

## 2. Architecture: The Multi-Tier Cache & Inverted Funnel

The screening process MUST be re-ordered based on data acquisition cost and volatility, leveraging a local file-system cache (`AMS/cache/`) to minimize network calls.

### Phase 1: The Fast/Static Filter (Batch Operations)
*These gates use data that changes infrequently. They must filter out the majority of the 5000 stocks using bulk data before any slow API calls are made.*

- **Gate A: Macro Industry Gate (Layer 5)**
  - **Volatility**: Static (Rarely changes).
  - **Cache Strategy**: Fetch full A-share industry mapping once. Save as `cache/industry_map.json`. Only re-fetch if a stock code is missing from the cache.
  - **Action**: Filter out Airlines, Shipping, etc.
- **Gate B: Financial Health Gate (Layer 2)**
  - **Volatility**: Quarterly (Changes 4 times a year).
  - **Cache Strategy**: Fetch latest financial metrics (Current Ratio, Debt, Operating Cash). Save as `cache/financials.json`. Implement a TTL (Time-To-Live) check—re-fetch only if the cache file is older than 30 days.
- **Gate C: Contrarian Drop Gate (Layer 4)**
  - **Volatility**: Daily.
  - **Cache Strategy**: No cache. Use `akshare`'s bulk A-share spot market API to calculate YTD return for all remaining stocks in one single network call.

### Phase 2: The Slow/Dynamic Filter (Point Operations)
*Only the stocks that survive Phase 1 (estimated < 500) proceed to these expensive, per-stock API calls.*

- **Gate D: Valuation Percentile Gate (Layer 3)**
  - **Volatility**: Long-term historical.
  - **Cache Strategy**: Fetch the 5-year historical PE series for a stock and save it as `cache/pe_history/<stock_code>.csv`. 
  - **Update Logic**: When checking a stock, if the CSV exists and is less than 7 days old, use it to calculate the percentile. If older or missing, re-fetch the full 5-year history and overwrite the CSV.
- **Gate E: Forward Profit Gate (Layer 1 & 3)**
  - **Volatility**: High (Analyst revisions).
  - **API Cost**: Extremely slow, prone to hanging (`ak.stock_profit_forecast_ths`).
  - **Cache Strategy**: No cache. Real-time fetch. 
  - **Action**: This must be the absolute LAST step. Use strict timeouts and the `ThreadPoolExecutor` implemented in M6.

## 3. Acceptance Criteria
- A `cache` directory is implemented to store JSON and CSV data.
- The script successfully processes a list of 5000 dummy stock codes (or a realistic large proxy list) by dropping 90% of them in Phase 1 via cached data.
- Slow APIs (`stock_profit_forecast_ths`, historical PE) are ONLY called for stocks that pass the Fast/Static filter.
- Cache invalidation logic works (e.g., if a file is manually deleted or deemed expired, the script automatically re-fetches it).
- The final output remains a clean JSON array of qualifying stock codes printed to stdout.
