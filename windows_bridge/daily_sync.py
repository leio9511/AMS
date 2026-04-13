import os
import sys
import time
import logging

try:
    from xtquant import xtdata
except ImportError:
    xtdata = None  # For local testing without xtquant

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_dir_size(path):
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += get_dir_size(entry.path)
    except Exception as e:
        logging.debug(f"Error reading directory {path}: {e}")
    return total

def wait_for_data_stabilization(data_dir, timeout=300, check_interval=2.0, required_stable_checks=3):
    """
    Poll the datadir to see when the size stops changing, indicating download completion.
    """
    if not os.path.exists(data_dir):
        logging.warning(f"Data directory {data_dir} does not exist yet. Creating...")
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception as e:
            logging.error(f"Failed to create data dir {data_dir}: {e}")
        
    start_time = time.time()
    stable_count = 0
    last_size = -1
    
    while time.time() - start_time < timeout:
        current_size = get_dir_size(data_dir)
        logging.info(f"Current data dir size: {current_size} bytes")
        
        if current_size == last_size and current_size > 0:
            stable_count += 1
            logging.info(f"Size stable for {stable_count}/{required_stable_checks} checks.")
            if stable_count >= required_stable_checks:
                logging.info("Data download stabilized and completed.")
                return True
        else:
            if current_size > 0:
                stable_count = 0  # Reset if size changed
            last_size = current_size
            
        time.sleep(check_interval)
        
    logging.error(f"Timeout reached ({timeout}s) waiting for data stabilization.")
    return False

def main(data_dir=None, timeout=300):
    if xtdata is None:
        logging.error("xtquant.xtdata module not found. Are you running this on the QMT node?")
        sys.exit(1)
        
    if data_dir is None:
        try:
            data_dir = xtdata.data_dir
            if not data_dir:
                data_dir = r"C:\qmt\userdata_mini\datadir"
        except AttributeError:
            data_dir = r"C:\qmt\userdata_mini\datadir"
        
    logging.info("Starting sector data download...")
    xtdata.download_sector_data()
    
    logging.info("Starting financial data download...")
    xtdata.download_financial_data()
    
    logging.info(f"Waiting for downloads to stabilize in {data_dir}...")
    success = wait_for_data_stabilization(data_dir, timeout=timeout)
    
    if success:
        logging.info("Daily sync completed successfully.")
        sys.exit(0)
    else:
        logging.error("Daily sync failed due to timeout.")
        sys.exit(1)

if __name__ == "__main__":
    main()
