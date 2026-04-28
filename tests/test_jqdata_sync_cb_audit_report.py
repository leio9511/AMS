"""Tests for PR-003: Validator Stage, Root/Secondary Formulas, and Audit Reporting.

Covers the TDD blueprint from the PR contract:
- test_formula_premium_source_truncation
- test_formula_is_st_gap
- test_full_audit_report_schema
- test_audit_isolation_integrity
"""

import json
import os
import tempfile
from unittest.mock import patch

import pandas as pd
import pytest

from etl.jqdata_sync_cb import (
    CBETLAuditRunner,
    DATA_PATH,
)


# ---------------------------------------------------------------------------
# Helpers: Build complete, schema-compliant mock stage results
# ---------------------------------------------------------------------------

def _make_pass_source() -> dict:
    return {
        "status": "PASS", "failure_type": "NONE",
        "basic_info_row_count": 10, "all_bond_security_count": 5,
        "price_row_count": 10, "price_unique_bond_count": 5,
        "premium_source_row_count": 10, "premium_source_unique_bond_count": 5,
        "is_st_source_row_count": 10, "is_st_source_unique_underlying_count": 5,
        "redemption_source_row_count": 10, "redemption_source_unique_bond_count": 5,
        "message": "",
    }


def _make_pass_supportability(supportable=10, unique=5) -> dict:
    return {
        "status": "PASS", "failure_type": "NONE",
        "supportable_row_count": supportable, "supportable_unique_bond_count": unique,
        "outside_basic_info_row_count": 0, "outside_basic_info_unique_bond_count": 0,
        "missing_company_code_legacy_row_count": 0, "missing_company_code_legacy_unique_bond_count": 0,
        "unexpected_contract_regression_row_count": 0, "unexpected_contract_regression_unique_bond_count": 0,
        "missing_underlying_row_count": 0, "missing_underlying_unique_bond_count": 0,
        "message": "",
    }


def _make_pass_premium() -> dict:
    return {
        "status": "PASS", "failure_type": "NONE",
        "premium_joined_row_count": 10, "premium_joined_unique_bond_count": 5,
        "missing_premium_row_count": 0, "missing_premium_unique_bond_count": 0,
        "missing_premium_ratio": 0.0,
        "message": "",
    }


def _make_pass_is_st() -> dict:
    return {
        "status": "PASS", "failure_type": "NONE",
        "is_st_joined_row_count": 10, "is_st_joined_unique_bond_count": 5,
        "missing_is_st_row_count": 0, "missing_is_st_unique_bond_count": 0,
        "missing_is_st_ratio": 0.0,
        "message": "",
    }


def _make_pass_redemption() -> dict:
    return {
        "status": "PASS", "failure_type": "NONE",
        "redemption_joined_row_count": 10, "redemption_joined_unique_bond_count": 5,
        "missing_redemption_row_count": 0, "missing_redemption_unique_bond_count": 0,
        "missing_redemption_ratio": 0.0,
        "message": "",
    }


def _make_pass_validator() -> dict:
    return {
        "status": "PASS", "failure_type": "NONE",
        "schema_validator_status": "PASS",
        "semantic_validator_status": "PASS",
        "drift_validator_status": "PASS",
        "schema_validator_message": "",
        "semantic_validator_message": "",
        "drift_validator_message": "",
        "message": "",
    }


# ---------------------------------------------------------------------------
# Test 1: PREMIUM_SOURCE_TRUNCATION formula
# ---------------------------------------------------------------------------

