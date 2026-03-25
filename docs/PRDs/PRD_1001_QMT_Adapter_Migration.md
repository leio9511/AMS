# PRD-1001: Phase 1 QMT Adapter Migration for Stock Radar

## 1. Problem Statement
The AMS `pilot_stock_radar.py` script frequently crashes with `RemoteDisconnected` errors during Phase 1 bulk market data fetching because it relies on the `akshare` public API (`ak.stock_zh_a_spot_em()`). The underlying miniQMT infrastructure (`QMTClient`) has been established (PRD-007), but the business logic needs to be refactored to use it.

## 2. Solution: The QMT DataFrame Adapter
We must replace the `akshare` fetching functions with `QMTClient` calls, but we cannot fundamentally rewrite the entire scoring and filtering logic in `pilot_stock_radar.py`. That logic expects a specific `pandas.DataFrame` structure returned by AkShare.

We will build an **Adapter Layer** in `pilot_stock_radar.py` (or a helper module) that calls the Windows `QMTClient.get_quote()` or a new batch quote endpoint, and reformats the resulting JSON dictionary into a Pandas DataFrame identical in column naming and types to the legacy `akshare` output.

## 3. Scope & Target Directory
- **Target Project Absolute Path**: `/root/.openclaw/workspace/AMS`
- **In Scope**:
  1. Modify `qmt_client.py` if necessary to support a bulk/full-market tick fetch (e.g., `get_full_tick` wrapper).
  2. Modify the Windows `qmt_bridge_server.py` to expose a `/api/bulk_quote` endpoint calling `xtdata.get_full_tick()`.
  3. Refactor `pilot_stock_radar.py`: Replace `ak.stock_zh_a_spot_em()` and `ak.stock_hk_spot_em()` with the new `QMTClient` bulk fetch.
  4. Create an adapter function in `pilot_stock_radar.py` that maps QMT's raw tick data (e.g., `lastPrice`, `volume`) to the AkShare standard columns (e.g., `代码`, `最新价`, `成交量`, `总市值`, `市盈率-动态`).
- **Out of Scope**: Refactoring `crystal_fly_swatter.py` or `etf_tracker.py` (reserved for Phase 2). Replacing historical K-line fetching logic.

## 4. Testing Strategy & TDD Guardrails
**Strategy**:
- **TDD GUARDRAIL**: The PR contract MUST contain both the failing test AND its implementation fix in the same PR.
- **Unit Testing**: Update `tests/test_qmt_client.py` to mock the new bulk endpoint. Add a new test in `test_data_source.py` or a radar-specific test file to assert that the `Adapter` correctly translates a mocked QMT JSON into a Pandas DataFrame with the required columns.

## 5. Rollout
This migration applies to the `pilot_stock_radar.py` script. The script must successfully run its Phase 1 filter using the new data source without crashing.
