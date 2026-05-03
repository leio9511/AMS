import json
import os
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
import datetime

from etl.cb_etl_pipeline import (
    CBETLPipeline,
    STAGE_STATUS_PASS,
    STAGE_STATUS_FAIL,
    STAGE_STATUS_NOT_RUN,
)

@pytest.fixture
def mock_jqdata():
    mock_jq = MagicMock()
    mock_jq.auth.return_value = None
    mock_jq.bond.run_query.return_value = pd.DataFrame(columns=["code", "company_code", "delist_Date"])
    mock_jq.get_all_securities.return_value = pd.DataFrame(columns=["code"])
    mock_jq.get_price.return_value = pd.DataFrame()
    mock_jq.get_extras.return_value = pd.DataFrame()
    
    # Mock query filters
    mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    return mock_jq

def test_stage_c_deterministic_batching_by_month_and_code(mock_jqdata):
    # Setup pipeline with 2-month window and 150 codes (should trigger multiple batches)
    start_date = "2025-01-01"
    end_date = "2025-02-28"
    pipeline = CBETLPipeline(start_date, end_date, jqdata_provider=mock_jqdata)
    
    # Mock Stage A/B success
    pipeline.results["source_coverage"]["status"] = STAGE_STATUS_PASS
    pipeline.df = pd.DataFrame({
        "date": [pd.Timestamp("2025-01-01")] * 150,
        "ticker": [f"{i}.XSHG" for i in range(150)],
        "bond_code_raw": [f"{i}" for i in range(150)],
        "bond_exchange_code": ["XSHG"] * 150,
        "supportability_bucket": ["supportable"] * 150
    })
    pipeline.bond_to_stock = {f"{i}": f"STK{i}" for i in range(150)}
    
    # Run Stage C
    pipeline.run_stage_c_premium_join()
    
    # Verify multiple calls to run_query
    # 2 months * 2 code batches (100 + 50) = 4 calls expected
    assert mock_jqdata.bond.run_query.call_count == 4

def test_stage_c_truncation_guard_trigger(mock_jqdata):
    start_date = "2025-01-01"
    end_date = "2025-01-05"
    pipeline = CBETLPipeline(start_date, end_date, jqdata_provider=mock_jqdata)
    
    pipeline.results["source_coverage"]["status"] = STAGE_STATUS_PASS
    pipeline.df = pd.DataFrame({
        "date": [pd.Timestamp("2025-01-01")],
        "ticker": ["110059.XSHG"],
        "bond_code_raw": ["110059"],
        "bond_exchange_code": ["XSHG"],
        "supportability_bucket": ["supportable"]
    })
    
    # Mock run_query to return 5000 rows (simulating truncation in a single batch)
    mock_jqdata.bond.run_query.return_value = pd.DataFrame({"code": ["1"] * 5000})
    
    pipeline.run_stage_c_premium_join()
    
    assert pipeline.results["premium_join_summary"]["status"] == STAGE_STATUS_FAIL
    assert "Premium source query returned the provider single-call cap characteristic" in pipeline.results["premium_join_summary"]["message"]

def test_stage_d_is_st_window_hardening_exception(mock_jqdata):
    start_date = "2025-01-01"
    end_date = "2025-01-05"
    pipeline = CBETLPipeline(start_date, end_date, jqdata_provider=mock_jqdata)
    
    pipeline.results["source_coverage"]["status"] = STAGE_STATUS_PASS
    pipeline.df = pd.DataFrame({
        "date": [pd.Timestamp("2025-01-01")],
        "ticker": ["110059.XSHG"],
        "bond_code_raw": ["110059"],
        "bond_exchange_code": ["XSHG"],
        "underlying_ticker": ["600001.XSHG"],
        "supportability_bucket": ["supportable"]
    })
    
    # Mock get_extras to raise window error
    mock_jqdata.get_extras.side_effect = Exception("JQData window restriction: support only from 2025-01-20")
    
    pipeline.run_stage_d_is_st_join()
    
    assert pipeline.results["is_st_join_summary"]["status"] == STAGE_STATUS_FAIL
    assert "is_st source query exceeded the provider-supported date window" in pipeline.results["is_st_join_summary"]["message"]

def test_stage_d_is_st_full_gap_message(mock_jqdata):
    start_date = "2025-01-01"
    end_date = "2025-01-05"
    pipeline = CBETLPipeline(start_date, end_date, jqdata_provider=mock_jqdata)
    
    pipeline.results["source_coverage"]["status"] = STAGE_STATUS_PASS
    pipeline.df = pd.DataFrame({
        "date": [pd.Timestamp("2025-01-01")],
        "ticker": ["110059.XSHG"],
        "bond_code_raw": ["110059"],
        "bond_exchange_code": ["XSHG"],
        "underlying_ticker": ["600001.XSHG"],
        "supportability_bucket": ["supportable"]
    })
    
    # Mock empty return (100% gap)
    mock_jqdata.get_extras.return_value = pd.DataFrame()
    
    pipeline.run_stage_d_is_st_join()
    
    assert pipeline.results["is_st_join_summary"]["status"] == STAGE_STATUS_FAIL
    assert "is_st source query exceeded the provider-supported date window" in pipeline.results["is_st_join_summary"]["message"]


def test_stage_c_premium_join_succeeds_for_live_shape_without_exchange_code(mock_jqdata):
    start_date = "2025-01-01"
    end_date = "2025-01-01"
    pipeline = CBETLPipeline(start_date, end_date, jqdata_provider=mock_jqdata)

    pipeline.results["source_coverage"]["status"] = STAGE_STATUS_PASS
    pipeline.results["supportability_summary"]["supportable_row_count"] = 2
    pipeline.df = pd.DataFrame(
        {
            "date": [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-01")],
            "ticker": ["110059.XSHG", "123001.XSHE"],
            "bond_code_raw": ["110059", "123001"],
            "bond_exchange_code": ["XSHG", "XSHE"],
            "underlying_ticker": ["600001.XSHG", "000001.XSHE"],
            "supportability_bucket": ["supportable", "supportable"],
            "close": [100.0, 200.0],
        }
    )

    mock_jqdata.bond.run_query.return_value = pd.DataFrame(
        {
            "code": ["110059", "123001"],
            "date": ["2025-01-01", "2025-01-01"],
            "convert_price": [10.0, 20.0],
            "convert_premium_rate": [15.0, 25.0],
        }
    )

    pipeline.run_stage_c_premium_join()

    summary = pipeline.results["premium_join_summary"]
    assert summary["premium_joined_row_count"] > 0
    assert summary["premium_missing_ratio_against_active_universe"] < 1.0
    assert pipeline.df["premium_rate"].notna().sum() == 2
    assert pipeline.df["bond_code_raw"].tolist() == ["110059", "123001"]
    assert pipeline.df["bond_exchange_code"].tolist() == ["XSHG", "XSHE"]