def test_formula_premium_source_truncation():
    """PRD 3.5.4: Verify PREMIUM_SOURCE_TRUNCATION is identified as root blocker.

    Conditions:
      - supportable_row_count >= 50000
      - premium_source_row_count == 5000
      - missing_premium_ratio >= 0.80
    """
    runner = CBETLAuditRunner("2025-01-01", "2025-01-31")

    premium_truncated = {
        "status": "FAIL",
        "failure_type": "PREMIUM_SOURCE_TRUNCATION",
        "premium_joined_row_count": 5000,
        "premium_joined_unique_bond_count": 500,
        "missing_premium_row_count": 45000,
        "missing_premium_unique_bond_count": 500,
        "missing_premium_ratio": 0.9,
        "message": "Premium source appears truncated (supportable>=50000, source_rows==5000, missing_ratio>=0.80)",
    }

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": _make_pass_supportability(supportable=50000, unique=500),
        "premium_join_summary": premium_truncated,
        "is_st_join_summary": _make_pass_is_st(),
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": _make_pass_validator(),
    }

    runner.pipeline.context["premium_source_row_count"] = 5000

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    root_blocker_types = [b["type"] for b in report["root_blockers"]]
    assert "PREMIUM_SOURCE_TRUNCATION" in root_blocker_types, \
        f"Expected PREMIUM_SOURCE_TRUNCATION in root_blockers, got: {root_blocker_types}"

    # Verify evidence
    trunc_blocker = next(b for b in report["root_blockers"] if b["type"] == "PREMIUM_SOURCE_TRUNCATION")
    assert trunc_blocker["stage"] == "C"
    assert trunc_blocker["evidence"]["supportable_row_count"] == 50000
    assert trunc_blocker["evidence"]["premium_source_row_count"] == 5000
    assert trunc_blocker["evidence"]["missing_premium_ratio"] == 0.9

    # Downstream missing premium rows should be secondary, not root blocker
    assert any(
        f["type"] == "MISSING_PREMIUM_RATE_ROWS" for f in report["secondary_findings"]
    ), "MISSING_PREMIUM_RATE_ROWS should be a secondary finding"

    assert report["final_status"] == "FAIL_ROOT_BLOCKER"


# ---------------------------------------------------------------------------
# Test 2: IS_ST_SOURCE_GAP formula
# ---------------------------------------------------------------------------

def test_formula_is_st_gap():
    """PRD 3.5.6: Verify IS_ST_SOURCE_GAP is identified as root blocker.

    Conditions:
      - supportable_row_count > 0
      - missing_is_st_ratio >= 0.20
    """
    runner = CBETLAuditRunner("2025-01-01", "2025-01-31")

    is_st_gapped = {
        "status": "FAIL",
        "failure_type": "IS_ST_SOURCE_GAP",
        "is_st_joined_row_count": 400,
        "is_st_joined_unique_bond_count": 400,
        "missing_is_st_row_count": 600,
        "missing_is_st_unique_bond_count": 600,
        "missing_is_st_ratio": 0.60,
        "message": "is_st coverage is low.",
    }

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": _make_pass_supportability(supportable=1000, unique=1000),
        "premium_join_summary": _make_pass_premium(),
        "is_st_join_summary": is_st_gapped,
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": _make_pass_validator(),
    }

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    root_blocker_types = [b["type"] for b in report["root_blockers"]]
    assert "IS_ST_SOURCE_GAP" in root_blocker_types, \
        f"Expected IS_ST_SOURCE_GAP in root_blockers, got: {root_blocker_types}"

    # Verify evidence
    is_st_blocker = next(b for b in report["root_blockers"] if b["type"] == "IS_ST_SOURCE_GAP")
    assert is_st_blocker["stage"] == "D"
    assert is_st_blocker["evidence"]["supportable_row_count"] == 1000
    assert is_st_blocker["evidence"]["missing_is_st_ratio"] == 0.60

    # Verify downstream missing is_st rows are secondary
    assert any(
        f["type"] == "MISSING_IS_ST_ROWS" for f in report["secondary_findings"]
    ), "MISSING_IS_ST_ROWS should be a secondary finding"

    assert report["final_status"] == "FAIL_ROOT_BLOCKER"


def test_is_st_gap_threshold_not_triggered_below_20_pct():
    """Verify IS_ST_SOURCE_GAP is NOT triggered when ratio < 0.20."""
    runner = CBETLAuditRunner("2025-01-01", "2025-01-31")

    is_st_ok = {
        "status": "PASS",
        "failure_type": "NONE",
        "is_st_joined_row_count": 900,
        "is_st_joined_unique_bond_count": 900,
        "missing_is_st_row_count": 100,
        "missing_is_st_unique_bond_count": 100,
        "missing_is_st_ratio": 0.10,
        "message": "",
    }

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": _make_pass_supportability(),
        "premium_join_summary": _make_pass_premium(),
        "is_st_join_summary": is_st_ok,
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": _make_pass_validator(),
    }

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    root_blocker_types = [b["type"] for b in report["root_blockers"]]
    assert "IS_ST_SOURCE_GAP" not in root_blocker_types, \
        f"IS_ST_SOURCE_GAP should NOT be triggered at 10% missing, got: {root_blocker_types}"


