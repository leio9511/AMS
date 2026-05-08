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


def run_cli(extra_args, *, cwd: Path = REPO_ROOT, env: dict | None = None):
    command = [sys.executable, str(REPO_ROOT / "main_runner.py"), *BACKTEST_ARGS, *extra_args]
    return subprocess.run(command, capture_output=True, text=True, cwd=cwd, env=env)


def parse_json_output(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"Output is not valid JSON: {exc}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")


@pytest.mark.usefixtures("isolated_paths")
def test_default_path_non_empty(isolated_paths):
    result = run_cli([], env=isolated_paths["env"])
    assert result.returncode == 0, result.stderr

    output = parse_json_output(result)
    assert output["summary"]
    assert set(output["summary"]).issuperset({"final_equity", "total_return", "max_drawdown", "calmar_ratio"})


@pytest.mark.usefixtures("isolated_paths")
def test_canonical_path_non_empty(isolated_paths):
    result = run_cli(["--data-path", isolated_paths["tushare_data"]], env=isolated_paths["env"])
    assert result.returncode == 0, result.stderr

    output = parse_json_output(result)
    assert output["summary"]
    assert set(output["summary"]).issuperset({"final_equity", "total_return", "max_drawdown", "calmar_ratio"})


@pytest.mark.usefixtures("isolated_paths")
def test_main_runtime_contract_outputs_are_cwd_independent(isolated_paths, tmp_path):
    repo_cwd_result = run_cli([], cwd=REPO_ROOT, env=isolated_paths["env"])
    assert repo_cwd_result.returncode == 0, repo_cwd_result.stderr
    repo_cwd_output = parse_json_output(repo_cwd_result)

    temp_cwd_result = run_cli([], cwd=tmp_path, env=isolated_paths["env"])
    assert temp_cwd_result.returncode == 0, temp_cwd_result.stderr
    temp_cwd_output = parse_json_output(temp_cwd_result)

    assert set(repo_cwd_output) == set(temp_cwd_output)
    assert set(repo_cwd_output["summary"]) == set(temp_cwd_output["summary"])
    assert set(repo_cwd_output["weekly_performance"][0]) == set(temp_cwd_output["weekly_performance"][0])
    assert repo_cwd_output == temp_cwd_output
