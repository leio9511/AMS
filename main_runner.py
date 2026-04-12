import sys
import logging
from engine.event_engine import EventEngine
from engine.gateway import TickGateway
from strategies.etf_arb import ETFArbStrategy
from strategies.convertible_bond import ConvertibleBondStrategy
from strategies.crystal_fly import CrystalFlyStrategy

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Initializing Main Runner...")
    engine = EventEngine()
    gateway = TickGateway()

    etf_arb = ETFArbStrategy(engine)
    conv_bond = ConvertibleBondStrategy(engine)
    crystal_fly = CrystalFlyStrategy(engine)

    etf_arb.start()
    conv_bond.start()
    crystal_fly.start()

    logger.info("Strategies started. Fetching fundamentals snapshot...")
    
    import time
    max_retries = 3
    
    for attempt in range(1, max_retries + 1):
        try:
            gateway.update_fundamentals()
            break
        except Exception as e:
            logger.warning(f"Failed to update fundamentals (Attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                logger.error("Max retries reached for update_fundamentals.")
    
    logger.info("Polling gateway once...")
    for attempt in range(1, max_retries + 1):
        try:
            gateway.poll_once(engine)
            logger.info("Poll complete. Exiting cleanly.")
            break
        except Exception as e:
            logger.warning(f"Failed to poll gateway (Attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                logger.error("Max retries reached for poll_once.")
    
if __name__ == "__main__":
    main()
    sys.exit(0)