# ---------------------------------------------------------------------------
# Test 3: Full audit report schema
# ---------------------------------------------------------------------------

def test_full_audit_report_schema():
    """PRD 3.9 & Section 7: Verify all required top-level and nested fields exist.

    Runs the audit runner with mocked stages and checks every field from
    the hardcoded content definitions in PRD Section 7.
    """
    runner = CBETLAuditRunner("2025-01-06", "2025-01-07")

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": _make_pass_supportability(),
        "premium_join_summary": _make_pass_premium(),
        "is_st_join_summary": _make_pass_is_st(),
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": _make_pass_validator(),
    }

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    # --- PRD Section 7: required_top_level_json_fields ---
    top_level_fields = [
        "execution_mode", "start_date", "end_date", "final_status",
        "non_promotion_disclaimer", "source_coverage", "supportability_summary",
        "premium_join_summary", "is_st_join_summary", "redemption_summary",
        "validator_summary", "root_blockers", "secondary_findings",
    ]
    for field in top_level_fields:
        assert field in report, f"Missing top-level field: {field}"

    assert report["execution_mode"] == "audit"
    assert report["start_date"] == "2025-01-06"
    assert report["end_date"] == "2025-01-07"
    assert "diagnostic only" in report["non_promotion_disclaimer"]
    assert "No canonical dataset promotion" in report["non_promotion_disclaimer"]

    # --- required_source_coverage_schema ---
    sc = report["source_coverage"]
    for field in ["status", "failure_type", "basic_info_row_count",
                  "all_bond_security_count", "price_row_count",
                  "price_unique_bond_count", "premium_source_row_count",
                  "premium_source_unique_bond_count", "is_st_source_row_count",
                  "is_st_source_unique_underlying_count",
                  "redemption_source_row_count", "redemption_source_unique_bond_count",
                  "message"]:
        assert field in sc, f"Missing source_coverage field: {field}"
    assert sc["status"] in ("PASS", "FAIL", "NOT_RUN")
    assert sc["failure_type"] in ("NONE", "SOURCE_AUTH_FAILURE", "PRICE_SOURCE_UNREADABLE")

    # --- required_supportability_summary_schema ---
    ss = report["supportability_summary"]
    for field in ["status", "failure_type", "supportable_row_count",
                  "supportable_unique_bond_count", "outside_basic_info_row_count",
                  "outside_basic_info_unique_bond_count",
                  "missing_company_code_legacy_row_count",
                  "missing_company_code_legacy_unique_bond_count",
                  "unexpected_contract_regression_row_count",
                  "unexpected_contract_regression_unique_bond_count",
                  "missing_underlying_row_count", "missing_underlying_unique_bond_count",
                  "message"]:
        assert field in ss, f"Missing supportability_summary field: {field}"
    assert ss["status"] in ("PASS", "FAIL", "NOT_RUN")
    assert ss["failure_type"] in ("NONE", "SUPPORTABILITY_REGRESSION")

    # --- required_premium_join_summary_schema ---
    pj = report["premium_join_summary"]
    for field in ["status", "failure_type", "premium_joined_row_count",
                  "premium_joined_unique_bond_count", "missing_premium_row_count",
                  "missing_premium_unique_bond_count", "missing_premium_ratio",
                  "message"]:
        assert field in pj, f"Missing premium_join_summary field: {field}"
    assert pj["status"] in ("PASS", "FAIL", "NOT_RUN")
    assert pj["failure_type"] in ("NONE", "PREMIUM_SOURCE_TRUNCATION",
                                  "PREMIUM_RATE_MISSING_BROAD_COVERAGE")

    # --- required_is_st_join_summary_schema ---
    is_st = report["is_st_join_summary"]
    for field in ["status", "failure_type", "is_st_joined_row_count",
                  "is_st_joined_unique_bond_count", "missing_is_st_row_count",
                  "missing_is_st_unique_bond_count", "missing_is_st_ratio",
                  "message"]:
        assert field in is_st, f"Missing is_st_join_summary field: {field}"
    assert is_st["status"] in ("PASS", "FAIL", "NOT_RUN")
    assert is_st["failure_type"] in ("NONE", "IS_ST_SOURCE_GAP")

    # --- required_redemption_summary_schema ---
    rd = report["redemption_summary"]
    for field in ["status", "failure_type", "redemption_joined_row_count",
                  "redemption_joined_unique_bond_count", "missing_redemption_row_count",
                  "missing_redemption_unique_bond_count", "missing_redemption_ratio",
                  "message"]:
        assert field in rd, f"Missing redemption_summary field: {field}"
    assert rd["status"] in ("PASS", "FAIL", "NOT_RUN")
    assert rd["failure_type"] in ("NONE", "REDEMPTION_SOURCE_GAP")

    # --- required_validator_summary_schema ---
    vs = report["validator_summary"]
    for field in ["status", "failure_type", "schema_validator_status",
                  "semantic_validator_status", "drift_validator_status",
                  "schema_validator_message", "semantic_validator_message",
                  "drift_validator_message", "message"]:
        assert field in vs, f"Missing validator_summary field: {field}"
    assert vs["status"] in ("PASS", "FAIL", "NOT_RUN")
    assert vs["failure_type"] in ("NONE", "VALIDATOR_SCHEMA_FAILURE",
                                  "VALIDATOR_SEMANTIC_FAILURE", "VALIDATOR_DRIFT_FAILURE")
    assert vs["schema_validator_status"] in ("PASS", "FAIL", "NOT_RUN")
    assert vs["semantic_validator_status"] in ("PASS", "FAIL", "NOT_RUN")
    assert vs["drift_validator_status"] in ("PASS", "FAIL", "NOT_RUN")

    # --- root_blockers and secondary_findings are lists ---
    assert isinstance(report["root_blockers"], list)
    assert isinstance(report["secondary_findings"], list)

    # --- final_status ---
    assert report["final_status"] in ("PASS", "FAIL_ROOT_BLOCKER", "FAIL_SECONDARY_ONLY")


