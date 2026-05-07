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


def _run_cli(data_path: str, *, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "main_runner.py", *BACKTEST_ARGS, "--data-path", data_path]
    return subprocess.run(command, capture_output=True, text=True, cwd=REPO_ROOT, env=env)


def _load_json(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"Output is not valid JSON: {exc}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")


def test_cli_smoke_json_output(isolated_paths):
    result = _run_cli(isolated_paths["data"], env=isolated_paths["env"])
    assert result.returncode == 0, result.stderr

    output = _load_json(result)
    assert output["summary"]
    assert output["weekly_performance"]
    assert len(output["weekly_performance"]) > 0
    for key in ["final_equity", "total_return", "max_drawdown", "calmar_ratio"]:
        assert key in output["summary"]
        assert output["summary"][key] is not None
        assert str(output["summary"][key]) != ""
