import subprocess
import sys
import json
import os
import pytest

def test_real_cli_execution_smoke():
    """
    Execute the actual main_runner.py script with subprocess. 
    Verify it finishes without error and produces expected JSON structure.
    """
    fixture_path = "/root/projects/AMS/tests/fixtures/cb_history_factors.csv"
    
    command = [
        sys.executable, "main_runner.py",
        "--strategy", "cb_rotation",
        "--start-date", "2025-01-06",
        "--end-date", "2025-01-10",
        "--capital", "4000000",
        "--top-n", "10",
        "--rebalance", "daily",
        "--tp-mode", "both",
        "--tp-pos", "0.20",
        "--tp-intra", "0.08",
        "--sl", "-0.08",
        "--data-path", fixture_path,
        "--format", "json"
    ]
    
    result = subprocess.run(command, capture_output=True, text=True)
    
    # Assert exit_code == 0
    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
    
    # Assert output is valid JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Output is not valid JSON: {result.stdout}")
        
    # Assert contains summary and weekly_performance
    assert "summary" in output
    assert "weekly_performance" in output
    
    # Check if we have some results (since we have 5 days of data)
    assert "total_return" in output["summary"]

def test_canonical_data_path_usage():
    """
    Verify that when no data path is specified, it defaults to the production canonical path.
    We don't need to RUN it (as it might fail if file doesn't exist), 
    just check the help or use a mock if possible, but the requirement says 
    'Verify that when no data path is specified, it defaults to the production canonical path.'
    """
    result = subprocess.run([sys.executable, "main_runner.py", "--help"], capture_output=True, text=True)
    assert "/root/projects/AMS/data/cb_history_factors.csv" in result.stdout
    assert "/root/.openclaw/workspace/data/cb_history_factors.csv" not in result.stdout

def test_json_format_integrity():
    """
    Verify the JSON output matches the schema required by existing reports 
    (Decimal values converted to strings, etc.).
    """
    fixture_path = "/root/projects/AMS/tests/fixtures/cb_history_factors.csv"
    
    command = [
        sys.executable, "main_runner.py",
        "--strategy", "cb_rotation",
        "--start-date", "2025-01-06",
        "--end-date", "2025-01-10",
        "--capital", "4000000",
        "--top-n", "10",
        "--rebalance", "daily",
        "--tp-mode", "both",
        "--tp-pos", "0.20",
        "--tp-intra", "0.08",
        "--sl", "-0.08",
        "--data-path", fixture_path,
        "--format", "json"
    ]
    
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0
    
    output = json.loads(result.stdout)
    summary = output["summary"]
    
    # In DecimalEncoder, Decimals are converted to strings
    assert isinstance(summary["total_return"], str)
    assert isinstance(summary["max_drawdown"], str)
    assert isinstance(summary["final_equity"], str)
    
    if output["weekly_performance"]:
        week = output["weekly_performance"][0]
        assert isinstance(week["total_assets"], str)
        assert isinstance(week["weekly_profit_pct"], str)