def test_full_audit_report_schema_root_blocker_item():
    """Verify root blocker items match required schema from PRD Section 7."""
    runner = CBETLAuditRunner("2025-01-01", "2025-01-31")

    premium_truncated = {
        "status": "FAIL", "failure_type": "PREMIUM_SOURCE_TRUNCATION",
        "premium_joined_row_count": 5000, "premium_joined_unique_bond_count": 500,
        "missing_premium_row_count": 45000, "missing_premium_unique_bond_count": 500,
        "missing_premium_ratio": 0.9,
        "message": "Premium source appears truncated",
    }

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": _make_pass_supportability(supportable=50000, unique=500),
        "premium_join_summary": premium_truncated,
        "is_st_join_summary": _make_pass_is_st(),
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": _make_pass_validator(),
    }

    runner.pipeline.context["premium_source_row_count"] = 5000

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    assert len(report["root_blockers"]) > 0
    blocker = report["root_blockers"][0]

    # required_root_blocker_item_schema
    required_fields = {"type", "stage", "trigger", "evidence"}
    assert required_fields.issubset(set(blocker.keys())), \
        f"Root blocker item missing fields: {required_fields - set(blocker.keys())}"

    valid_types = {
        "SOURCE_AUTH_FAILURE", "PRICE_SOURCE_UNREADABLE",
        "SUPPORTABILITY_REGRESSION", "PREMIUM_SOURCE_TRUNCATION",
        "PREMIUM_RATE_MISSING_BROAD_COVERAGE", "IS_ST_SOURCE_GAP",
        "REDEMPTION_SOURCE_GAP", "VALIDATOR_SCHEMA_FAILURE",
        "VALIDATOR_SEMANTIC_FAILURE", "VALIDATOR_DRIFT_FAILURE",
    }
    assert blocker["type"] in valid_types, f"Invalid root blocker type: {blocker['type']}"
    assert blocker["stage"] in ("A", "B", "C", "D", "E", "F")
    assert isinstance(blocker["evidence"], dict)


