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
            if [ -n "${PYTEST_BEHAVIOR:-}" ]; then
                case "$PYTEST_BEHAVIOR" in
                    fail-with-summary)
                        for arg in "$@"; do
                            printf '%s\\n' "$arg" >> "$PYTEST_ARGS_FILE"
                        done
                        cat <<'EOF'
============================= test session starts ==============================
collected 2 items

tests/test_alpha.py F                                                    [ 50%]
tests/test_beta.py .                                                     [100%]

=================================== FAILURES ===================================
______________________________ test_alpha_failure ______________________________

    def test_alpha_failure():
>       assert False
E       assert False

tests/test_alpha.py:3: AssertionError
=========================== short test summary info ============================
FAILED tests/test_alpha.py::test_alpha_failure - AssertionError: assert False
FAILED tests/test_gamma.py - AssertionError: synthetic file failure
========================= 2 failed, 1 passed in 0.12s ==========================
EOF
                        exit 1
                        ;;
                    success)
                        ;;
                    *)
                        echo "unknown PYTEST_BEHAVIOR: $PYTEST_BEHAVIOR" >&2
                        exit 97
                        ;;
                esac
            fi
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
    tmp_path: Path,
    *,
    manifest_text: str | None,
    args: list[str] | None = None,
    include_helper: bool = True,
    include_manifest: bool = True,
    python_source: str = "x = 1\n",
    pytest_behavior: str = "success",
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
    (temp_repo / "sample_module.py").write_text(python_source, encoding="utf-8")

    if include_helper:
        (scripts_dir / "preflight_ignore_manifest.py").write_text(
            (repo_root / "scripts" / "preflight_ignore_manifest.py").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )

    if include_manifest and manifest_text is not None:
        (temp_repo / "ignore_tests.json").write_text(manifest_text, encoding="utf-8")

    fake_pytest = fake_bin_dir / "pytest"
    _write_fake_pytest(fake_pytest)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin_dir}{os.pathsep}{env['PATH']}"
    env["PYTEST_ARGS_FILE"] = str(args_capture_path)
    env["PYTEST_BEHAVIOR"] = pytest_behavior

    command = ["bash", "preflight.sh", *(args or [])]
    result = subprocess.run(
        command,
        cwd=temp_repo,
        env=env,
        capture_output=True,
        text=True,
    )

    return result, args_capture_path


def test_preflight_runs_full_pytest_surface_for_missing_manifest(tmp_path):
    """PR-001_2_1 TDD Case 1: missing ignore_tests.json → exit 0, zero --ignore args."""
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=None,
        include_manifest=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert args_capture_path.exists()
    assert args_capture_path.read_text(encoding="utf-8") == ""
    assert "✅ PREFLIGHT SUCCESS" in result.stdout



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
        "a string manifest",
        42,
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
        "{\n",
        json.dumps({"pytest": [123]}) + "\n",
    ],
)
def test_preflight_does_not_invoke_pytest_when_manifest_validation_fails(
    tmp_path, manifest_text
):
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=manifest_text,
        include_manifest=manifest_text is not None,
    )

    assert result.returncode != 0
    assert not args_capture_path.exists()



def test_preflight_runs_full_pytest_surface_for_canonical_empty_manifest(tmp_path):
    """PR-001_2_1 TDD Case 2: {"pytest": []} → exit 0, zero --ignore args."""
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=CANONICAL_EMPTY_MANIFEST,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert args_capture_path.exists()
    assert args_capture_path.read_text(encoding="utf-8") == ""
    assert "✅ PREFLIGHT SUCCESS" in result.stdout



def test_preflight_rejects_unknown_mode_flags_and_fails_closed(tmp_path):
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=CANONICAL_EMPTY_MANIFEST,
        args=["--some-unknown-flag"],
    )

    assert result.returncode != 0
    assert not args_capture_path.exists()
    assert "PREFLIGHT FAILED" in result.stdout
    assert "Unknown preflight mode flag: --some-unknown-flag" in result.stdout



def test_preflight_report_all_emits_summary_block_when_pytest_fails(tmp_path):
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=CANONICAL_EMPTY_MANIFEST,
        args=["--report-all"],
        pytest_behavior="fail-with-summary",
    )

    assert result.returncode != 0
    assert args_capture_path.exists()
    stdout = result.stdout
    assert "=== REPORT-ALL SUMMARY ===" in stdout
    assert "MODE: report-all" in stdout
    assert "PYTEST RESULT:" in stdout
    assert "FAILED TESTS:" in stdout
    assert "SHORT SUMMARY INFO:" in stdout
    assert "=== END REPORT-ALL SUMMARY ===" in stdout
    assert "tests/test_alpha.py::test_alpha_failure" in stdout
    assert "tests/test_gamma.py" in stdout
    assert (
        "FAILED tests/test_alpha.py::test_alpha_failure - AssertionError: assert False"
        in stdout
    )



def test_preflight_runs_full_pytest_surface_for_manifest_missing_pytest_field(tmp_path):
    """PR-001_2_1 TDD Case 3: {} → exit 0, zero --ignore args."""
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=json.dumps({}) + "\n",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert args_capture_path.exists()
    assert args_capture_path.read_text(encoding="utf-8") == ""
    assert "✅ PREFLIGHT SUCCESS" in result.stdout


def test_preflight_logs_no_ignore_diagnostic_for_ignore_nothing_manifests(
    tmp_path,
):
    """PR-001_2_1: diagnostic log line appears for all ignore-nothing states.

    Uses a failing pytest behavior so the log file is preserved on exit.
    """
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=CANONICAL_EMPTY_MANIFEST,
        pytest_behavior="fail-with-summary",
    )

    log_path = tmp_path / "repo" / "build_preflight.log"
    assert log_path.exists()
    log_content = log_path.read_text(encoding="utf-8")
    assert (
        "Contract Compliance Test: no ignore entries — running full test surface (no --ignore args)"
        in log_content
    )


def test_preflight_report_all_still_hard_fails_before_pytest_on_prerequisite_error(
    tmp_path,
):
    result, args_capture_path = _run_preflight_with_manifest(
        tmp_path,
        manifest_text=CANONICAL_EMPTY_MANIFEST,
        args=["--report-all"],
        python_source="def broken(:\n    pass\n",
    )

    assert result.returncode != 0
    assert not args_capture_path.exists()
    assert "PREFLIGHT FAILED" in result.stdout
    assert "REPORT-ALL SUMMARY" not in result.stdout
    assert "SyntaxError" in result.stdout or "invalid syntax" in result.stdout
