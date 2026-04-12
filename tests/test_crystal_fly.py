import unittest
import io
import sys
from engine.event_engine import EventEngine, Event
from strategies.crystal_fly import CrystalFlyStrategy

class TestCrystalFlyStrategy(unittest.TestCase):
    def setUp(self):
        self.engine = EventEngine()
        self.strategy = CrystalFlyStrategy(self.engine)
        self.strategy.start()

    def tearDown(self):
        self.strategy.stop()

    def test_dynamic_pe_calculation_valid(self):
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        # pe = (10.0 * 100.0) / 50.0 = 20.0
        event = Event("eTick", {"code": "600519.SH", "lastPrice": 10.0, "total_capital": 100.0, "net_profit": 50.0})
        self.engine.process(event)
        
        sys.stdout = sys.__stdout__
        self.assertIn("SIGNAL: 600519.SH passed fundamental screening (PE: 20.00)", captured_output.getvalue())

    def test_dynamic_pe_calculation_zero_or_missing_profit(self):
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        # net_profit = 0
        event = Event("eTick", {"code": "600519.SH", "lastPrice": 10.0, "total_capital": 100.0, "net_profit": 0.0})
        self.engine.process(event)
        
        # missing profit
        event2 = Event("eTick", {"code": "600519.SH", "lastPrice": 10.0, "total_capital": 100.0})
        self.engine.process(event2)
        
        sys.stdout = sys.__stdout__
        self.assertEqual(captured_output.getvalue(), "")

if __name__ == '__main__':
    unittest.main()
