import csv
import json
import hashlib

from ams.utils.path_resolver import resolve_repo_asset


FORBIDDEN_HOST_LAYOUT_TEXT = [
    "/root/" + "projects/AMS",
    "/root/" + ".openclaw",
    ".openclaw/" + "workspace",
]

WITNESS_RELATIVE_PATH = "tests/golden/data/redeem_risk_split_state_witness.csv"


def _parse_csv_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"Unsupported boolean literal in witness artifact: {value}")


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

    assert metadata["source_lineage"] == (
        "Repo-owned golden snapshot derived from AMS product backtest data and frozen for Phase 1C validation on 2026-04-23"
    )


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


def test_golden_metadata_does_not_bake_in_root_lineage():
    """
    Test Case 1: JSON payloads or report assertions shouldn't fail because 
    the expected path output string lacks `/root/...`.
    """
    metadata_path = resolve_repo_asset("tests/golden/data/metadata.json")
    metadata_text = metadata_path.read_text(encoding="utf-8")
    metadata = json.loads(metadata_text)
    
    assert "source_lineage" in metadata
    assert "Repo-owned golden snapshot" in metadata["source_lineage"]
    
    # Assert structural validation fields confirm contract correctness without absolute prefixes
    for key, value in metadata.items():
        if isinstance(value, str):
            for pattern in FORBIDDEN_HOST_LAYOUT_TEXT:
                assert pattern not in value, f"Host layout pattern found in {key}: {value}"


def test_golden_split_state_witness_metadata_is_witness_scoped():
    metadata_path = resolve_repo_asset("tests/golden/data/metadata.json")
    witness_path = resolve_repo_asset(WITNESS_RELATIVE_PATH)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert metadata["witness_filename"] == "redeem_risk_split_state_witness.csv"
    assert witness_path.name == metadata["witness_filename"]
    assert metadata["witness_row_count"] == 1
    assert metadata["witness_split_state_row_count"] == 1
    assert metadata["witness_redeem_risk_true_count"] == 1
    assert metadata["witness_is_redeemed_false_count"] == 1
    assert metadata["witness_is_st_false_count"] == 1

    snapshot_contract_keys = {"sha256", "file_size_bytes", "row_count", "source_lineage"}
    witness_contract_keys = {
        "witness_filename",
        "witness_row_count",
        "witness_split_state_row_count",
        "witness_redeem_risk_true_count",
        "witness_is_redeemed_false_count",
        "witness_is_st_false_count",
    }

    assert snapshot_contract_keys.issubset(metadata)
    assert witness_contract_keys.issubset(metadata)
    assert not snapshot_contract_keys & {key for key in metadata if key.startswith("witness_")}


def test_golden_split_state_witness_asset_is_repo_owned_and_loadable():
    witness_path = resolve_repo_asset(WITNESS_RELATIVE_PATH)
    golden_data_dir = resolve_repo_asset("tests/golden/data")

    assert witness_path.exists(), "Witness artifact missing"
    assert witness_path.is_file(), "Witness artifact should be a file"
    assert witness_path.suffix == ".csv"
    assert witness_path.parent == golden_data_dir

    with witness_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1, f"Witness artifact should contain exactly one data row, got {len(rows)}"


def test_golden_split_state_witness_encodes_redeem_risk_before_terminal_state():
    witness_path = resolve_repo_asset(WITNESS_RELATIVE_PATH)

    with witness_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    split_state_rows = [
        row
        for row in rows
        if _parse_csv_bool(row["redeem_risk"])
        and not _parse_csv_bool(row["is_redeemed"])
    ]

    assert len(split_state_rows) == 1, (
        "Witness artifact must encode exactly one split-state row with "
        "redeem_risk=True and is_redeemed=False"
    )

    split_state_row = split_state_rows[0]
    if "is_st" in split_state_row:
        assert _parse_csv_bool(split_state_row["is_st"]) is False
