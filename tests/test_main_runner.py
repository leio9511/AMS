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

def test_cli_tp_mode_validation():
    test_args = ["main_runner.py", "--strategy", "cb_rotation", "--start-date", "2025-01-01", 
                 "--end-date", "2025-01-31", "--capital", "4000000", "--top-n", "20", 
                 "--rebalance", "daily", "--tp-mode", "both", "--sl", "-0.08"]
    
    with patch("sys.argv", test_args):
        with pytest.raises(ValueError) as exc:
            main_runner.main()
        assert "ERROR: --tp-mode 'both' requires both --tp-pos and --tp-intra to be set." in str(exc.value)

@patch("main_runner.BacktestRunner")
@patch("main_runner.reporting.generate_report_data")
def test_cli_integration_json_output(mock_gen_report, mock_runner_class, capsys):
    mock_runner = MagicMock()
    mock_runner.run.return_value = pd.DataFrame() # Mocked return value
    mock_runner_class.return_value = mock_runner
    
    mock_gen_report.return_value = {
        "summary": {
            "total_return": Decimal("0.1234"),
            "max_drawdown": Decimal("-0.0567"),
            "calmar_ratio": Decimal("2.17"),
            "final_equity": Decimal("4493600.00")
        },
        "weekly_performance": [
            {
                "week_ending": "2025-01-10",
                "total_assets": Decimal("4100000.00"),
                "weekly_profit_pct": Decimal("0.025"),
                "cumulative_pct": Decimal("0.025")
            }
        ]
    }

    test_args = ["main_runner.py", "--strategy", "cb_rotation", "--start-date", "2025-01-01", 
                 "--end-date", "2025-01-31", "--capital", "4000000", "--top-n", "20", 
                 "--rebalance", "daily", "--tp-mode", "position", "--tp-pos", "0.20", 
                 "--sl", "-0.08", "--format", "json"]
    
    with patch("sys.argv", test_args):
        main_runner.main()
        
    captured = capsys.readouterr()
    output = captured.out
    
    # Verify it is valid JSON
    parsed = json.loads(output)
    assert parsed["summary"]["total_return"] == "0.1234"
    assert parsed["weekly_performance"][0]["total_assets"] == "4100000.00"

def test_strategy_instantiation_with_routed_params():
    # Verify CBRotationStrategy can be instantiated with the new parameter set
    tp_config = TakeProfitConfig(mode=TakeProfitMode.BOTH, pos_threshold=Decimal('0.2'), intra_threshold=Decimal('0.08'))
    strategy = CBRotationStrategy(
        top_n=10,
        rebalance='daily',
        sl=-0.08,
        tp_mode='both',
        tp_config=tp_config,
        extra_param="should_be_ignored"
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
    assert kwargs['rebalance'] == 'weekly'
    assert kwargs['sl'] == -0.05
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
