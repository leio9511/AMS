import sys
import logging

sys.path.append('/root/.openclaw/workspace/projects/AMS')
from engine.event_engine import EventEngine, Event, EVENT_TICK
from strategies.etf_arb import ETFArbStrategy
from strategies.convertible_bond import ConvertibleBondStrategy
from strategies.crystal_fly import CrystalFlyStrategy

logging.basicConfig(level=logging.INFO, format='%(message)s')

def simulate():
    print("==================================================")
    print("🚀 [Simulation] AMS v2.0 Friday Close Data Replay")
    print("==================================================\n")
    
    engine = EventEngine()
    
    # Initialize and start strategies
    etf = ETFArbStrategy(engine)
    cb = ConvertibleBondStrategy(engine)
    cf = CrystalFlyStrategy(engine)
    
    etf.start()
    cb.start()
    cf.start()

    # 2. Mock Friday's closing data 
    # (Since QMT tick is empty over the weekend and we can't reliably fetch historical fundamentals without QMT terminal download)
    friday_close_ticks = {
        # ETF Arbitrage Scenario: Price significantly higher than IOPV
        "510300.SH": {"lastPrice": 4.642, "iopv": 4.510},  # ~2.9% premium
        
        # Convertible Bond Arbitrage Scenario: Price lower than Conversion Value
        # Note: ConvertibleBondStrategy in Phase 3 expected "price" key, let's provide both just in case
        "113050.SH": {"lastPrice": 115.000, "price": 115.000, "conv_value": 117.000}, # ~ -1.7% discount
        
        # Crystal Fly Fundamental Scenario: High quality, low PE
        # PE = (Price * total_capital) / net_profit
        # Let's mock China Shenhua with a PE ~ 10.0
        "601088.SH": {"lastPrice": 38.500, "total_capital": 19800000000, "net_profit": 76200000000}, 
        
        # Yangtze Power: PE ~ 18.0 (Should trigger if threshold is < 30)
        "600900.SH": {"lastPrice": 25.400, "total_capital": 24400000000, "net_profit": 34400000000},
        
        # A stock that shouldn't trigger Crystal Fly (PE too high, e.g., > 100)
        "300750.SZ": {"lastPrice": 180.000, "total_capital": 4300000000, "net_profit": 5000000000}   
    }

    print("[System] Injecting Friday Close Events into EventEngine...\n")
    
    for code, tick in friday_close_ticks.items():
        payload = {"code": code}
        payload.update(tick)
        
        event = Event(type=EVENT_TICK, data=payload)
        engine.process(event)
        
    print("\n[System] Simulation Complete.")

if __name__ == "__main__":
    simulate()