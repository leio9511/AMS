import pytest
import subprocess
import json
import sys
from decimal import Decimal
from unittest.mock import patch, MagicMock
from ams.core.factory import StrategyFactory
from ams.utils.reporting import format_json
import main_runner

def test_cli_help_output():
    result = subprocess.run([sys.executable, "main_runner.py", "--help"], capture_output=True, text=True)
    stdout_no_newlines = result.stdout.replace('\n', ' ')
    assert "--strategy" in result.stdout
    # We check if the un-wrapped help strings are present, to accommodate argparse wrapping.
    assert "The identifier of the strategy to run" in result.stdout
    assert "--start-date" in result.stdout
    assert "Backtest start date" in result.stdout
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

@patch("main_runner.StrategyFactory.create_strategy")
def test_cli_integration_json_output(mock_create_strategy, capsys):
    mock_strategy = MagicMock()
    mock_strategy.run.return_value = {
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
    mock_create_strategy.return_value = mock_strategy

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

def test_skill_md_content():
    with open("/root/projects/AMS/SKILL.md", "r") as f:
        content = f.read()
    
    expected_block = "5. **Strategy Backtester**:\n   `python3 main_runner.py --strategy <ID> --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --capital <FLOAT> --top-n <INT> --rebalance <daily|weekly> --tp-mode <both|position|intraday> --tp-pos <FLOAT> --tp-intra <FLOAT> --sl <FLOAT> [--format json]`\n   Use this for rigorous strategy validation. Use `--format json` for bit-accurate results."
    
    assert expected_block in content

