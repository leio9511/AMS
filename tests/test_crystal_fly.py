import unittest
import sys
import io
from engine.event_engine import EventEngine, Event
from strategies.crystal_fly import CrystalFlyStrategy

class TestCrystalFlyStrategy(unittest.TestCase):
    def setUp(self):
        self.engine = EventEngine()
        self.strategy = CrystalFlyStrategy(self.engine)

    def test_crystal_fly_pure_filters(self):
        self.assertTrue(self.strategy.check_fundamentals(20.0, 30.0))
        self.assertFalse(self.strategy.check_fundamentals(35.0, 30.0))
        self.assertFalse(self.strategy.check_fundamentals(None, 30.0))

    def test_crystal_fly_event_dispatch(self):
        self.strategy.start()
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        event = Event("eTick", {"code": "600519.SH", "pe": 25.0})
        self.engine.process(event)
        
        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()
        self.assertIn("SIGNAL: 600519.SH passed fundamental screening", output)

if __name__ == '__main__':
    unittest.main()
