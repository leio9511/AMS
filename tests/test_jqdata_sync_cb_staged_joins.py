"""Tests for PR-002: Join Stages C D E and NOT_RUN Propagation.

Covers:
- Premium join coverage metrics (Stage C)
- is_st join missing data handling (Stage D)
- NOT_RUN propagation when Stage A fails
- Stage B regression does not stop Stage C-E in audit mode (PRD 3.4.2)
"""

import pytest
from unittest.mock import MagicMock, patch
import pandas as pd

from etl.jqdata_sync_cb import (
    PremiumJoinStage,
    STJoinStage,
    RedemptionStage,
    StagedPipeline,
    SourceAcquisitionStage,
    SupportabilityStage,
    ValidatorStage,
    CBETLAuditRunner,
)


def _fix_mock_comparisons(mock_jq):
    """Fix MagicMock >= / <= operators so query building works.

    PremiumJoinStage constructs filter expressions like::

        CONBOND_DAILY_CONVERT.date >= start_date

    Plain MagicMock.__ge__ returns NotImplemented for string operands,
    causing TypeError.  This helper patches the date attribute so the
    comparison returns a truthy value (another MagicMock).
    """
    date_mock = mock_jq.bond.CONBOND_DAILY_CONVERT.date
    date_mock.__ge__ = MagicMock(return_value=True)
    date_mock.__le__ = MagicMock(return_value=True)


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("JQDATA_USER", "fake_user")
    monkeypatch.setenv("JQDATA_PWD", "fake_pwd")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_price_df(tickers=None, dates=None):
    """Build a minimal price DataFrame in the MultiIndex format that
    jqdatasdk.get_price() returns (index: time, code)."""
    if tickers is None:
        tickers = ["123456.XSHG"]
    if dates is None:
        dates = ["2025-01-06"]
    rows = []
    idx_tuples = []
    opens, highs, lows, closes, volumes = [], [], [], [], []
    for t in tickers:
        for d in dates:
            idx_tuples.append((pd.to_datetime(d), t))
            opens.append(100.0)
            highs.append(101.0)
            lows.append(99.0)
            closes.append(100.5)
            volumes.append(1000)
    index = pd.MultiIndex.from_tuples(idx_tuples, names=["time", "code"])
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    }, index=index)


def _make_basic_info_df(codes=None, company_codes=None, delist_dates=None):
    """Build a minimal CONBOND_BASIC_INFO DataFrame.

    Note: company_codes should use the full ticker-with-exchange format
    (e.g. "600000.XSHG") to match what get_extras("is_st") returns.
    """
    if codes is None:
        codes = ["123456.XSHG"]
    if company_codes is None:
        company_codes = ["600000.XSHG"]
    if delist_dates is None:
        delist_dates = ["2025-12-31"] * len(codes)
    return pd.DataFrame({
        "code": codes,
        "company_code": company_codes,
        "delist_Date": delist_dates,
    })


def _make_premium_df(date="2025-01-06", code="123456", exchange="XSHG", rate=15.0):
    """Build a minimal CONBOND_DAILY_CONVERT DataFrame."""
    return pd.DataFrame({
        "date": [date],
        "code": [code],
        "exchange_code": [exchange],
        "convert_premium_rate": [rate],
    })


# ---------------------------------------------------------------------------
# Test 1: Premium join coverage metrics
# ---------------------------------------------------------------------------

def test_premium_join_coverage_metrics():
    """Verify missing_premium_ratio is correctly calculated when some bonds
    are missing premium data (PR-002 acceptance criterion 1)."""
    import jqdatasdk

    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock_jq:
        _fix_mock_comparisons(mock_jq)
        # --- Stage A data ---
        mock_jq.auth.return_value = None
        mock_jq.bond.run_query.return_value = _make_basic_info_df(
            codes=["123456.SH", "789012.SH"],
            company_codes=["600000", "000001"],
        )
        mock_jq.get_all_securities.return_value = pd.DataFrame(
            index=["123456.XSHG", "789012.XSHG"]
        )
        mock_jq.get_price.return_value = _make_price_df(
            tickers=["123456.XSHG", "789012.XSHG"]
        )

        pipeline = StagedPipeline([
            SourceAcquisitionStage("2025-01-06", "2025-01-07"),
            SupportabilityStage("2025-01-06"),
            PremiumJoinStage("2025-01-06", "2025-01-07"),
        ])
        results = pipeline.run(stop_on_failure=False)

        premium = results["premium_join_summary"]
        # Without a proper premium mock, premium join will fail (exception)
        # → premium_rate = NaN for all rows → missing_premium_ratio = 1.0
        assert premium["missing_premium_ratio"] == 1.0
        assert premium["missing_premium_row_count"] == 2
        assert premium["premium_joined_row_count"] == 0


