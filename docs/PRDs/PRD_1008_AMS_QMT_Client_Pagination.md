# PRD-1008: QMT Client Pagination & Chunked Data Retrieval (Robust Market Scanner)

## 1. Problem Statement
The AMS (Automated Market Screener) pipeline currently attempts to fetch real-time tick data for the entire A-share market (5,000+ stocks) via a single HTTP GET request to the Windows QMT Bridge (`/api/bulk_quote`).
Due to the massive size of the resulting JSON payload and the processing time required by the `xtdata` API in Windows, the lightweight FastAPI/Uvicorn server frequently exceeds connection timeout thresholds or crashes with a `RemoteDisconnected` error. 
To ensure the stock radar operates reliably across the entire market without arbitrary truncation, we must transition to a robust **Client-Side Pagination (Chunking)** architecture.

## 2. Objective
Redesign the data transmission pipeline between the Linux AMS Radar (`qmt_client.py`) and the Windows QMT Bridge (`server.py`) to support batch processing (e.g., fetching 500 stocks per request). This ensures network stability, prevents server-side memory bloat, and guarantees 100% market coverage.

## 3. Architecture & Solution Strategy

### 3.1 Windows Node (Bridge Server) Upgrades
- Modify `server.py`'s `/api/bulk_quote` endpoint to accept query parameters: `?chunk_size=500&chunk_index=0`.
- **Implementation**:
  1. Retrieve the full list of A-share codes (`xtdata.get_stock_list_in_sector`).
  2. Calculate the slice: `start = chunk_index * chunk_size`, `end = start + chunk_size`.
  3. Fetch full ticks ONLY for that specific slice (`xtdata.get_full_tick(slice)`).
  4. Return the data payload alongside metadata: `{"data": {...}, "total_stocks": 5300, "chunk_index": 0}`.

### 3.2 Linux Node (AMS Client) Upgrades
- Modify `qmt_client.py`'s `get_full_tick()` method.
- **Implementation**:
  1. Implement a `while` loop that requests data chunk by chunk (`chunk_index=0, 1, 2...`).
  2. Accumulate the JSON responses into a single master dictionary.
  3. Break the loop when the returned chunk is empty or the accumulated count matches `total_stocks`.
  4. Ensure a small `time.sleep()` (e.g., 0.2s) between chunk requests to prevent overloading the Windows bridge.

### 3.3 Stock Radar Pipeline
- `pilot_stock_radar.py` remains largely untouched in its core logic, as `qmt_client.get_full_tick()` will abstract away the pagination and simply return the full dictionary just as it did before.

## 4. Scope & Affected Files
- **In Scope**:
  - `AMS/qmt_client.py`: Add pagination loop to `get_full_tick()`.
  - Windows Bridge `server.py`: Update the `/api/bulk_quote` endpoint logic to slice arrays.
  - `AMS/tests/test_qmt_client.py` (New): Write a mock test to verify the client correctly aggregates multiple paginated chunks into one final dataset.

- **Out of Scope**:
  - Modification of the fundamental valuation logic or AkShare fundamental data fetching (already solved in PRD-1002).

## 5. Acceptance Criteria
1. **Pagination**: The Windows endpoint successfully returns data slices without throwing `RemoteDisconnected`.
2. **Aggregation**: The Linux client aggregates 10+ chunks into a single dictionary containing >5000 keys.
3. **Pipeline Health**: `pilot_stock_radar.py` executes from start to finish on the full market dataset without network timeouts.
4. **Testing**: `pytest` passes for the new chunking/aggregation logic.