def test_full_audit_report_schema_secondary_finding_item():
    """Verify secondary finding items match required schema from PRD Section 7."""
    runner = CBETLAuditRunner("2025-01-01", "2025-01-31")

    spt = _make_pass_supportability()
    spt["missing_underlying_row_count"] = 3
    spt["missing_underlying_unique_bond_count"] = 2

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": spt,
        "premium_join_summary": _make_pass_premium(),
        "is_st_join_summary": _make_pass_is_st(),
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": _make_pass_validator(),
    }

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    assert len(report["secondary_findings"]) > 0
    finding = report["secondary_findings"][0]

    # required_secondary_finding_item_schema
    required_fields = {"type", "stage", "trigger", "evidence"}
    assert required_fields.issubset(set(finding.keys())), \
        f"Secondary finding item missing fields: {required_fields - set(finding.keys())}"

    valid_types = {
        "MISSING_UNDERLYING_TICKER_ROWS", "MISSING_PREMIUM_RATE_ROWS",
        "MISSING_IS_ST_ROWS", "MISSING_REDEMPTION_ROWS",
        "EXCLUSION_ONLY_WINDOW", "SEMANTIC_THRESHOLD_BREACH",
    }
    assert finding["type"] in valid_types, f"Invalid secondary finding type: {finding['type']}"
    assert finding["stage"] in ("B", "C", "D", "E", "F")
    assert isinstance(finding["evidence"], dict)


# Regression: full report should be valid JSON in a round-trip test
def test_full_audit_report_is_roundtrip_json():
    """Verify the report can be serialized and deserialized without loss."""
    runner = CBETLAuditRunner("2025-01-06", "2025-01-07")

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": _make_pass_supportability(),
        "premium_join_summary": _make_pass_premium(),
        "is_st_join_summary": _make_pass_is_st(),
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": _make_pass_validator(),
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = os.path.join(tmpdir, "test_report.json")
        with patch.object(runner.pipeline, "run", return_value=stage_results), \
             patch("etl.jqdata_sync_cb.os.makedirs"), \
             patch("etl.jqdata_sync_cb.open", create=True) as mock_open:
            # Write the report to a real temp file for round-trip test
            report = runner.run()
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

        with open(report_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        # All top-level fields must survive the round-trip
        for field in ["execution_mode", "start_date", "end_date", "final_status",
                      "non_promotion_disclaimer", "source_coverage",
                      "supportability_summary", "premium_join_summary",
                      "is_st_join_summary", "redemption_summary",
                      "validator_summary", "root_blockers", "secondary_findings"]:
            assert field in loaded, f"Field '{field}' lost in round-trip"


# ---------------------------------------------------------------------------
# Test 4: Audit isolation integrity
# ---------------------------------------------------------------------------

def test_audit_isolation_integrity():
    """PRD 3.10: Verify audit run does NOT modify canonical data CSV.

    Even a successful audit run must not write to data/cb_history_factors.csv.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a temporary "canonical" data file
        data_path = os.path.join(tmpdir, "cb_history_factors.csv")
        initial_content = "ticker,date,open,high,low,close\n123456,2025-01-06,100,101,99,100.5\n"
        with open(data_path, "w", encoding="utf-8") as f:
            f.write(initial_content)

        initial_mtime = os.path.getmtime(data_path)
        initial_size = os.path.getsize(data_path)

        # Create a runner and mock the pipeline
        runner = CBETLAuditRunner("2025-01-06", "2025-01-07")

        stage_results = {
            "source_coverage": _make_pass_source(),
            "supportability_summary": _make_pass_supportability(),
            "premium_join_summary": _make_pass_premium(),
            "is_st_join_summary": _make_pass_is_st(),
            "redemption_summary": _make_pass_redemption(),
            "validator_summary": _make_pass_validator(),
        }

        with patch.object(runner.pipeline, "run", return_value=stage_results), \
             patch("etl.jqdata_sync_cb.DATA_PATH", data_path), \
             patch("etl.jqdata_sync_cb.os.makedirs"), \
             patch("etl.jqdata_sync_cb.open", create=True):
            report = runner.run()

        # Verify the canonical data file is unmodified
        assert os.path.exists(data_path)
        assert os.path.getmtime(data_path) == initial_mtime, \
            "DATA_PATH was modified by audit run"
        assert os.path.getsize(data_path) == initial_size, \
            "DATA_PATH size changed during audit run"
        with open(data_path, "r", encoding="utf-8") as f:
            assert f.read() == initial_content, \
                "DATA_PATH content was modified by audit run"

        # Verify the report declares non-promotion
        assert "diagnostic only" in report["non_promotion_disclaimer"]
        assert "No canonical dataset promotion" in report["non_promotion_disclaimer"]
        assert report["execution_mode"] == "audit"


def test_audit_isolation_integrity_no_tmp_bak_files():
    """Verify audit run does not create promotion tmp/bak artifacts.

    PRD 3.10.2: audit runner must not create or overwrite:
      - data/cb_history_factors.csv.tmp
      - data/cb_history_factors.csv.bak
      - data/cb_history_factors.metrics.json
      - data/cb_history_factors.metrics.json.tmp
      - data/cb_history_factors.metrics.json.bak
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        data_path = os.path.join(tmpdir, "cb_history_factors.csv")
        metrics_path = os.path.join(tmpdir, "cb_history_factors.metrics.json")

        # Create minimal files (metrics is empty JSON)
        with open(data_path, "w", encoding="utf-8") as f:
            f.write("ticker,date,open\n")
        with open(metrics_path, "w", encoding="utf-8") as f:
            f.write("{}")

        runner = CBETLAuditRunner("2025-01-06", "2025-01-07")

        stage_results = {
            "source_coverage": _make_pass_source(),
            "supportability_summary": _make_pass_supportability(),
            "premium_join_summary": _make_pass_premium(),
            "is_st_join_summary": _make_pass_is_st(),
            "redemption_summary": _make_pass_redemption(),
            "validator_summary": _make_pass_validator(),
        }

        with patch.object(runner.pipeline, "run", return_value=stage_results), \
             patch("etl.jqdata_sync_cb.DATA_PATH", data_path), \
             patch("etl.jqdata_sync_cb.METRICS_PATH", metrics_path), \
             patch("etl.jqdata_sync_cb.os.makedirs"), \
             patch("etl.jqdata_sync_cb.open", create=True):
            runner.run()

        # Verify no promotion tmp/bak artifacts were created
        forbidden_files = [
            data_path + ".tmp",
            data_path + ".bak",
            metrics_path,
            metrics_path + ".tmp",
            metrics_path + ".bak",
        ]
        # metrics_path itself was pre-created; check it wasn't overwritten
        for forbidden in [data_path + ".tmp", data_path + ".bak",
                          metrics_path + ".tmp", metrics_path + ".bak"]:
            assert not os.path.exists(forbidden), \
                f"Forbidden promotion artifact was created: {forbidden}"


# ---------------------------------------------------------------------------
# Additional formula tests: PREMIUM_RATE_MISSING_BROAD_COVERAGE
# ---------------------------------------------------------------------------

def test_formula_premium_rate_missing_broad_coverage():
    """PRD 3.5.5: PREMIUM_RATE_MISSING_BROAD_COVERAGE when ratio >= 0.20
    but PREMIUM_SOURCE_TRUNCATION is NOT triggered."""
    runner = CBETLAuditRunner("2025-01-01", "2025-01-31")

    premium_coverage_low = {
        "status": "FAIL",
        "failure_type": "PREMIUM_RATE_MISSING_BROAD_COVERAGE",
        "premium_joined_row_count": 800,
        "premium_joined_unique_bond_count": 800,
        "missing_premium_row_count": 200,
        "missing_premium_unique_bond_count": 200,
        "missing_premium_ratio": 0.25,
        "message": "Premium rate coverage is low.",
    }

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": _make_pass_supportability(supportable=1000, unique=1000),
        "premium_join_summary": premium_coverage_low,
        "is_st_join_summary": _make_pass_is_st(),
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": _make_pass_validator(),
    }

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    root_blocker_types = [b["type"] for b in report["root_blockers"]]
    assert "PREMIUM_RATE_MISSING_BROAD_COVERAGE" in root_blocker_types
    assert "PREMIUM_SOURCE_TRUNCATION" not in root_blocker_types