def test_premium_join_with_partial_coverage():
    """Verify missing_premium_ratio < 1.0 when only some bonds lack premium data."""
    import jqdatasdk

    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock_jq:
        _fix_mock_comparisons(mock_jq)
        mock_jq.auth.return_value = None
        mock_jq.bond.run_query.side_effect = [
            _make_basic_info_df(
                codes=["123456.XSHG", "789012.XSHG"],
                company_codes=["600000.XSHG", "000001.XSHG"],
            ),
            _make_premium_df(date="2025-01-06", code="123456", exchange="XSHG", rate=15.0),
        ]
        mock_jq.get_all_securities.return_value = pd.DataFrame(
            index=["123456.XSHG", "789012.XSHG"]
        )
        mock_jq.get_price.return_value = _make_price_df(
            tickers=["123456.XSHG", "789012.XSHG"]
        )

        pipeline = StagedPipeline([
            SourceAcquisitionStage("2025-01-06", "2025-01-07"),
            SupportabilityStage("2025-01-06"),
            PremiumJoinStage("2025-01-06", "2025-01-07"),
        ])
        results = pipeline.run(stop_on_failure=False)

        premium = results["premium_join_summary"]
        # One bond (123456) has premium, the other (789012) doesn't
        assert premium["premium_joined_row_count"] == 1
        assert premium["missing_premium_row_count"] == 1
        assert premium["missing_premium_ratio"] == 0.5


# ---------------------------------------------------------------------------
# Test 2: is_st join missing data handling
# ---------------------------------------------------------------------------

def test_st_join_missing_data():
    """Verify Stage D handles missing is_st data correctly.

    When get_extras("is_st") raises or returns empty, the stage should
    fall back to pd.NA for is_st and report the gap (PR-002 criterion 2).
    """
    import jqdatasdk

    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock_jq:
        _fix_mock_comparisons(mock_jq)
        mock_jq.auth.return_value = None
        mock_jq.bond.run_query.side_effect = [
            _make_basic_info_df(),
            _make_premium_df(),
        ]
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=["123456.XSHG"])
        mock_jq.get_price.return_value = _make_price_df()

        # Simulate get_extras failing
        mock_jq.get_extras.side_effect = Exception("is_st source unavailable")

        pipeline = StagedPipeline([
            SourceAcquisitionStage("2025-01-06", "2025-01-07"),
            SupportabilityStage("2025-01-06"),
            PremiumJoinStage("2025-01-06", "2025-01-07"),
            STJoinStage("2025-01-06", "2025-01-07"),
        ])
        results = pipeline.run(stop_on_failure=False)

        is_st = results["is_st_join_summary"]
        # is_st should be NA → all rows missing
        assert is_st["missing_is_st_row_count"] == 1
        assert is_st["missing_is_st_ratio"] == 1.0
        assert is_st["is_st_joined_row_count"] == 0


def test_st_join_with_valid_data():
    """Verify Stage D successfully joins is_st data when available."""
    import jqdatasdk

    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock_jq:
        _fix_mock_comparisons(mock_jq)
        mock_jq.auth.return_value = None
        mock_jq.bond.run_query.side_effect = [
            _make_basic_info_df(),
            _make_premium_df(),
        ]
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=["123456.XSHG"])
        mock_jq.get_price.return_value = _make_price_df()

        # Provide valid is_st data (matching company_code with exchange suffix)
        mock_jq.get_extras.return_value = pd.DataFrame(
            {"600000.XSHG": [False]},
            index=pd.to_datetime(["2025-01-06"]),
        )

        pipeline = StagedPipeline([
            SourceAcquisitionStage("2025-01-06", "2025-01-07"),
            SupportabilityStage("2025-01-06"),
            PremiumJoinStage("2025-01-06", "2025-01-07"),
            STJoinStage("2025-01-06", "2025-01-07"),
        ])
        results = pipeline.run(stop_on_failure=False)

        is_st = results["is_st_join_summary"]
        assert is_st["is_st_joined_row_count"] == 1
        assert is_st["missing_is_st_row_count"] == 0
        assert is_st["missing_is_st_ratio"] == 0.0


# ---------------------------------------------------------------------------
# Test 3: NOT_RUN propagation when Stage A fails
# ---------------------------------------------------------------------------

def test_propagation_stage_a_fail():
    """Assert Stages C, D, and E are NOT_RUN when Stage A fails.

    Per PRD 3.4.1: If Stage A status == FAIL, Stages B-F must all be
    marked NOT_RUN with message "Skipped because Stage A failed."
    (PR-002 acceptance criterion 3)
    """
    import jqdatasdk

    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock_jq:
        # Stage A auth failure
        mock_jq.auth.side_effect = Exception("Auth failed")

        pipeline = StagedPipeline([
            SourceAcquisitionStage("2025-01-06", "2025-01-07"),
            SupportabilityStage("2025-01-06"),
            PremiumJoinStage("2025-01-06", "2025-01-07"),
            STJoinStage("2025-01-06", "2025-01-07"),
            RedemptionStage(),
        ])
        results = pipeline.run(stop_on_failure=False)

        # Stage A must be FAIL
        assert results["source_coverage"]["status"] == "FAIL"
        assert results["source_coverage"]["failure_type"] == "SOURCE_AUTH_FAILURE"

        # Stages B through E must all be NOT_RUN with the canonical message
        for stage_name in ["supportability_summary", "premium_join_summary",
                           "is_st_join_summary", "redemption_summary"]:
            assert results[stage_name]["status"] == "NOT_RUN", \
                f"Expected {stage_name} NOT_RUN, got {results[stage_name]['status']}"
            assert results[stage_name]["message"] == "Skipped because Stage A failed.", \
                f"Wrong NOT_RUN message in {stage_name}: {results[stage_name].get('message')}"
            assert results[stage_name]["failure_type"] == "NONE", \
                f"Expected failure_type NONE in {stage_name}"


