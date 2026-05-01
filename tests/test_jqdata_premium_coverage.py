import pandas as pd
from unittest.mock import MagicMock
from etl.jqdata_provider import JQDataProvider
from etl.cb_etl_pipeline import CBETLPipeline, SUPPORTABILITY_BUCKET_SUPPORTABLE, SUPPORTABILITY_BUCKET_OUTSIDE_BASIC_INFO

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
        "supportable_row_count": 2
    }
    
    pipeline.df = pd.DataFrame({
        "date": pd.to_datetime(["2023-01-01", "2023-01-01", "2023-01-01"]),
        "bond_code_raw": ["110001", "110002", "110003"],
        "bond_exchange_code": ["XSHG", "XSHG", "XSHG"],
        "supportability_bucket": [SUPPORTABILITY_BUCKET_SUPPORTABLE, SUPPORTABILITY_BUCKET_SUPPORTABLE, SUPPORTABILITY_BUCKET_OUTSIDE_BASIC_INFO],
        "underlying_ticker": ["000001.XSHE", "000002.XSHE", None]
    })
    
    # Provide premium for only one bond
    mock_provider.fetch_cb_price_changes.return_value = pd.DataFrame({
        "date": pd.to_datetime(["2023-01-01"]),
        "code": ["110001.XSHG"],
        "convert_price": [10.0],
        "convert_premium_rate": [15.0]
    })
    
    pipeline.run_stage_c_premium_join()
    
    summary = pipeline.results["premium_join_summary"]
    # We have 2 supportable bonds. Premium joined 1. Missing premium 1.
    # Missing premium ratio should be 1 / 2 = 0.5
    assert summary["missing_premium_ratio"] == 0.5
    assert summary["missing_premium_row_count"] == 1
    assert summary["premium_joined_row_count"] == 1
