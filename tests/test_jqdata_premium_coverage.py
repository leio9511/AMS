import pandas as pd
import pytest
from unittest.mock import MagicMock
from etl.jqdata_provider import JQDataProvider
from etl.cb_provider_base import DataProviderError
from etl.cb_audit_contract import JQDATA_CONVERT_PRICE_PROVENANCE
from etl.cb_etl_pipeline import (
    CBETLPipeline,
    SUPPORTABILITY_BUCKET_SUPPORTABLE,
    SUPPORTABILITY_BUCKET_OUTSIDE_BASIC_INFO,
    _normalize_premium_source,
)

def test_jqdata_premium_fetches_direct_rates():
    # Expected: JQData provider correctly queries and maps CONBOND_DAILY_CONVERT fields without recalculating them manually.
    mock_jqdata = MagicMock()
    mock_query = MagicMock()
    mock_jqdata.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdata.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    mock_jqdata.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdata.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    
    mock_df = pd.DataFrame({
        "code": ["110001", "110002"],
        "date": ["2023-01-01", "2023-01-01"],
        "convert_price": [10.0, 20.0],
        "convert_premium_rate": [15.0, 20.0]
    })
    mock_jqdata.bond.run_query.return_value = mock_df
    
    provider = JQDataProvider(jqdata_client=mock_jqdata)
    df_res = provider.fetch_cb_price_changes(["110001", "110002"], "2023-01-01", "2023-01-01")
    
    assert not df_res.empty
    assert "convert_price" in df_res.columns
    assert "convert_price_provenance" in df_res.columns
    assert (df_res["convert_price_provenance"] == JQDATA_CONVERT_PRICE_PROVENANCE).all()
    assert "convert_premium_rate" in df_res.columns
    
    query_call = mock_jqdata.query.call_args[0]
    assert mock_jqdata.bond.CONBOND_DAILY_CONVERT.convert_price in query_call
    assert mock_jqdata.bond.CONBOND_DAILY_CONVERT.convert_premium_rate in query_call

def test_premium_coverage_uses_enrichment_target_universe():
    # Expected: The missing premium ratio is calculated using only supportable, valid-underlying rows as the denominator.
    mock_provider = MagicMock()
    
    # 2 supportable rows, 1 unsupported.
    # We will simulate the dataframe after stage B.
    # enrichment target universe = supportable + underlying_ticker notna
    
    pipeline = CBETLPipeline(start_date="2023-01-01", end_date="2023-01-01", provider=mock_provider)
    pipeline.results["source_coverage"]["status"] = "PASS"
    pipeline.results["source_coverage"]["premium_source_row_count"] = 1
    
    # We mock supportability
    pipeline.results["supportability_summary"] = {
        "status": "PASS",
        "supportable_row_count": 3
    }
    
    pipeline.df = pd.DataFrame({
        "date": pd.to_datetime(["2023-01-01", "2023-01-01", "2023-01-01", "2023-01-01"]),
        "bond_code_raw": ["110001", "110002", "110003", "110004"],
        "bond_exchange_code": ["XSHG", "XSHG", "XSHG", "XSHG"],
        "supportability_bucket": [SUPPORTABILITY_BUCKET_SUPPORTABLE, SUPPORTABILITY_BUCKET_SUPPORTABLE, SUPPORTABILITY_BUCKET_OUTSIDE_BASIC_INFO, SUPPORTABILITY_BUCKET_SUPPORTABLE],
        "underlying_ticker": ["000001.XSHE", "000002.XSHE", None, None]
    })
    
    # Provide premium for only one bond
    mock_provider.fetch_cb_price_changes.return_value = pd.DataFrame({
        "date": pd.to_datetime(["2023-01-01"]),
        "code": ["110001.XSHG"],
        "convert_price": [10.0],
        "convert_price_provenance": [JQDATA_CONVERT_PRICE_PROVENANCE],
        "convert_premium_rate": [15.0]
    })
    
    pipeline.run_stage_c_premium_join()
    
    summary = pipeline.results["premium_join_summary"]
    
    assert summary["premium_missing_ratio_against_active_universe"] == 0.5
    assert summary["missing_premium_row_count"] == 2
    assert summary["premium_joined_row_count"] == 1


