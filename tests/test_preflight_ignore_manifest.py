import json
import os
import stat
import subprocess
import textwrap
from pathlib import Path

from scripts.preflight_ignore_manifest import build_pytest_ignore_args, load_manifest

EXPECTED_PYTEST_IGNORE_ENTRIES = [
    "tests/test_data_source.py",
    "tests/test_execution_arbitration.py",
    "tests/test_execution_semantics_stop_loss.py",
    "tests/test_finance_fetcher.py",
    "tests/test_main_runner.py",
    "tests/test_main_runner_smoke.py",
    "tests/test_order_semantics_e2e.py",
    "tests/validation/test_golden_integrity.py",
    "tests/validation/test_path_consistency.py",
    "tests/validation/test_smoke.py",
]


def _write_fake_pytest(fake_pytest: Path) -> None:
    fake_pytest.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            printf '%s\\n' "$@" > "$PYTEST_ARGS_FILE"
            printf '1 passed\\n'
            """
        ),
        encoding="utf-8",
    )
    fake_pytest.chmod(fake_pytest.stat().st_mode | stat.S_IXUSR)



def test_seed_manifest_matches_current_known_failure_surface():
    repo_root = Path(__file__).resolve().parents[1]
    manifest = json.loads((repo_root / "ignore_tests.json").read_text(encoding="utf-8"))

    assert manifest == {"pytest": EXPECTED_PYTEST_IGNORE_ENTRIES}



def test_helper_builds_ordered_pytest_ignore_args_from_seed_manifest():
    repo_root = Path(__file__).resolve().parents[1]
    manifest = load_manifest(repo_root / "ignore_tests.json")

    assert build_pytest_ignore_args(manifest, repo_root) == [
        f"--ignore={entry}" for entry in EXPECTED_PYTEST_IGNORE_ENTRIES
    ]



def test_helper_emits_no_ignore_args_for_canonical_empty_manifest(tmp_path):
    manifest_path = tmp_path / "ignore_tests.json"
    manifest_path.write_text('{"pytest": []}\n', encoding="utf-8")
    manifest = load_manifest(manifest_path)

    assert build_pytest_ignore_args(manifest, tmp_path) == []



def test_preflight_invokes_pytest_with_manifest_supplied_ignore_args(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    temp_repo = tmp_path / "repo"
    scripts_dir = temp_repo / "scripts"
    tests_dir = temp_repo / "tests"
    fake_bin_dir = tmp_path / "bin"
    args_capture_path = tmp_path / "pytest_args.txt"
    manifest_entries = [
        "tests/custom_a.py",
        "tests/nested/custom_b.py",
    ]

    scripts_dir.mkdir(parents=True)
    (tests_dir / "nested").mkdir(parents=True)
    fake_bin_dir.mkdir(parents=True)

    (temp_repo / "preflight.sh").write_text(
        (repo_root / "preflight.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (scripts_dir / "preflight_ignore_manifest.py").write_text(
        (repo_root / "scripts" / "preflight_ignore_manifest.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (temp_repo / "ignore_tests.json").write_text(
        json.dumps({"pytest": manifest_entries}, indent=2) + "\n",
        encoding="utf-8",
    )

    for entry in manifest_entries:
        file_path = temp_repo / entry
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")

    fake_pytest = fake_bin_dir / "pytest"
    _write_fake_pytest(fake_pytest)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin_dir}{os.pathsep}{env['PATH']}"
    env["PYTEST_ARGS_FILE"] = str(args_capture_path)

    result = subprocess.run(
        ["bash", "preflight.sh"],
        cwd=temp_repo,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert args_capture_path.read_text(encoding="utf-8").splitlines() == [
        f"--ignore={entry}" for entry in manifest_entries
    ]



def test_preflight_fails_closed_when_manifest_is_missing(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    temp_repo = tmp_path / "repo"
    scripts_dir = temp_repo / "scripts"
    fake_bin_dir = tmp_path / "bin"
    args_capture_path = tmp_path / "pytest_args.txt"

    scripts_dir.mkdir(parents=True)
    fake_bin_dir.mkdir(parents=True)

    (temp_repo / "preflight.sh").write_text(
        (repo_root / "preflight.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (scripts_dir / "preflight_ignore_manifest.py").write_text(
        (repo_root / "scripts" / "preflight_ignore_manifest.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    fake_pytest = fake_bin_dir / "pytest"
    _write_fake_pytest(fake_pytest)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin_dir}{os.pathsep}{env['PATH']}"
    env["PYTEST_ARGS_FILE"] = str(args_capture_path)

    result = subprocess.run(
        ["bash", "preflight.sh"],
        cwd=temp_repo,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert not args_capture_path.exists()
    assert "PREFLIGHT FAILED" in result.stdout
    assert "ignore_tests.json" in result.stdout
