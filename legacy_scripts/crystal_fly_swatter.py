import os
import json
import time
import logging
import pandas as pd
import akshare as ak
import concurrent.futures

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CACHE_DIR = "AMS/cache"
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(f"{CACHE_DIR}/pe_history", exist_ok=True)

def run_with_timeout_and_retry(func, *args, max_retries=2, timeout=5, **kwargs):
    for attempt in range(max_retries):
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logging.warning(f"Timeout on {func.__name__} (attempt {attempt+1}/{max_retries}) after {timeout}s")
        except Exception as e:
            logging.warning(f"Error on {func.__name__}: {e} (attempt {attempt+1}/{max_retries})")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        time.sleep(1) # Backoff before retry
    return None

def is_cache_valid(filepath, max_age_days):
    if not os.path.exists(filepath):
        return False
    mtime = os.path.getmtime(filepath)
    age = time.time() - mtime
    return age < (max_age_days * 86400)

def fetch_industry_map():
    filepath = f"{CACHE_DIR}/industry_map.json"
    if os.path.exists(filepath):
        logging.info("Phase 1: Loaded industry_map.json from cache [CACHE HIT]")
        with open(filepath, 'r') as f:
            return json.load(f)
    logging.info("Phase 1: Fetching industry map [CACHE MISS]")
    # Lightweight mock for test speed, representing batch industry fetch
    data = {"600519": "Liquor", "000858": "Liquor"}
    tmp_path = filepath + ".tmp"
    with open(tmp_path, 'w') as f:
        json.dump(data, f)
    os.replace(tmp_path, filepath)
    return data

def fetch_financials():
    filepath = f"{CACHE_DIR}/financials.json"
    if is_cache_valid(filepath, max_age_days=30):
        logging.info("Phase 1: Loaded financials.json from cache [CACHE HIT]")
        with open(filepath, 'r') as f:
            return json.load(f)
    logging.info("Phase 1: Fetching financials [CACHE MISS]")
    data = {"600519": {"pe": 30}, "000858": {"pe": 20}}
    tmp_path = filepath + ".tmp"
    with open(tmp_path, 'w') as f:
        json.dump(data, f)
    os.replace(tmp_path, filepath)
    return data

def fetch_bulk_spot():
    logging.info("Phase 1: Fetching bulk spot market data for YTD Return")
    # Using ak.stock_zh_a_spot_em for bulk spot market data
    df = run_with_timeout_and_retry(ak.stock_zh_a_spot_em, timeout=10)
    return df

def fetch_pe_history(symbol):
    filepath = f"{CACHE_DIR}/pe_history/{symbol}.csv"
    if is_cache_valid(filepath, max_age_days=7):
        logging.info(f"Phase 2: Loaded pe_history for {symbol} from cache [CACHE HIT]")
        return pd.read_csv(filepath)
    logging.info(f"Phase 2: Fetching pe_history for {symbol} [CACHE MISS]")
    df = run_with_timeout_and_retry(ak.stock_zh_a_hist, symbol=symbol, period="daily", start_date="20240101", adjust="qfq", timeout=5)
    if df is not None and not df.empty:
        tmp_path = filepath + ".tmp"
        df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, filepath)
    return df

def fetch_profit_forecast(symbol):
    logging.info(f"Phase 2: Real-time fetch profit forecast for {symbol}")
    return run_with_timeout_and_retry(ak.stock_profit_forecast_ths, symbol=symbol, timeout=5)

def main():
    logging.info("=== Phase 1: Batch ===")
    industry_map = fetch_industry_map()
    financials = fetch_financials()
    spot_data = fetch_bulk_spot()
    
    test_stocks = ["600519", "000858"]
    survivors = []
    
    if spot_data is not None and not spot_data.empty:
        for symbol in test_stocks:
            if symbol in industry_map and symbol in financials:
                survivors.append(symbol)
    else:
        logging.warning("Failed to fetch spot data, using test stocks as fallback.")
        survivors = test_stocks

    logging.info(f"Phase 1 survivors: {survivors}")

    logging.info("=== Phase 2: Point ===")
    passed_stocks = []
    for symbol in survivors:
        logging.info(f"--- Processing {symbol} ---")
        pe_hist = fetch_pe_history(symbol)
        if pe_hist is None or pe_hist.empty:
            logging.info(f"Failed to get PE history for {symbol}")
            continue
            
        forecast = fetch_profit_forecast(symbol)
        if forecast is None:
            logging.info(f"Failed to get profit forecast for {symbol}")
            continue
            
        passed_stocks.append(symbol)

    logging.info("=============================")
    logging.info(f"Final Filtered Stocks: {passed_stocks}")

if __name__ == "__main__":
    main()
