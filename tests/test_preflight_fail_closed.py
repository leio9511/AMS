import json
import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest


CANONICAL_EMPTY_MANIFEST = '{"pytest": []}\n'


def _write_fake_pytest(fake_pytest: Path) -> None:
    fake_pytest.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            : > "$PYTEST_ARGS_FILE"
            for arg in "$@"; do
                printf '%s\\n' "$arg" >> "$PYTEST_ARGS_FILE"
            done
            printf '1 passed\\n'
            """
        ),
        encoding="utf-8",
    )
    fake_pytest.chmod(fake_pytest.stat().st_mode | stat.S_IXUSR)


def _run_preflight_with_manifest(
    tmp_path: Path, *, manifest_text: str | None
) -> tuple[subprocess.CompletedProcess[str], Path]:
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
        (repo_root / "scripts" / "preflight_ignore_manifest.py").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    if manifest_text is not None:
        (temp_repo / "ignore_tests.json").write_text(manifest_text, encoding="utf-8")

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

    return result, args_capture_path


def test_preflight_fails_when_ignore_manifest_is_missing(tmp_path):
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=None,
    )

    assert result.returncode != 0
    assert not args_capture_path.exists()
    assert "PREFLIGHT FAILED" in result.stdout
    assert "ignore_tests.json" in result.stdout



def test_preflight_fails_before_pytest_on_malformed_json(tmp_path):
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text="{\n",
    )

    assert result.returncode != 0
    assert not args_capture_path.exists()
    assert "PREFLIGHT FAILED" in result.stdout



@pytest.mark.parametrize(
    "manifest_payload",
    [
        [],
        {},
        {"pytest": [], "extra": []},
        {"pytest": "tests/test_placeholder.py"},
        {"pytest": [123]},
    ],
)
def test_preflight_fails_before_pytest_on_structural_manifest_errors(
    tmp_path, manifest_payload
):
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=json.dumps(manifest_payload) + "\n",
    )

    assert result.returncode != 0
    assert not args_capture_path.exists()
    assert "PREFLIGHT FAILED" in result.stdout



@pytest.mark.parametrize(
    "manifest_text",
    [
        None,
        "{\n",
        json.dumps({}) + "\n",
        json.dumps({"pytest": [123]}) + "\n",
    ],
)
def test_preflight_does_not_invoke_pytest_when_manifest_validation_fails(
    tmp_path, manifest_text
):
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=manifest_text,
    )

    assert result.returncode != 0
    assert not args_capture_path.exists()



def test_preflight_runs_full_pytest_surface_for_canonical_empty_manifest(tmp_path):
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=CANONICAL_EMPTY_MANIFEST,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert args_capture_path.exists()
    assert args_capture_path.read_text(encoding="utf-8") == ""
    assert "✅ PREFLIGHT SUCCESS" in result.stdout
