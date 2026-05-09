import json
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
