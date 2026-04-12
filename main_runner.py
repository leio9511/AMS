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

    logger.info("Strategies started. Polling gateway once...")
    gateway.poll_once(engine)
    logger.info("Poll complete. Exiting cleanly.")
    
if __name__ == "__main__":
    main()
    sys.exit(0)
