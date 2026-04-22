import pytest
import subprocess
import json
import sys
import pandas as pd
from decimal import Decimal
from unittest.mock import patch, MagicMock
from ams.core.factory import StrategyFactory
from ams.utils import reporting
from ams.core.cb_rotation_strategy import CBRotationStrategy
from ams.core.history_datafeed import HistoryDataFeed
from ams.models.config import TakeProfitConfig, TakeProfitMode
import main_runner

def test_cli_help_output():
    result = subprocess.run([sys.executable, "main_runner.py", "--help"], capture_output=True, text=True)
    assert "--strategy" in result.stdout
    assert "The identifier of the strategy to run" in result.stdout
    assert "--start-date" in result.stdout
    assert "--end-date" in result.stdout
    assert "--capital" in result.stdout
    assert "--top-n" in result.stdout
    assert "--rebalance" in result.stdout
    assert "--tp-mode" in result.stdout
    assert "--tp-pos" in result.stdout
    assert "--tp-intra" in result.stdout
    assert "--sl" in result.stdout
    assert "--format" in result.stdout

def test_main_runner_default_data_path():
    result = subprocess.run([sys.executable, "main_runner.py", "--help"], capture_output=True, text=True)
    expected_default = "/root/.openclaw/workspace/data/cb_history_factors.csv"
    assert expected_default in result.stdout

def test_main_runner_argument_default():
    test_args = ["main_runner.py", "--strategy", "cb_rotation", "--start-date", "2025-01-01", 
                 "--end-date", "2025-01-31", "--capital", "4000000", "--top-n", "20", 
                 "--rebalance", "daily", "--tp-mode", "position", "--tp-pos", "0.20", 
                 "--sl", "-0.08"]
    
    with patch("sys.argv", test_args), \
         patch("main_runner.HistoryDataFeed") as mock_data_feed, \
         patch("main_runner.SimBroker"), \
         patch("main_runner.StrategyFactory.create_strategy"), \
         patch("main_runner.BacktestRunner"), \
         patch("main_runner.reporting.generate_report_data"):
        main_runner.main()
        
        mock_data_feed.assert_called_once()
        call_args = mock_data_feed.call_args
        assert call_args.kwargs['file_path'] == "/root/.openclaw/workspace/data/cb_history_factors.csv"

def test_cli_tp_mode_validation():
    test_args = ["main_runner.py", "--strategy", "cb_rotation", "--start-date", "2025-01-01", 
                 "--end-date", "2025-01-31", "--capital", "4000000", "--top-n", "20", 
                 "--rebalance", "daily", "--tp-mode", "both", "--sl", "-0.08"]
    
    with patch("sys.argv", test_args):
        with pytest.raises(ValueError) as exc:
            main_runner.main()
        assert "ERROR: --tp-mode 'both' requires both --tp-pos and --tp-intra to be set." in str(exc.value)

def test_cli_integration_json_output(tmp_path, capsys):
    # Create a small fixture CSV
    csv_file = tmp_path / "test_cb_data.csv"
    csv_content = """ticker,date,open,high,low,close,volume,premium_rate,double_low,underlying_ticker,is_st,is_redeemed
123001.SZ,2025-01-06,120.0,122.0,119.0,121.0,100000,0.05,125.0,300001.SZ,False,False
123002.SZ,2025-01-06,110.0,112.0,109.0,111.0,200000,0.10,121.0,300002.SZ,False,False
123001.SZ,2025-01-07,121.0,123.0,120.0,122.0,110000,0.06,128.0,300001.SZ,False,False
123002.SZ,2025-01-07,111.0,113.0,110.0,112.0,210000,0.11,123.0,300002.SZ,False,False
"""
    csv_file.write_text(csv_content)

    test_args = ["main_runner.py", "--strategy", "cb_rotation", "--start-date", "2025-01-06", 
                 "--end-date", "2025-01-07", "--capital", "4000000", "--top-n", "10", 
                 "--rebalance", "daily", "--tp-mode", "position", "--tp-pos", "0.20", 
                 "--sl", "-0.08", "--format", "json"]
    
    # Patch the DataFeed path in main_runner and run
    with patch("sys.argv", test_args), \
         patch("main_runner.HistoryDataFeed", return_value=HistoryDataFeed(file_path=str(csv_file))):
        main_runner.main()
        
    captured = capsys.readouterr()
    output = captured.out
    
    # Verify it is valid JSON and contains required keys
    parsed = json.loads(output)
    assert "summary" in parsed
    assert "weekly_performance" in parsed
    assert "total_return" in parsed["summary"]
    assert "max_drawdown" in parsed["summary"]