def test_propagation_stage_a_fail_audit_report():
    """End-to-end audit report test: Stage A failure → all downstream NOT_RUN."""
    import jqdatasdk

    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock_jq:
        mock_jq.auth.side_effect = Exception("Auth failed")

        with patch("etl.jqdata_sync_cb.os.makedirs"), \
             patch("etl.jqdata_sync_cb.open", create=True):
            runner = CBETLAuditRunner("2025-01-06", "2025-01-07")
            report = runner.run()

        assert report["source_coverage"]["status"] == "FAIL"
        for key in ["supportability_summary", "premium_join_summary",
                    "is_st_join_summary", "redemption_summary", "validator_summary"]:
            assert report[key]["status"] == "NOT_RUN", \
                f"{key} should be NOT_RUN"
            assert report[key]["message"] == "Skipped because Stage A failed."

        # Root blocker must be SOURCE_AUTH_FAILURE
        assert any(b["type"] == "SOURCE_AUTH_FAILURE" for b in report["root_blockers"])
        assert report["final_status"] == "FAIL_ROOT_BLOCKER"


# ---------------------------------------------------------------------------
# Test 4: Stage B regression continues audit (C-E still run)
# ---------------------------------------------------------------------------

def test_propagation_stage_b_regression_continues_audit():
    """Verify Stage C still runs in audit mode even if Stage B has a regression.

    Per PRD 3.4.2: SUPPORTABILITY_REGRESSION must NOT stop Stage C-E in
    audit mode; root_blockers must include SUPPORTABILITY_REGRESSION.
    (PR-002 acceptance criterion 4)
    """
    import jqdatasdk

    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock_jq:
        _fix_mock_comparisons(mock_jq)
        mock_jq.auth.return_value = None
        # Basic info with NO company_code → regression
        mock_jq.bond.run_query.side_effect = [
            _make_basic_info_df(company_codes=[None]),
        ]
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=["123456.XSHG"])
        mock_jq.get_price.return_value = _make_price_df()

        with patch("etl.jqdata_sync_cb.os.makedirs"), \
             patch("etl.jqdata_sync_cb.open", create=True):
            runner = CBETLAuditRunner("2025-01-06", "2025-01-07")
            report = runner.run()

        # Stage B must have regression
        assert report["supportability_summary"]["status"] == "FAIL"
        assert report["supportability_summary"]["failure_type"] == "SUPPORTABILITY_REGRESSION"

        # Stage C must NOT be NOT_RUN (it should have run)
        assert report["premium_join_summary"]["status"] != "NOT_RUN", \
            "Stage C should run despite Stage B regression"

        # Stage D must NOT be NOT_RUN
        assert report["is_st_join_summary"]["status"] != "NOT_RUN", \
            "Stage D should run despite Stage B regression"

        # Stage E must NOT be NOT_RUN
        assert report["redemption_summary"]["status"] != "NOT_RUN", \
            "Stage E should run despite Stage B regression"

        # Root blockers must include SUPPORTABILITY_REGRESSION
        assert any(b["type"] == "SUPPORTABILITY_REGRESSION" for b in report["root_blockers"]), \
            "SUPPORTABILITY_REGRESSION must be in root_blockers"


def test_propagation_stage_b_regression_does_not_set_downstream_not_run():
    """When Stage B has SUPPORTABILITY_REGRESSION, downstream stages must
    NOT show the 'Skipped because Stage A' or any skip message."""
    import jqdatasdk

    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock_jq:
        _fix_mock_comparisons(mock_jq)
        mock_jq.auth.return_value = None
        mock_jq.bond.run_query.side_effect = [
            _make_basic_info_df(company_codes=[None]),
        ]
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=["123456.XSHG"])
        mock_jq.get_price.return_value = _make_price_df()

        with patch("etl.jqdata_sync_cb.os.makedirs"), \
             patch("etl.jqdata_sync_cb.open", create=True):
            runner = CBETLAuditRunner("2025-01-06", "2025-01-07")
            report = runner.run()

        # No stage after B should have a skip message
        for key in ["premium_join_summary", "is_st_join_summary",
                    "redemption_summary", "validator_summary"]:
            msg = report[key].get("message", "")
            assert "Skipped because" not in msg, \
                f"{key} should not be skipped: message='{msg}'"
