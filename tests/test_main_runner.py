import pytest
from unittest.mock import patch, MagicMock
import main_runner

def test_main_runner_initialization_and_poll():
    with patch("main_runner.TickGateway") as MockGateway, \
         patch("main_runner.ETFArbStrategy") as MockETFArb, \
         patch("main_runner.ConvertibleBondStrategy") as MockConvBond, \
         patch("main_runner.CrystalFlyStrategy") as MockCrystalFly, \
         patch("main_runner.EventEngine") as MockEventEngine:
         
         mock_gateway = MockGateway.return_value
         mock_etf_arb = MockETFArb.return_value
         mock_conv_bond = MockConvBond.return_value
         mock_crystal_fly = MockCrystalFly.return_value
         
         main_runner.main()
         
         MockEventEngine.assert_called_once()
         MockGateway.assert_called_once()
         
         MockETFArb.assert_called_once()
         MockConvBond.assert_called_once()
         MockCrystalFly.assert_called_once()
         
         mock_etf_arb.start.assert_called_once()
         mock_conv_bond.start.assert_called_once()
         mock_crystal_fly.start.assert_called_once()
         
         mock_gateway.poll_once.assert_called_once()