def test_strategy_instantiation_with_routed_params():
    # Verify CBRotationStrategy can be instantiated with the formal parameter set
    tp_config = TakeProfitConfig(mode=TakeProfitMode.BOTH, pos_threshold=Decimal('0.2'), intra_threshold=Decimal('0.08'))
    strategy = CBRotationStrategy(
        top_n=10,
        rebalance_period='daily',
        stop_loss_threshold=-0.08,
        tp_mode='both',
        tp_config=tp_config
    )
    assert strategy.top_n == 10
    assert strategy.rebalance_period == 'daily'
    assert strategy.stop_loss_threshold == -0.08
    assert strategy.tp_config == tp_config

@patch("main_runner.BacktestRunner")
@patch("main_runner.SimBroker")
@patch("main_runner.StrategyFactory.create_strategy")
def test_main_runner_argument_distribution(mock_create_strategy, mock_broker_class, mock_runner_class):
    test_args = ["main_runner.py", "--strategy", "cb_rotation", "--start-date", "2025-01-01", 
                 "--end-date", "2025-01-31", "--capital", "5000000", "--top-n", "15", 
                 "--rebalance", "weekly", "--tp-mode", "intraday", "--tp-intra", "0.10", 
                 "--sl", "-0.05", "--format", "text"]
    
    with patch("sys.argv", test_args):
        main_runner.main()
        
    # Verify SimBroker received capital
    mock_broker_class.assert_called_once_with(initial_cash=5000000.0)
    
    # Verify StrategyFactory received correct parameters
    kwargs = mock_create_strategy.call_args.kwargs
    assert kwargs['top_n'] == 15
    assert kwargs['rebalance_period'] == 'weekly'
    assert kwargs['stop_loss_threshold'] == -0.05
    assert kwargs['tp_mode'] == 'intraday'
    assert isinstance(kwargs['tp_config'], TakeProfitConfig)
    assert kwargs['tp_config'].mode == TakeProfitMode.INTRADAY
    assert kwargs['tp_config'].intra_threshold == Decimal('0.1')
    
    # Verify BacktestRunner.run received dates
    mock_runner = mock_runner_class.return_value
    mock_runner.run.assert_called_once_with("2025-01-01", "2025-01-31")

def test_tp_config_injection():
    # Verify that TakeProfitConfig is correctly created and injected
    test_args = ["main_runner.py", "--strategy", "cb_rotation", "--start-date", "2025-01-01", 
                 "--end-date", "2025-01-31", "--capital", "4000000", "--top-n", "20", 
                 "--rebalance", "daily", "--tp-mode", "both", "--tp-pos", "0.20", 
                 "--tp-intra", "0.08", "--sl", "-0.08"]
    
    with patch("sys.argv", test_args), \
         patch("main_runner.StrategyFactory.create_strategy") as mock_create, \
         patch("main_runner.BacktestRunner"):
        main_runner.main()
        
        tp_config = mock_create.call_args.kwargs['tp_config']
        assert isinstance(tp_config, TakeProfitConfig)
        assert tp_config.mode == TakeProfitMode.BOTH
        assert tp_config.pos_threshold == Decimal('0.2')
        assert tp_config.intra_threshold == Decimal('0.08')

def test_skill_md_content():
    with open("/root/projects/AMS/SKILL.md", "r") as f:
        content = f.read()
    
    expected_block = "5. **Strategy Backtester**:\n   `python3 main_runner.py --strategy <ID> --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --capital <FLOAT> --top-n <INT> --rebalance <daily|weekly> --tp-mode <both|position|intraday> --tp-pos <FLOAT> --tp-intra <FLOAT> --sl <FLOAT> [--format json]`\n   Use this for rigorous strategy validation. Use `--format json` for bit-accurate results."
    
    assert expected_block in content
