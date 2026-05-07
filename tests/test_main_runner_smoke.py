import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
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
    "10",
    "--rebalance",
    "daily",
    "--tp-mode",
    "both",
    "--tp-pos",
    "0.20",
    "--tp-intra",
    "0.08",
    "--sl",
    "-0.08",
    "--format",
    "json",
]


def _fixture_data_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "cb_history_factors.csv"


def _mutable_fixture_path(tmp_path: Path) -> Path:
    mutable_dir = tmp_path / "mutable-data"
    mutable_dir.mkdir()
    mutable_path = mutable_dir / "cb_history_factors.csv"
    mutable_path.write_text(_fixture_data_path().read_text(encoding="utf-8"), encoding="utf-8")
    return mutable_path


def _run_cli(extra_args=None, *, env: dict | None = None):
    command = [sys.executable, "main_runner.py", *BACKTEST_ARGS]
    if extra_args:
        command.extend(extra_args)
    return subprocess.run(command, capture_output=True, text=True, cwd=REPO_ROOT, env=env)


def test_real_cli_execution_smoke(tmp_path, isolated_paths):
    explicit_data_path = _mutable_fixture_path(tmp_path)
    result = _run_cli(["--data-path", str(explicit_data_path)], env=isolated_paths["env"])
    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Output is not valid JSON: {result.stdout}")

    assert "summary" in output
    assert "weekly_performance" in output
    assert "total_return" in output["summary"]


def test_canonical_data_path_usage():
    result = subprocess.run([sys.executable, "main_runner.py", "--help"], capture_output=True, text=True, cwd=REPO_ROOT)
    assert "provider contract precedence" in result.stdout
    assert "configured default provider's project-local dataset path" in result.stdout
    assert "/root/projects/AMS/data/cb_history_factors_jqdata.csv" not in result.stdout
    assert "/root/.openclaw/workspace/data/cb_history_factors.csv" not in result.stdout


def test_json_format_integrity(tmp_path, isolated_paths):
    explicit_data_path = _mutable_fixture_path(tmp_path)
    result = _run_cli(["--data-path", str(explicit_data_path)], env=isolated_paths["env"])
    assert result.returncode == 0

    output = json.loads(result.stdout)
    summary = output["summary"]

    assert isinstance(summary["total_return"], str)
    assert isinstance(summary["max_drawdown"], str)
    assert isinstance(summary["final_equity"], str)

    if output["weekly_performance"]:
        week = output["weekly_performance"][0]
        assert isinstance(week["total_assets"], str)
        assert isinstance(week["weekly_profit_pct"], str)
