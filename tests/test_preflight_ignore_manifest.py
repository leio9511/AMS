import json
import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

from scripts.preflight_ignore_manifest import (
    build_pytest_ignore_args,
    load_manifest,
    main,
)


def test_helper_builds_ordered_pytest_ignore_args_from_fixture_manifest(tmp_path):
    manifest_path = tmp_path / "ignore_tests.json"
    manifest_entries = [
        "tests/custom_a.py",
        "tests/nested/custom_b.py",
    ]
    manifest_path.write_text(
        json.dumps({"pytest": manifest_entries}, indent=2) + "\n",
        encoding="utf-8",
    )
    for entry in manifest_entries:
        file_path = tmp_path / entry
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")

    manifest = load_manifest(manifest_path)

    assert build_pytest_ignore_args(manifest, tmp_path) == [
        f"--ignore={entry}" for entry in manifest_entries
    ]


def test_helper_cli_emits_ordered_pytest_ignore_args_from_fixture_manifest(tmp_path, capsys):
    manifest_path = tmp_path / "ignore_tests.json"
    manifest_entries = [
        "tests/custom_a.py",
        "tests/nested/custom_b.py",
    ]
    manifest_path.write_text(
        json.dumps({"pytest": manifest_entries}, indent=2) + "\n",
        encoding="utf-8",
    )
    for entry in manifest_entries:
        file_path = tmp_path / entry
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")

    exit_code = main(
        ["--manifest", str(manifest_path), "--repo-root", str(tmp_path)]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.splitlines() == [
        f"--ignore={entry}" for entry in manifest_entries
    ]
    assert captured.err == ""


def test_helper_returns_empty_ignore_args_for_empty_manifest(tmp_path):
    manifest_path = tmp_path / "ignore_tests.json"
    manifest_path.write_text('{"pytest": []}\n', encoding="utf-8")
    manifest = load_manifest(manifest_path)

    assert build_pytest_ignore_args(manifest, tmp_path) == []


def test_helper_treats_missing_manifest_as_empty_ignore_list(tmp_path):
    manifest = load_manifest(tmp_path / "nonexistent.json")
    assert manifest == {"pytest": []}
    assert build_pytest_ignore_args(manifest, tmp_path) == []


def test_helper_treats_missing_pytest_field_as_empty_ignore_list(tmp_path):
    manifest_path = tmp_path / "ignore_tests.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    manifest = load_manifest(manifest_path)
    assert manifest == {"pytest": []}
    assert build_pytest_ignore_args(manifest, tmp_path) == []


@pytest.mark.parametrize(
    "manifest_text",
    [
        pytest.param("not json\n", id="malformed_json"),
        pytest.param("[]\n", id="array_manifest"),
        pytest.param('"a string"\n', id="string_manifest"),
        pytest.param("42\n", id="number_manifest"),
        pytest.param('{"pytest": "not_a_list"}\n', id="non_list_pytest"),
        pytest.param('{"pytest": [123]}\n', id="non_string_entries"),
    ],
)
def test_helper_cli_rejects_malformed_or_structurally_invalid_manifest_payloads(
    tmp_path, capsys, manifest_text
):
    manifest_path = tmp_path / "ignore_tests.json"
    manifest_path.write_text(manifest_text, encoding="utf-8")

    exit_code = main(
        ["--manifest", str(manifest_path), "--repo-root", str(tmp_path)]
    )
    captured = capsys.readouterr()

    assert exit_code != 0
    assert captured.out == ""


def test_helper_cli_returns_zero_for_missing_manifest(tmp_path, capsys):
    exit_code = main(
        ["--manifest", str(tmp_path / "nonexistent.json"), "--repo-root", str(tmp_path)]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == ""
    assert captured.err == ""


def test_helper_cli_returns_zero_for_manifest_missing_pytest_field(tmp_path, capsys):
    manifest_path = tmp_path / "ignore_tests.json"
    manifest_path.write_text("{}\n", encoding="utf-8")

    exit_code = main(
        ["--manifest", str(manifest_path), "--repo-root", str(tmp_path)]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == ""
    assert captured.err == ""


def test_preflight_invokes_pytest_with_manifest_supplied_ignore_args(tmp_path):
    """PR-001_2_2 TDD Case 3: non-empty manifest → ordered --ignore= args through shell."""
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
    (temp_repo / "sample_module.py").write_text("x = 1\n", encoding="utf-8")
    (scripts_dir / "preflight_ignore_manifest.py").write_text(
        (repo_root / "scripts" / "preflight_ignore_manifest.py").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    manifest_entries = [
        "tests/custom_a.py",
        "tests/nested/custom_b.py",
    ]
    (temp_repo / "ignore_tests.json").write_text(
        json.dumps({"pytest": manifest_entries}, indent=2) + "\n",
        encoding="utf-8",
    )

    for entry in manifest_entries:
        file_path = temp_repo / entry
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            "def test_placeholder():\n    assert True\n", encoding="utf-8"
        )

    fake_pytest = fake_bin_dir / "pytest"
    fake_pytest.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            for arg in "$@"; do
                printf '%s\\n' "$arg" >> "$PYTEST_ARGS_FILE"
            done
            printf '1 passed\\n'
            """
        ),
        encoding="utf-8",
    )
    fake_pytest.chmod(fake_pytest.stat().st_mode | stat.S_IXUSR)

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
    assert args_capture_path.exists()
    captured_args = args_capture_path.read_text(encoding="utf-8").strip().splitlines()

    expected_ignores = [f"--ignore={entry}" for entry in manifest_entries]
    for ignore_arg in expected_ignores:
        assert ignore_arg in captured_args, (
            f"Expected {ignore_arg!r} in captured pytest args"
        )

    ignore_indices = [captured_args.index(arg) for arg in expected_ignores]
    assert ignore_indices == sorted(ignore_indices), (
        f"Ignore args must appear in manifest order; got indices {ignore_indices}"
    )

    assert "✅ PREFLIGHT SUCCESS" in result.stdout
