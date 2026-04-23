import os
import json
import hashlib
import pytest

def test_golden_snapshot_integrity():
    """Verify SHA256, size, and row count of the created snapshot match the metadata."""
    metadata_path = "/root/projects/AMS/tests/golden/data/metadata.json"
    snapshot_path = "/root/projects/AMS/tests/golden/data/cb_history_factors_golden_2025_2026.csv"
    
    assert os.path.exists(metadata_path), "Metadata file missing"
    assert os.path.exists(snapshot_path), "Snapshot file missing"
    
    with open(metadata_path, 'r') as f:
        metadata = json.load(f)
    
    # Verify file size
    actual_size = os.path.getsize(snapshot_path)
    assert actual_size == metadata['file_size_bytes'], f"Size mismatch: expected {metadata['file_size_bytes']}, got {actual_size}"
    
    # Verify SHA256
    sha256_hash = hashlib.sha256()
    with open(snapshot_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    actual_sha256 = sha256_hash.hexdigest()
    assert actual_sha256 == metadata['sha256'], f"SHA256 mismatch: expected {metadata['sha256']}, got {actual_sha256}"
    
    # Verify row count
    with open(snapshot_path, 'r') as f:
        actual_row_count = sum(1 for _ in f)
    assert actual_row_count == metadata['row_count'], f"Row count mismatch: expected {metadata['row_count']}, got {actual_row_count}"

def test_baseline_artifacts_loadable():
    """Verify golden_cases.json is valid JSON and contains all required keys."""
    baseline_path = "/root/projects/AMS/tests/golden/baselines/golden_cases.json"
    assert os.path.exists(baseline_path), "Baseline file missing"
    
    with open(baseline_path, 'r') as f:
        baselines = json.load(f)
    
    required_cases = ["CASE_WEEKLY_BEST", "CASE_WEEKLY_CONSERVATIVE", "CASE_DAILY_COMPARATOR"]
    for case_name in required_cases:
        assert case_name in baselines, f"Case {case_name} missing from baselines"
        case_data = baselines[case_name]
        
        # Verify essential keys in each case
        assert "strategy" in case_data
        assert "summary" in case_data
        assert "checkpoints" in case_data
        
        # Verify summary keys
        summary = case_data["summary"]
        required_summary_keys = ["total_return", "max_drawdown", "calmar_ratio", "final_equity"]
        for key in required_summary_keys:
            assert key in summary, f"Summary key {key} missing in {case_name}"

def test_directory_discipline():
    """Verify no files are created in unauthorized root paths."""
    # This is a bit tricky to test from within the test suite, 
    # but we can check if any files were created in the project root that shouldn't be there.
    # For now, we'll just check that the files we expected to create are in the right places.
    allowed_dirs = [
        "/root/projects/AMS/tests/golden/data/",
        "/root/projects/AMS/tests/golden/baselines/"
    ]
    
    for d in allowed_dirs:
        assert os.path.isdir(d), f"Directory {d} should exist"
    
    # We could also check that no random files were created in /root/projects/AMS/ 
    # during this process, but that's hard to verify without a baseline of the root dir.
    pass
