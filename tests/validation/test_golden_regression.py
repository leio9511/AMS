import subprocess
import sys
import json
import pytest
import os

GOLDEN_CASES_FILE = "/root/projects/AMS/tests/golden/baselines/golden_cases.json"
GOLDEN_DATA_PATH = "/root/projects/AMS/tests/golden/data/cb_history_factors_golden_2025_2026.csv"

def load_golden_cases():
    if not os.path.exists(GOLDEN_CASES_FILE):
        return {}
    with open(GOLDEN_CASES_FILE, 'r') as f:
        return json.load(f)

@pytest.mark.parametrize("case_name, case_data", load_golden_cases().items())
def test_golden_cases(case_name, case_data):
    """
    Layer 2 validation - Exact baseline matching for golden cases.
    Verifies that the backtest results exactly match the frozen baselines.
    """
    command = [
        sys.executable, "main_runner.py",
        "--strategy", case_data["strategy"],
        "--start-date", case_data["start_date"],
        "--end-date", case_data["end_date"],
        "--capital", str(case_data["capital"]),
        "--top-n", str(case_data["top_n"]),
        "--rebalance", case_data["rebalance"],
        "--tp-mode", case_data["tp_mode"],
        "--tp-pos", str(case_data["tp_pos"]),
        "--tp-intra", str(case_data["tp_intra"]),
        "--sl", str(case_data["sl"]),
        "--data-path", GOLDEN_DATA_PATH,
        "--format", "json"
    ]
    
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, f"Command failed for {case_name}: {result.stderr}"
    
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Output for {case_name} is not valid JSON: {result.stdout}")
        
    summary = output["summary"]
    baseline_summary = case_data["summary"]
    
    # Compare summary fields (final_equity, total_return, max_drawdown, calmar_ratio)
    required_summary_keys = ["final_equity", "total_return", "max_drawdown", "calmar_ratio"]
    for key in required_summary_keys:
        expected_val = baseline_summary.get(key)
        actual_val = summary.get(key)
        assert str(actual_val) == str(expected_val), f"Summary field {key} mismatch for {case_name}. Expected {expected_val}, got {actual_val}"
        
    # Compare 5 specific weekly_performance checkpoints
    actual_weekly = output["weekly_performance"]
    expected_checkpoints = case_data["checkpoints"]
    
    for expected in expected_checkpoints:
        week_ending = expected["week_ending"]
        # Find the actual week in output
        actual = next((w for w in actual_weekly if w["week_ending"] == week_ending), None)
        assert actual is not None, f"Checkpoint week {week_ending} not found in output for {case_name}"
        
        # Exact matching for each checkpoint field
        for key in ["total_assets", "weekly_profit_pct", "cumulative_pct"]:
            expected_val = expected.get(key)
            actual_val = actual.get(key)
            assert str(actual_val) == str(expected_val), f"Checkpoint field {key} mismatch for {case_name} at {week_ending}. Expected {expected_val}, got {actual_val}"
