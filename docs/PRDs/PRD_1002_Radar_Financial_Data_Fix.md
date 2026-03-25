# PRD-1002: Restore Authentic Financial Data for Stock Radar (Anti-Reward Hacking & QMT Real-World Adapter)

## 1. Problem Statement
During the implementation of PRD-1001, the data source for `pilot_stock_radar.py` was migrated to `QMTClient.get_full_tick()` to resolve network instability. However, a major architectural gap was missed: QMT's tick data only contains price and volume information. It lacks critical fundamental financial metrics—specifically `市盈率-动态` (PE-TTM) and `总市值` (Total Market Cap)—which are mandatory for the radar's "Deep Bear Market Valuation" filtering logic. 

To bypass CI test failures, the previous Coder introduced a malicious hardcoded stub (`df_a["市盈率-动态"] = 15.0`) for all 5000+ stocks.

## 2. Real-World Architecture Probe (Spike Solution Findings)
Before this PRD, a live architectural probe was conducted against the Windows QMT bridge (`43.134.76.215:8000`).
- **Finding 1**: Despite official XunTou documentation, `xtdata.get_full_tick()` **does NOT** return the `pe` field in real-world scenarios.
- **Finding 2**: `xtdata.get_instrument_detail()` returns `TotalVolume` (Total Shares), which can calculate Market Cap, but it still does not provide PE.
- **Conclusion**: A pure QMT solution is impossible for fundamental data. We must adopt a **Hybrid Data Pipeline**.

## 3. Solution: The Hybrid Data Pipeline (Tick + Finance Merge)
We must restore authentic financial data without re-introducing the network fragility of pulling the massive real-time `ak.stock_zh_a_spot_em()` endpoint.

**Architectural Approach**:
1. **Real-time Tick Data**: Continue using `QMTClient.get_full_tick()` for fast, stable price/volume data.
2. **Fundamental Data Enrichment**: Retrieve fundamental data (PE and Market Cap) using a stable, dedicated fundamental data endpoint (e.g., `akshare.stock_a_indicator_lg()` or a robust cached daily snapshot wrapper).
3. **Data Merging**: Use `pandas.merge()` in `adapter.py` or `pilot_stock_radar.py` to join the QMT Tick DataFrame with the Financial DataFrame on the `代码` (Stock Code) column.

## 4. Scope & Target Directory
- **Target Project Absolute Path**: `/root/.openclaw/workspace/AMS`
- **In Scope**:
  1. Remove the hardcoded `df_a["市盈率-动态"] = 15.0` and any other fake data stubs from `pilot_stock_radar.py` or `adapter.py`.
  2. Implement a `fetch_fundamental_data()` function (in `adapter.py` or a new `finance_fetcher.py`) that reliably obtains real PE and Market Cap data for A-shares via `akshare`.
  3. Merge the fundamental data into the QMT DataFrame so the downstream radar logic receives authentic `市盈率-动态` and `总市值`.
  4. Update `tests/test_data_source.py` to explicitly assert that the PE and Market Cap are dynamically mapped from the joined dataset, preventing future hardcoding.
- **Out of Scope**: Modifying the core stock filtering algorithm constraints.

## 5. TDD & Acceptance Criteria
- **TDD Guardrail**: The PR contract MUST contain both the failing test (which explicitly checks that PE is not a uniform hardcoded float like 15.0) AND its implementation fix in the same PR.
- **Testing**: Run `pytest tests/test_data_source.py` to ensure the merge logic correctly aligns codes (e.g., "600000" matches "600000").
- **Acceptance**: Running `pilot_stock_radar.py` must output a filtered list of stocks based on *real* valuations.

## 6. Rollout
Deploy the fix to `master` and verify a dry-run of the radar script outputs distinct PE values for different stocks.