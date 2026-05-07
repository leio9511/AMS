import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKTEST_ARGS = [
    "--strategy",
    "cb_rotation",
    "--start-date",
    "2025-01-06",
    "--end-date",
    "2025-01-10",
    "--capital",
    "4000000",
    "--top-n",
    "20",
    "--rebalance",
    "weekly",
    "--tp-mode",
    "both",
    "--tp-pos",
    "0.15",
    "--tp-intra",
    "0.12",
    "--sl",
    "-0.10",
    "--format",
    "json",
]


def run_cli(extra_args, *, cwd: Path = REPO_ROOT):
    command = [sys.executable, "main_runner.py", *BACKTEST_ARGS, *extra_args]
    return subprocess.run(command, capture_output=True, text=True, cwd=cwd)


def parse_json_output(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"Output is not valid JSON: {exc}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")


@pytest.mark.usefixtures("isolated_paths")
def test_default_path_non_empty(isolated_paths):
    result = run_cli([])
    assert result.returncode == 0, result.stderr

    output = parse_json_output(result)
    assert output["summary"]
    assert set(output["summary"]).issuperset({"final_equity", "total_return", "max_drawdown", "calmar_ratio"})


@pytest.mark.usefixtures("isolated_paths")
def test_canonical_path_non_empty(isolated_paths):
    result = run_cli(["--data-path", isolated_paths["data"]])
    assert result.returncode == 0, result.stderr

    output = parse_json_output(result)
    assert output["summary"]
    assert set(output["summary"]).issuperset({"final_equity", "total_return", "max_drawdown", "calmar_ratio"})


@pytest.mark.usefixtures("isolated_paths")
def test_no_path_branching(isolated_paths):
    default_result = run_cli([])
    assert default_result.returncode == 0, default_result.stderr
    default_output = parse_json_output(default_result)

    override_result = run_cli(["--data-path", isolated_paths["data"]])
    assert override_result.returncode == 0, override_result.stderr
    override_output = parse_json_output(override_result)

    assert default_output["summary"]
    assert override_output["summary"]
    assert set(default_output["summary"]) == set(override_output["summary"])
