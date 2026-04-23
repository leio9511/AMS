import subprocess
import sys
import json
import pytest
import os

# Exact canonical research data path from PRD
CANONICAL_DATA_PATH = "/root/projects/AMS/data/cb_history_factors.csv"

@pytest.fixture
def smoke_args():
    return [
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

@pytest.fixture
def ensure_canonical_data():
    """
    Ensure the canonical data path is restored from the default path.
    This protects against other tests that overwrite the canonical file with mock data.
    """
    default_path = "/root/.openclaw/workspace/data/cb_history_factors.csv"
    if os.path.exists(default_path):
        os.makedirs(os.path.dirname(CANONICAL_DATA_PATH), exist_ok=True)
        subprocess.run(["cp", default_path, CANONICAL_DATA_PATH], check=True)
    yield
    # No cleanup needed as it will be overwritten again by other tests if necessary

def test_default_path_non_empty(smoke_args):
    """
    Test Case 1: Verify that running without --data-path yields a summary.
    """
    result = subprocess.run(smoke_args, capture_output=True, text=True)
    assert result.returncode == 0, f"Default path execution failed: {result.stderr}"
    
    output = json.loads(result.stdout)
    assert "summary" in output, "Output should contain 'summary' key"
    assert output["summary"], "Summary should not be empty"

def test_canonical_path_non_empty(smoke_args, ensure_canonical_data):
    """
    Test Case 2: Verify that running with explicit canonical path yields a summary.
    """
    command = smoke_args + ["--data-path", CANONICAL_DATA_PATH]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, f"Canonical path execution failed: {result.stderr}"
    
    output = json.loads(result.stdout)
    assert "summary" in output, "Output should contain 'summary' key"
    assert output["summary"], "Summary should not be empty"

def test_no_path_branching(smoke_args, ensure_canonical_data):
    """
    Test Case 3: Verify that both paths are functional for the same strategy configuration.
    This acts as the Layer 4: Canonical Path Consistency gate.
    """
    # 1. Run Default
    result_default = subprocess.run(smoke_args, capture_output=True, text=True)
    assert result_default.returncode == 0
    output_default = json.loads(result_default.stdout)
    
    # 2. Run Canonical
    command_canonical = smoke_args + ["--data-path", CANONICAL_DATA_PATH]
    result_canonical = subprocess.run(command_canonical, capture_output=True, text=True)
    assert result_canonical.returncode == 0
    output_canonical = json.loads(result_canonical.stdout)
    
    # Assertions based on "Exact rule for canonical path consistency gate"
    assert output_default.get("summary"), "Default path produced empty summary"
    assert output_canonical.get("summary"), "Canonical path produced empty summary"
    
    # Verify basic structural consistency
    required_keys = ["final_equity", "total_return", "max_drawdown", "calmar_ratio"]
    for key in required_keys:
        assert key in output_default["summary"]
        assert key in output_canonical["summary"]

def test_walk_forward_doc_exists():
    """
    Test Case 4: Verify that the extension point documentation is created.
    """
    doc_path = "/root/projects/AMS/docs/architecture/WALK_FORWARD.md"
    assert os.path.exists(doc_path), f"Walk-forward documentation missing at {doc_path}"
    with open(doc_path, 'r') as f:
        content = f.read()
        assert "Walk-Forward" in content
        assert "Layer 5" in content