# ---------------------------------------------------------------------------
# Additional formula tests: REDEMPTION_SOURCE_GAP
# ---------------------------------------------------------------------------

def test_formula_redemption_source_gap():
    """PRD 3.5.7: REDEMPTION_SOURCE_GAP when missing_redemption_ratio >= 0.20."""
    runner = CBETLAuditRunner("2025-01-01", "2025-01-31")

    redemption_gapped = {
        "status": "FAIL",
        "failure_type": "REDEMPTION_SOURCE_GAP",
        "redemption_joined_row_count": 700,
        "redemption_joined_unique_bond_count": 700,
        "missing_redemption_row_count": 300,
        "missing_redemption_unique_bond_count": 300,
        "missing_redemption_ratio": 0.30,
        "message": "Redemption/delist coverage is low.",
    }

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": _make_pass_supportability(supportable=1000, unique=1000),
        "premium_join_summary": _make_pass_premium(),
        "is_st_join_summary": _make_pass_is_st(),
        "redemption_summary": redemption_gapped,
        "validator_summary": _make_pass_validator(),
    }

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    root_blocker_types = [b["type"] for b in report["root_blockers"]]
    assert "REDEMPTION_SOURCE_GAP" in root_blocker_types
    assert report["final_status"] == "FAIL_ROOT_BLOCKER"


