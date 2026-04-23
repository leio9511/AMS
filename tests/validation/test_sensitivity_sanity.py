import subprocess
import sys
import json
import pytest
import os

# Absolute paths as per Mandatory File I/O Policy
PROJECT_ROOT = "/root/projects/AMS"
GOLDEN_CASES_FILE = os.path.join(PROJECT_ROOT, "tests/golden/baselines/golden_cases.json")
GOLDEN_DATA_PATH = os.path.join(PROJECT_ROOT, "tests/golden/data/cb_history_factors_golden_2025_2026.csv")

def load_base_config():
    if not os.path.exists(GOLDEN_CASES_FILE):
        pytest.skip(f"Golden cases file not found: {GOLDEN_CASES_FILE}")
    with open(GOLDEN_CASES_FILE, 'r') as f:
        data = json.load(f)
        # Use CASE_WEEKLY_BEST as the standard sensitivity baseline
        return data.get("CASE_WEEKLY_BEST")

def run_backtest(params):
    command = [
        sys.executable, "main_runner.py",
        "--strategy", params["strategy"],
        "--start-date", params["start_date"],
        "--end-date", params["end_date"],
        "--capital", str(params["capital"]),
        "--top-n", str(params["top_n"]),
        "--rebalance", params["rebalance"],
        "--tp-mode", params["tp_mode"],
        "--tp-pos", str(params["tp_pos"]),
        "--tp-intra", str(params["tp_intra"]),
        "--sl", str(params["sl"]),
        "--data-path", GOLDEN_DATA_PATH,
        "--format", "json"
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Backtest failed with return code {result.returncode}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON: {e}")
        print(f"STDOUT: {result.stdout}")
        return None

def test_stop_loss_sensitivity():
    """
    Test Case 1: Verify that changing sl affects the summary results.
    """
    base_params = load_base_config()
    assert base_params is not None, "CASE_WEEKLY_BEST not found in golden_cases.json"
    
    res_base = run_backtest(base_params)
    assert res_base is not None, "Base backtest failed"
    summary_base = res_base["summary"]
    
    # Perturb sl
    perturbed_params = base_params.copy()
    perturbed_params["sl"] = -0.05  # Base is -0.10
    res_perturbed = run_backtest(perturbed_params)
    assert res_perturbed is not None, "Perturbed backtest failed (sl)"
    summary_perturbed = res_perturbed["summary"]
    
    # Check sensitivity
    metrics = ["final_equity", "total_return", "max_drawdown", "calmar_ratio"]
    different = any(str(summary_base[m]) != str(summary_perturbed[m]) for m in metrics)
    
    assert different, (
        f"Sensitivity failure: Summary results (final_equity, total_return, max_drawdown, calmar_ratio) "
        f"remained identical when sl was modified from {base_params['sl']} to {perturbed_params['sl']}. "
        f"This suggests 'sl' parameter may be disconnected from execution logic."
    )

def test_tp_pos_sensitivity():
    """
    Test Case 2: Verify that changing tp_pos affects the summary results.
    """
    base_params = load_base_config()
    assert base_params is not None, "CASE_WEEKLY_BEST not found in golden_cases.json"
    
    res_base = run_backtest(base_params)
    assert res_base is not None, "Base backtest failed"
    summary_base = res_base["summary"]
    
    # Perturb tp_pos
    perturbed_params = base_params.copy()
    perturbed_params["tp_pos"] = 0.25  # Base is 0.15
    res_perturbed = run_backtest(perturbed_params)
    assert res_perturbed is not None, "Perturbed backtest failed (tp_pos)"
    summary_perturbed = res_perturbed["summary"]
    
    # Check sensitivity
    metrics = ["final_equity", "total_return", "max_drawdown", "calmar_ratio"]
    different = any(str(summary_base[m]) != str(summary_perturbed[m]) for m in metrics)
    
    assert different, (
        f"Sensitivity failure: Summary results remained identical when tp_pos was modified "
        f"from {base_params['tp_pos']} to {perturbed_params['tp_pos']}. "
        f"This suggests 'tp_pos' parameter may be disconnected from execution logic."
    )

def test_tp_intra_sensitivity():
    """
    Test Case 3: Verify that changing tp_intra affects the summary results.
    """
    base_params = load_base_config()
    assert base_params is not None, "CASE_WEEKLY_BEST not found in golden_cases.json"
    
    res_base = run_backtest(base_params)
    assert res_base is not None, "Base backtest failed"
    summary_base = res_base["summary"]
    
    # Perturb tp_intra
    perturbed_params = base_params.copy()
    perturbed_params["tp_intra"] = 0.08  # Base is 0.12
    res_perturbed = run_backtest(perturbed_params)
    assert res_perturbed is not None, "Perturbed backtest failed (tp_intra)"
    summary_perturbed = res_perturbed["summary"]
    
    # Check sensitivity
    metrics = ["final_equity", "total_return", "max_drawdown", "calmar_ratio"]
    different = any(str(summary_base[m]) != str(summary_perturbed[m]) for m in metrics)
    
    assert different, (
        f"Sensitivity failure: Summary results remained identical when tp_intra was modified "
        f"from {base_params['tp_intra']} to {perturbed_params['tp_intra']}. "
        f"This suggests 'tp_intra' parameter may be disconnected from execution logic."
    )

def test_no_false_negatives():
    """
    Test Case 4: Verify that the test fails if and only if the results are identical.
    This meta-test ensures our 'different' logic is sound.
    """
    summary_a = {
        "final_equity": "5160304.1",
        "total_return": "0.290076025",
        "max_drawdown": "-0.03358338309209775",
        "calmar_ratio": "8.637486705985126892185289367"
    }
    summary_b = summary_a.copy()
    
    metrics = ["final_equity", "total_return", "max_drawdown", "calmar_ratio"]
    
    # Identical summaries
    different = any(str(summary_a[m]) != str(summary_b[m]) for m in metrics)
    assert not different, "Identical summaries should NOT be marked as different"
    
    # One metric different
    summary_c = summary_a.copy()
    summary_c["final_equity"] = "5160304.2"
    different = any(str(summary_a[m]) != str(summary_c[m]) for m in metrics)
    assert different, "Summaries with one different metric SHOULD be marked as different"
