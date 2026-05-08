import json
import os
import site
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_PROJECTS_AMS = "/root/" + "projects/AMS"
ROOT_OPENCLAW = "/root/" + ".openclaw"
OPENCLAW_WORKSPACE = ".openclaw/" + "workspace"
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


def _run_cli(extra_args, *, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(REPO_ROOT / "main_runner.py"), *BACKTEST_ARGS, *extra_args]
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    pythonpath_entries = [str(REPO_ROOT)]
    for site_path in site.getsitepackages() + [site.getusersitepackages()]:
        site_path_obj = Path(site_path)
        if site_path_obj.exists():
            pythonpath_entries.append(str(site_path_obj))
    existing_pythonpath = process_env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    process_env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    return subprocess.run(command, capture_output=True, text=True, cwd=cwd, env=process_env)


def _load_json(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"Output is not valid JSON: {exc}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")


def test_main_runtime_provider_default_runs_from_non_repo_cwd(isolated_paths, tmp_path):
    result = _run_cli([], cwd=tmp_path, env=isolated_paths["env"])
    assert result.returncode == 0, result.stderr

    output = _load_json(result)
    assert output["summary"]
    assert output["weekly_performance"]
    assert ROOT_PROJECTS_AMS not in result.stdout
    assert ROOT_OPENCLAW not in result.stdout
    assert OPENCLAW_WORKSPACE not in result.stdout
    assert not (REPO_ROOT / ".openclaw" / "workspace").exists()


def test_main_runtime_rejects_root_bound_cli_path_from_non_repo_cwd(isolated_paths, tmp_path):
    result = _run_cli(
        ["--data-path", ROOT_PROJECTS_AMS + "/data/cb_history_factors_jqdata.csv"],
        cwd=tmp_path,
        env=isolated_paths["env"],
    )

    assert result.returncode != 0
    assert "Path contains prohibited host layout coupling" in result.stderr
    assert "FileNotFoundError" not in result.stderr
    assert "does not exist" not in result.stderr