# ---------------------------------------------------------------------------
# Additional: Validator failure formulas
# ---------------------------------------------------------------------------

def test_formula_validator_schema_failure():
    """PRD 3.5.8: VALIDATOR_SCHEMA_FAILURE root blocker."""
    runner = CBETLAuditRunner("2025-01-01", "2025-01-31")

    validator_bad = {
        "status": "FAIL",
        "failure_type": "VALIDATOR_SCHEMA_FAILURE",
        "schema_validator_status": "FAIL",
        "semantic_validator_status": "PASS",
        "drift_validator_status": "PASS",
        "schema_validator_message": "Column type mismatch",
        "semantic_validator_message": "",
        "drift_validator_message": "",
        "message": "Column type mismatch",
    }

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": _make_pass_supportability(),
        "premium_join_summary": _make_pass_premium(),
        "is_st_join_summary": _make_pass_is_st(),
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": validator_bad,
    }

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    root_blocker_types = [b["type"] for b in report["root_blockers"]]
    assert "VALIDATOR_SCHEMA_FAILURE" in root_blocker_types


# ---------------------------------------------------------------------------
# Additional: final_status rules
# ---------------------------------------------------------------------------

def test_final_status_fail_secondary_only():
    """PRD 3.8: When secondary findings exist but no root blockers,
    final_status must be FAIL_SECONDARY_ONLY."""
    runner = CBETLAuditRunner("2025-01-01", "2025-01-31")

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": _make_pass_supportability(),  # no regression
        "premium_join_summary": _make_pass_premium(),
        "is_st_join_summary": _make_pass_is_st(),
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": _make_pass_validator(),
    }

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    # With everything passing, no root blockers, no secondary findings → PASS
    assert report["final_status"] == "PASS"
    assert len(report["root_blockers"]) == 0
    assert len(report["secondary_findings"]) == 0


def test_final_status_fail_secondary_only_with_findings():
    """When only secondary findings exist, final_status = FAIL_SECONDARY_ONLY."""
    runner = CBETLAuditRunner("2025-01-01", "2025-01-31")

    spt = _make_pass_supportability()
    spt["missing_underlying_row_count"] = 5

    pre = _make_pass_premium()
    pre["missing_premium_row_count"] = 3

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": spt,
        "premium_join_summary": pre,
        "is_st_join_summary": _make_pass_is_st(),
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": _make_pass_validator(),
    }

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    assert len(report["root_blockers"]) == 0
    assert len(report["secondary_findings"]) > 0
    assert report["final_status"] == "FAIL_SECONDARY_ONLY"


# ---------------------------------------------------------------------------
# Exclusion-only window tests
# ---------------------------------------------------------------------------

def test_exclusion_only_window_secondary_finding():
    """PRD 3.6.5: EXCLUSION_ONLY_WINDOW is a secondary finding when
    supportable_row_count == 0 and Stage B passes."""
    runner = CBETLAuditRunner("2025-01-01", "2025-01-31")

    spt = _make_pass_supportability(supportable=0, unique=0)

    stage_results = {
        "source_coverage": _make_pass_source(),
        "supportability_summary": spt,
        "premium_join_summary": _make_pass_premium(),
        "is_st_join_summary": _make_pass_is_st(),
        "redemption_summary": _make_pass_redemption(),
        "validator_summary": _make_pass_validator(),
    }

    with patch.object(runner.pipeline, "run", return_value=stage_results), \
         patch("etl.jqdata_sync_cb.os.makedirs"), \
         patch("etl.jqdata_sync_cb.open", create=True):
        report = runner.run()

    # C-E stages should be NOT_RUN (skipped because no supportable bonds)
    for key in ["premium_join_summary", "is_st_join_summary", "redemption_summary"]:
        assert report[key]["status"] == "NOT_RUN", \
            f"{key} should be NOT_RUN in exclusion-only window"

    assert any(
        f["type"] == "EXCLUSION_ONLY_WINDOW" for f in report["secondary_findings"]
    ), "EXCLUSION_ONLY_WINDOW must be in secondary_findings"
