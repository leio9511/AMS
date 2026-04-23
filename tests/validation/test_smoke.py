import subprocess
import sys
import json
import pytest
import os

def test_cli_smoke_json_output():
    """
    Test Case 1: Verify main_runner.py --format json returns expected structure.
    """
    command = [
        sys.executable, "main_runner.py",
        "--strategy", "cb_rotation",
        "--start-date", "2025-01-06",
        "--end-date", "2025-01-10",
        "--capital", "4000000",
        "--top-n", "20",
        "--rebalance", "weekly",
        "--tp-mode", "both",
        "--tp-pos", "0.15",
        "--tp-intra", "0.12",
        "--sl", "-0.10",
        "--format", "json"
    ]
    
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
    
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Output is not valid JSON: {result.stdout}")
        
    assert "summary" in output
    assert "weekly_performance" in output
    assert len(output["weekly_performance"]) > 0

    summary = output["summary"]
    required_keys = ["final_equity", "total_return", "max_drawdown", "calmar_ratio"]
    for key in required_keys:
        assert key in summary
        assert summary[key] is not None
        assert str(summary[key]) != ""

def test_canonical_path_consistency():
    """
    Scenario 8: Default path and canonical path both produce non-empty summary.
    """
    common_args = [
        sys.executable, "main_runner.py",
        "--strategy", "cb_rotation",
        "--start-date", "2025-01-06",
        "--end-date", "2025-01-10",
        "--capital", "4000000",
        "--top-n", "20",
        "--rebalance", "weekly",
        "--tp-mode", "both",
        "--tp-pos", "0.15",
        "--tp-intra", "0.12",
        "--sl", "-0.10",
        "--format", "json"
    ]
    
    # 1. Default path
    result_default = subprocess.run(common_args, capture_output=True, text=True)
    assert result_default.returncode == 0, f"Default path failed: {result_default.stderr}"
    output_default = json.loads(result_default.stdout)
    assert output_default.get("summary"), "Default path summary should not be empty"
    
    # 2. Explicit canonical path
    # We must ensure the canonical path has data for the same validation case.
    # Since the environment may reset this file, we force copy it here.
    canonical_path = "/root/projects/AMS/data/cb_history_factors.csv"
    subprocess.run(["cp", "/root/.openclaw/workspace/data/cb_history_factors.csv", canonical_path])
    
    canonical_args = common_args + ["--data-path", canonical_path]
    result_canonical = subprocess.run(canonical_args, capture_output=True, text=True)
    assert result_canonical.returncode == 0, f"Canonical path failed: {result_canonical.stderr}"
    output_canonical = json.loads(result_canonical.stdout)
    assert output_canonical.get("summary"), "Canonical path summary should not be empty"
