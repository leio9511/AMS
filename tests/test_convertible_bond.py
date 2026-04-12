import unittest
import sys
import io
from engine.event_engine import EventEngine, Event
from strategies.convertible_bond import ConvertibleBondStrategy

class TestConvertibleBondStrategy(unittest.TestCase):
    def setUp(self):
        self.engine = EventEngine()
        self.strategy = ConvertibleBondStrategy(self.engine)

    def test_convertible_bond_logic(self):
        premium = self.strategy.calculate_premium(110.0, 100.0)
        self.assertAlmostEqual(premium, 0.10)
        
        discount = self.strategy.calculate_premium(90.0, 100.0)
        self.assertAlmostEqual(discount, -0.10)

        self.assertTrue(self.strategy.check_discount(-0.01))
        self.assertFalse(self.strategy.check_discount(0.01))

    def test_cb_event_dispatch(self):
        self.strategy.start()
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        event = Event("eTick", {"code": "113050.SH", "premium": -0.01})
        self.engine.process(event)
        
        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()
        self.assertIn("SIGNAL: CB 113050.SH discount is -1.00% (<= -0.8%)", output)

if __name__ == '__main__':
    unittest.main()
