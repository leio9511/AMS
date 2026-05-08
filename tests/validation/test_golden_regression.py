import subprocess
import sys
import json
import pytest
import os
import site

from ams.utils.path_resolver import resolve_repo_asset, get_repo_root


REPO_ROOT = get_repo_root()
GOLDEN_CASES_FILE = resolve_repo_asset("tests/golden/baselines/golden_cases.json")
GOLDEN_DATA_PATH = resolve_repo_asset("tests/golden/data/cb_history_factors_golden_2025_2026.csv")


def load_golden_cases():
    if not GOLDEN_CASES_FILE.exists():
        return {}
    return json.loads(GOLDEN_CASES_FILE.read_text(encoding="utf-8"))


def test_golden_cases_use_repo_owned_golden_data_path():
    assert GOLDEN_DATA_PATH.exists()
    assert GOLDEN_CASES_FILE.exists()
    assert GOLDEN_DATA_PATH == resolve_repo_asset("tests/golden/data/cb_history_factors_golden_2025_2026.csv")
    assert GOLDEN_CASES_FILE == resolve_repo_asset("tests/golden/baselines/golden_cases.json")


@pytest.mark.parametrize("case_name, case_data", load_golden_cases().items())
def test_golden_cases(case_name, case_data):
    """
    Layer 2 validation - Exact baseline matching for golden cases.
    Verifies that the backtest results exactly match the frozen baselines.
    """
    command = [
        sys.executable, str(REPO_ROOT / "main_runner.py"),
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
        "--data-path", str(GOLDEN_DATA_PATH),
        "--format", "json"
    ]

    env = os.environ.copy()
    user_site = site.getusersitepackages()
    env["PYTHONPATH"] = f"{REPO_ROOT}:{user_site}"
    result = subprocess.run(command, capture_output=True, text=True, cwd=REPO_ROOT, env=env)
    assert result.returncode == 0, f"Command failed for {case_name}: {result.stderr}"

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Output for {case_name} is not valid JSON: {result.stdout}")

    summary = output["summary"]
    baseline_summary = case_data["summary"]

    required_summary_keys = ["final_equity", "total_return", "max_drawdown", "calmar_ratio"]
    for key in required_summary_keys:
        expected_val = baseline_summary.get(key)
        actual_val = summary.get(key)
        assert str(actual_val) == str(expected_val), f"Summary field {key} mismatch for {case_name}. Expected {expected_val}, got {actual_val}"

    actual_weekly = output["weekly_performance"]
    expected_checkpoints = case_data["checkpoints"]

    for expected in expected_checkpoints:
        week_ending = expected["week_ending"]
        actual = next((w for w in actual_weekly if w["week_ending"] == week_ending), None)
        assert actual is not None, f"Checkpoint week {week_ending} not found in output for {case_name}"

        for key in ["total_assets", "weekly_profit_pct", "cumulative_pct"]:
            expected_val = expected.get(key)
            actual_val = actual.get(key)
            assert str(actual_val) == str(expected_val), f"Checkpoint field {key} mismatch for {case_name} at {week_ending}. Expected {expected_val}, got {actual_val}"
