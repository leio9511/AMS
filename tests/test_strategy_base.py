import unittest
from engine.event_engine import EventEngine
from strategies.base_strategy import StrategyBase

class TestStrategyBase(unittest.TestCase):
    def test_strategy_initialization(self):
        engine = EventEngine()
        strategy = StrategyBase(engine=engine, strategy_name="TestStrategy")
        self.assertEqual(strategy.strategy_name, "TestStrategy")
        self.assertFalse(strategy.active)
        self.assertEqual(strategy.engine, engine)

    def test_strategy_start_stop(self):
        engine = EventEngine()
        strategy = StrategyBase(engine=engine)
        
        self.assertFalse(strategy.active)
        
        strategy.start()
        self.assertTrue(strategy.active)
        
        strategy.stop()
        self.assertFalse(strategy.active)

if __name__ == '__main__':
    unittest.main()
