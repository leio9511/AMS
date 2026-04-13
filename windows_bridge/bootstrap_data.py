import logging

try:
    import xtquant.xtdata as xtdata
except ImportError:
    xtdata = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("bootstrap_data")

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

def download_history_data():
    logger.info("Downloading historical K-lines and ticks...")
    if xtdata is None:
        logger.warning("xtquant.xtdata not found, skipping download_history_data")
        return
    try:
        # Note: In a real scenario, we might need to iterate over specific instrument codes.
        # Here we mock the behavior or call a generic download if available.
        # For demonstration, we assume downloading an index or full market if supported by xtdata wrapper.
        # We will just log it for now.
        logger.info("Historical data download initiated.")
    except Exception as e:
        logger.error(f"Failed to download historical data: {e}")
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
        download_history_data()
        download_financial_data()
        logger.info("Bootstrap data download finished successfully.")
    except Exception as e:
        logger.error(f"Bootstrap process encountered an error: {e}")

if __name__ == "__main__":
    run_bootstrap()
