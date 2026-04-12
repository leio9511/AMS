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
         
         mock_gateway.update_fundamentals.assert_called_once()
         mock_gateway.poll_once.assert_called_once()

def test_main_runner_calls_update_fundamentals():
    with patch("main_runner.TickGateway") as MockGateway, \
         patch("main_runner.ETFArbStrategy"), \
         patch("main_runner.ConvertibleBondStrategy"), \
         patch("main_runner.CrystalFlyStrategy"), \
         patch("main_runner.EventEngine"):
         
         mock_gateway = MockGateway.return_value
         
         main_runner.main()
         
         mock_gateway.update_fundamentals.assert_called_once()
         mock_gateway.poll_once.assert_called_once()
         
         # Assert order
         calls = mock_gateway.mock_calls
         update_idx = next(i for i, call in enumerate(calls) if "update_fundamentals" in str(call))
         poll_idx = next(i for i, call in enumerate(calls) if "poll_once" in str(call))
         assert update_idx < poll_idx

def test_heartbeat_updated():
    with open("/root/.openclaw/workspace/HEARTBEAT.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "## AMS 2.0 Agentic Integration (09:15 AM & 15:30 PM UTC+8)" in content
    assert "Execute `python3 /root/.openclaw/workspace/projects/AMS/main_runner.py`" in content

