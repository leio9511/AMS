import json
from pathlib import Path

import pytest

from scripts.preflight_ignore_manifest import build_pytest_ignore_args, load_manifest


EXPECTED_VALID_ENTRIES = [
    "tests/test_preflight_ignore_manifest.py",
    "tests/test_preflight_ignore_manifest_semantics.py",
]


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def manifest_path(tmp_path: Path) -> Path:
    return tmp_path / "ignore_tests.json"


@pytest.mark.parametrize(
    "entries",
    [
        ["tests/test_preflight_ignore_manifest.py", "tests/test_preflight_ignore_manifest.py"],
        ["tests/test_preflight_ignore_manifest_semantics.py", "tests/test_preflight_ignore_manifest.py", "tests/test_preflight_ignore_manifest_semantics.py"],
    ],
)
def test_rejects_duplicate_pytest_ignore_entry(
    manifest_path: Path, repo_root: Path, entries: list[str]
):
    manifest_path.write_text(json.dumps({"pytest": entries}) + "\n", encoding="utf-8")
    manifest = load_manifest(manifest_path)

    with pytest.raises(ValueError, match="Duplicate pytest ignore entry is invalid"):
        build_pytest_ignore_args(manifest, repo_root)



def test_rejects_nonexistent_pytest_file_entry(manifest_path: Path, repo_root: Path):
    manifest_path.write_text(
        json.dumps({"pytest": ["tests/does_not_exist_anywhere.py"]}) + "\n",
        encoding="utf-8",
    )
    manifest = load_manifest(manifest_path)

    with pytest.raises(ValueError, match="Pytest ignore entry does not exist"):
        build_pytest_ignore_args(manifest, repo_root)



@pytest.mark.parametrize(
    "entry, expected_message",
    [
        ("/tmp/evil.py", "Absolute pytest ignore entry is invalid"),
        ("tests/../outside.py", "Parent-traversing pytest ignore entry is invalid"),
        ("scripts/preflight_ignore_manifest.py", "Pytest ignore entry must live under tests/"),
    ],
)
def test_rejects_absolute_parent_traversal_and_outside_tests_paths(
    manifest_path: Path, repo_root: Path, entry: str, expected_message: str
):
    manifest_path.write_text(json.dumps({"pytest": [entry]}) + "\n", encoding="utf-8")
    manifest = load_manifest(manifest_path)

    with pytest.raises(ValueError, match=expected_message):
        build_pytest_ignore_args(manifest, repo_root)



@pytest.mark.parametrize(
    "entry, expected_message",
    [
        ("tests", "Pytest ignore entry must target a .py test file"),
        ("tests/validation", "Pytest ignore entry must target a .py test file"),
        ("tests/*.py", "Glob pytest ignore entry is invalid"),
        ("tests/test_preflight_ignore_manifest.txt", "Pytest ignore entry must target a .py test file"),
        ("tests/test_preflight_ignore_manifest.py::test_seed_manifest_matches_current_known_failure_surface", "Non-file pytest selector is invalid"),
    ],
)
def test_rejects_directory_glob_and_non_py_entries(
    manifest_path: Path, repo_root: Path, entry: str, expected_message: str
):
    manifest_path.write_text(json.dumps({"pytest": [entry]}) + "\n", encoding="utf-8")
    manifest = load_manifest(manifest_path)

    with pytest.raises(ValueError, match=expected_message):
        build_pytest_ignore_args(manifest, repo_root)



def test_accepts_existing_repo_relative_test_file_entries_only(
    manifest_path: Path, repo_root: Path
):
    manifest_path.write_text(json.dumps({"pytest": EXPECTED_VALID_ENTRIES}) + "\n", encoding="utf-8")
    manifest = load_manifest(manifest_path)

    assert build_pytest_ignore_args(manifest, repo_root) == [
        f"--ignore={entry}" for entry in EXPECTED_VALID_ENTRIES
    ]
