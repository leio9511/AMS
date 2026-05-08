import json
from pathlib import Path

from ams.utils.path_resolver import resolve_repo_asset


FORBIDDEN_HOST_LAYOUT_TEXT = [
    "/root/" + "projects/AMS",
    "/root/" + ".openclaw",
    ".openclaw/" + "workspace",
]


def test_fixture_assets_resolve_repo_relative_independent_of_cwd(tmp_path, monkeypatch):
    fixture_relative = "tests/fixtures/fixture_rebalance_next_bar.csv"
    before = resolve_repo_asset(fixture_relative)
    assert before.exists()
    assert before.is_file()

    monkeypatch.chdir(tmp_path)
    after = resolve_repo_asset(fixture_relative)

    assert after == before
    assert after.exists()


def test_golden_assets_resolve_repo_relative_independent_of_cwd(tmp_path, monkeypatch):
    golden_csv_relative = "tests/golden/data/cb_history_factors_golden_2025_2026.csv"
    golden_cases_relative = "tests/golden/baselines/golden_cases.json"
    metadata_relative = "tests/golden/data/metadata.json"

    before = {
        "csv": resolve_repo_asset(golden_csv_relative),
        "cases": resolve_repo_asset(golden_cases_relative),
        "metadata": resolve_repo_asset(metadata_relative),
    }
    for path in before.values():
        assert path.exists()

    monkeypatch.chdir(tmp_path)
    after = {
        "csv": resolve_repo_asset(golden_csv_relative),
        "cases": resolve_repo_asset(golden_cases_relative),
        "metadata": resolve_repo_asset(metadata_relative),
    }

    assert after == before
    json.loads(after["cases"].read_text(encoding="utf-8"))
    json.loads(after["metadata"].read_text(encoding="utf-8"))


def test_golden_metadata_contains_no_host_layout_lineage():
    metadata_path = resolve_repo_asset("tests/golden/data/metadata.json")
    metadata_text = metadata_path.read_text(encoding="utf-8")
    metadata = json.loads(metadata_text)

    for pattern in FORBIDDEN_HOST_LAYOUT_TEXT:
        assert pattern not in metadata_text

    source_lineage = metadata.get("source_lineage", "")
    assert "AMS" in source_lineage
    assert "Repo-owned golden snapshot" in source_lineage
    assert metadata["sha256"]
    assert metadata["file_size_bytes"] > 0
    assert metadata["row_count"] > 0
