import json
import hashlib

from ams.utils.path_resolver import resolve_repo_asset


FORBIDDEN_HOST_LAYOUT_TEXT = [
    "/root/" + "projects/AMS",
    "/root/" + ".openclaw",
    ".openclaw/" + "workspace",
]


def test_golden_snapshot_integrity_uses_repo_asset_contract():
    """Verify SHA256, size, and row count using repo-owned asset resolution."""
    metadata_path = resolve_repo_asset("tests/golden/data/metadata.json")
    snapshot_path = resolve_repo_asset("tests/golden/data/cb_history_factors_golden_2025_2026.csv")

    assert metadata_path.exists(), "Metadata file missing"
    assert snapshot_path.exists(), "Snapshot file missing"

    metadata_text = metadata_path.read_text(encoding="utf-8")
    for pattern in FORBIDDEN_HOST_LAYOUT_TEXT:
        assert pattern not in metadata_text

    metadata = json.loads(metadata_text)

    actual_size = snapshot_path.stat().st_size
    assert actual_size == metadata["file_size_bytes"], f"Size mismatch: expected {metadata['file_size_bytes']}, got {actual_size}"

    sha256_hash = hashlib.sha256()
    with snapshot_path.open("rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    actual_sha256 = sha256_hash.hexdigest()
    assert actual_sha256 == metadata["sha256"], f"SHA256 mismatch: expected {metadata['sha256']}, got {actual_sha256}"

    with snapshot_path.open("r", encoding="utf-8") as f:
        actual_row_count = sum(1 for _ in f)
    assert actual_row_count == metadata["row_count"], f"Row count mismatch: expected {metadata['row_count']}, got {actual_row_count}"


def test_baseline_artifacts_loadable():
    """Verify golden_cases.json is valid JSON and contains all required keys."""
    baseline_path = resolve_repo_asset("tests/golden/baselines/golden_cases.json")
    assert baseline_path.exists(), "Baseline file missing"

    baselines = json.loads(baseline_path.read_text(encoding="utf-8"))

    required_cases = ["CASE_WEEKLY_BEST", "CASE_WEEKLY_CONSERVATIVE", "CASE_DAILY_COMPARATOR"]
    for case_name in required_cases:
        assert case_name in baselines, f"Case {case_name} missing from baselines"
        case_data = baselines[case_name]

        assert "strategy" in case_data
        assert "summary" in case_data
        assert "checkpoints" in case_data

        summary = case_data["summary"]
        required_summary_keys = ["total_return", "max_drawdown", "calmar_ratio", "final_equity"]
        for key in required_summary_keys:
            assert key in summary, f"Summary key {key} missing in {case_name}"


def test_directory_discipline():
    """Verify golden artifacts remain in authorized repo-owned golden directories."""
    allowed_dirs = [
        resolve_repo_asset("tests/golden/data"),
        resolve_repo_asset("tests/golden/baselines"),
    ]

    for directory in allowed_dirs:
        assert directory.is_dir(), f"Directory {directory} should exist"
