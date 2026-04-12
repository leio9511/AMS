import unittest
import sys
import io
from engine.event_engine import EventEngine, Event
from strategies.etf_arb import ETFArbStrategy

class TestETFArbStrategy(unittest.TestCase):
    def setUp(self):
        self.engine = EventEngine()
        self.strategy = ETFArbStrategy(self.engine)

    def test_etf_arb_registration(self):
        self.strategy.start()
        # Verify that handlers were registered
        self.assertIn("eTick", self.engine._handlers)
        self.assertIn("eTimer", self.engine._handlers)
        self.assertIn(self.strategy.on_tick, self.engine._handlers["eTick"])
        self.assertIn(self.strategy.on_timer, self.engine._handlers["eTimer"])
        
        self.strategy.stop()
        self.assertNotIn(self.strategy.on_tick, self.engine._handlers.get("eTick", []))

    def test_calculate_premium_pure_logic(self):
        premium = self.strategy.calculate_premium(102.0, 100.0)
        self.assertAlmostEqual(premium, 0.02)
        
        discount = self.strategy.calculate_premium(98.0, 100.0)
        self.assertAlmostEqual(discount, -0.02)

        zero_iopv = self.strategy.calculate_premium(100.0, 0.0)
        self.assertEqual(zero_iopv, 0.0)

    def test_on_tick_extracts_lastPrice(self):
        self.strategy.start()
        
        # Capture stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        # Test premium > 2% using lastPrice
        event = Event("eTick", {"code": "510300.SH", "lastPrice": 4.1, "iopv": 4.0})
        self.engine.process(event)
        
        sys.stdout = sys.__stdout__
        
        output = captured_output.getvalue()
        self.assertIn("!!! SIGNAL: 510300.SH premium is 2.50% (> 2%)", output)
        
        # Test premium <= 2% (should not print)
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        event2 = Event("eTick", {"code": "510300.SH", "lastPrice": 4.05, "iopv": 4.0})
        self.engine.process(event2)
        
        sys.stdout = sys.__stdout__
        self.assertEqual(captured_output.getvalue(), "")

    def test_on_tick_ignores_missing_lastPrice(self):
        self.strategy.start()
        
        # Capture stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        # Test missing lastPrice
        event = Event("eTick", {"code": "510300.SH", "iopv": 4.0})
        self.engine.process(event)
        
        sys.stdout = sys.__stdout__
        
        # No exception should be raised, and no output should occur
        self.assertEqual(captured_output.getvalue(), "")

if __name__ == '__main__':
    unittest.main()
