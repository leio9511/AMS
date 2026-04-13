import logging
import time
import os

try:
    import xtquant.xtdata as xtdata
except ImportError:
    xtdata = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("bootstrap_data")

def get_dir_size(path):
    total = 0
    if not os.path.exists(path):
        return 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total += os.path.getsize(fp)
    except Exception:
        pass
    return total

def wait_for_download(timeout=600):
    if xtdata is None:
        return
    logger.info("Waiting for data downloads to complete...")
    # Attempt to locate datadir
    datadir = getattr(xtdata, 'data_dir', None)
    if not datadir:
        # Fallback to default QMT paths or just wait a fixed time
        datadir = r"C:\qmt\userdata_mini\datadir"
        
    if not os.path.exists(datadir):
        logger.warning(f"Data directory {datadir} not found. Waiting 30s as fallback.")
        time.sleep(30)
        return

    stable_count = 0
    last_size = -1
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        current_size = get_dir_size(datadir)
        if current_size == last_size and current_size > 0:
            stable_count += 1
        else:
            stable_count = 0
            
        last_size = current_size
        
        if stable_count >= 6: # 30 seconds of stability
            logger.info("Data download size stabilized. Assuming complete.")
            return
            
        time.sleep(5)
        
    logger.warning("Timeout reached waiting for data download.")

def download_sector_data():
    logger.info("Downloading sector data...")
    if xtdata is None:
        logger.warning("xtquant.xtdata not found, skipping download_sector_data")
        return
    try:
        xtdata.download_sector_data()
        logger.info("Sector data download initiated/completed.")
    except Exception as e:
        logger.error(f"Failed to download sector data: {e}")
        raise

def download_financial_data():
    logger.info("Downloading financial data...")
    if xtdata is None:
        logger.warning("xtquant.xtdata not found, skipping download_financial_data")
        return
    try:
        xtdata.download_financial_data(["Capital", "Balance", "Income"])
        logger.info("Financial data download initiated.")
    except Exception as e:
        logger.error(f"Failed to download financial data: {e}")
        raise

def run_bootstrap():
    logger.info("Starting sequential bootstrap data download...")
    try:
        download_sector_data()
        download_financial_data()
        wait_for_download(timeout=3600) # Bootstrap can take a while
        logger.info("Bootstrap data download finished successfully.")
    except Exception as e:
        logger.error(f"Bootstrap process encountered an error: {e}")

if __name__ == "__main__":
    run_bootstrap()