def test_normalize_premium_source_does_not_default_missing_provenance_without_explicit_jqdata_source():
    payload = pd.DataFrame(
        {
            "date": ["2023-01-01"],
            "code": ["110001.XSHG"],
            "convert_price": [10.0],
            "convert_premium_rate": [15.0],
        }
    )

    with pytest.raises(ValueError, match="convert_price_provenance is required"):
        _normalize_premium_source(payload)

    normalized_by_source = _normalize_premium_source(payload, source_provider="jqdata")
    assert normalized_by_source.loc[0, "convert_price_provenance"] == JQDATA_CONVERT_PRICE_PROVENANCE

    normalized_by_default = _normalize_premium_source(
        payload,
        convert_price_provenance_default=JQDATA_CONVERT_PRICE_PROVENANCE,
    )
    assert normalized_by_default.loc[0, "convert_price_provenance"] == JQDATA_CONVERT_PRICE_PROVENANCE


def test_jqdata_provider_stamps_convert_price_provenance_before_normalization():
    mock_jqdata = MagicMock()
    mock_query = MagicMock()
    mock_jqdata.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdata.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    mock_jqdata.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdata.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_jqdata.bond.run_query.return_value = pd.DataFrame(
        {
            "code": ["110001"],
            "date": ["2023-01-01"],
            "convert_price": [10.0],
            "convert_premium_rate": [15.0],
        }
    )

    provider = JQDataProvider(jqdata_client=mock_jqdata)
    stamped = provider.fetch_cb_price_changes(["110001.XSHG"], "2023-01-01", "2023-01-01")

    assert stamped.loc[0, "convert_price_provenance"] == JQDATA_CONVERT_PRICE_PROVENANCE
    normalized = _normalize_premium_source(stamped)
    assert normalized.loc[0, "convert_price_provenance"] == JQDATA_CONVERT_PRICE_PROVENANCE


def test_jqdata_provider_restores_exchange_code_from_requested_suffix_for_raw_live_response():
    mock_jqdata = MagicMock()
    mock_query = MagicMock()
    mock_jqdata.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
    mock_jqdata.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
    mock_jqdata.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
    mock_jqdata.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_jqdata.bond.run_query.return_value = pd.DataFrame(
        {
            "code": ["110001", "123456"],
            "date": ["2023-01-01", "2023-01-01"],
            "convert_price": [10.0, 20.0],
            "convert_premium_rate": [15.0, 20.0],
        }
    )

    provider = JQDataProvider(jqdata_client=mock_jqdata)
    restored = provider.fetch_cb_price_changes(["110001.XSHG", "123456.XSHE"], "2023-01-01", "2023-01-01")

    assert restored["exchange_code"].tolist() == ["XSHG", "XSHE"]
    assert (restored["convert_price_provenance"] == JQDATA_CONVERT_PRICE_PROVENANCE).all()
    queried_raw_codes = mock_jqdata.bond.CONBOND_DAILY_CONVERT.code.in_.call_args.args[0]
    assert queried_raw_codes == ["110001", "123456"]


def test_jqdata_provider_rejects_conflicting_suffix_mapping_for_same_raw_code():
    mock_jqdata = MagicMock()
    provider = JQDataProvider(jqdata_client=mock_jqdata)

    with pytest.raises(DataProviderError, match="Conflicting JQData premium exchange suffixes"):
        provider.fetch_cb_price_changes(["110001.XSHG", "110001.XSHE"], "2023-01-01", "2023-01-01")

    mock_jqdata.query.assert_not_called()
