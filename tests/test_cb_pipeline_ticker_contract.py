import pytest
import pandas as pd
from unittest.mock import MagicMock
from etl.cb_etl_pipeline import CBETLPipeline, STAGE_STATUS_PASS

def test_pipeline_assembles_full_tickers_for_premium_fetch():
    # 1. Setup Mock Provider
    mock_provider = MagicMock()
    # Mock fetch_cb_basic to return necessary info
    mock_provider.fetch_cb_basic.return_value = pd.DataFrame({
        "code": ["127076.SZ"],
        "company_code": ["002738.SZ"],
        "delist_Date": [None]
    })
    # Mock fetch_all_securities
    mock_provider.fetch_all_securities.return_value = pd.DataFrame(
        index=["127076.SZ"]
    )
    # Mock fetch_cb_daily
    mock_provider.fetch_cb_daily.return_value = pd.DataFrame({
        "code": ["127076.SZ"],
        "time": ["2025-01-20"],
        "open": [100.0],
        "high": [105.0],
        "low": [99.0],
        "close": [102.0],
        "volume": [1000.0]
    }).set_index(["code", "time"])
    
    # Mock fetch_cb_price_changes - this is what we want to check
    mock_provider.fetch_cb_price_changes.return_value = pd.DataFrame({
        "code": ["127076.SZ"],
        "date": ["2025-01-20"],
        "convert_premium_rate": [15.0]
    })

    # 2. Initialize Pipeline
    pipeline = CBETLPipeline(start_date="2025-01-20", end_date="2025-01-20", provider=mock_provider)
    
    # 3. Run Stages
    assert pipeline.run_stage_a_source_acquisition() is True
    assert pipeline.run_stage_b_supportability_classification() is True
    
    # Verify df state before Stage C
    assert "bond_code_raw" in pipeline.df.columns
    assert "bond_exchange_code" in pipeline.df.columns
    assert pipeline.df.iloc[0]["bond_code_raw"] == "127076"
    assert pipeline.df.iloc[0]["bond_exchange_code"] == "SZ"
    
    # 4. Run Stage C
    assert pipeline.run_stage_c_premium_join() is True
    
    # 5. Assertions
    # Ensure fetch_cb_price_changes was called with full tickers
    mock_provider.fetch_cb_price_changes.assert_called_once()
    args, kwargs = mock_provider.fetch_cb_price_changes.call_args
    assert args[0] == ["127076.SZ"]

def test_pipeline_skips_invalid_ticker_assembly():
    # 1. Setup Mock Provider with invalid ticker info (missing exchange)
    mock_provider = MagicMock()
    # Mock fetch_cb_daily with ticker that won't split correctly or missing exchange
    mock_provider.fetch_cb_daily.return_value = pd.DataFrame({
        "code": ["127076"], # No dot, so _split_bond_ticker returns (None, None)
        "time": ["2025-01-20"],
        "open": [100.0],
        "high": [105.0],
        "low": [99.0],
        "close": [102.0],
        "volume": [1000.0]
    }).set_index(["code", "time"])
    
    # Mock other required calls
    mock_provider.fetch_cb_basic.return_value = pd.DataFrame({"code": [], "stk_code": [], "delist_date": []})
    mock_provider.fetch_all_securities.return_value = pd.DataFrame(index=["127076"])
    
    # 2. Initialize Pipeline
    pipeline = CBETLPipeline(start_date="2025-01-20", end_date="2025-01-20", provider=mock_provider)
    
    # 3. Run Stages
    pipeline.run_stage_a_source_acquisition()
    pipeline.run_stage_b_supportability_classification()
    
    # Reset mock to clear Stage A calls
    mock_provider.fetch_cb_price_changes.reset_mock()
    
    # 4. Run Stage C
    pipeline.run_stage_c_premium_join()
    
    # 5. Assertions
    # If bond_exchange_code is None, it should not be in the tickers list passed to fetch_cb_price_changes
    if mock_provider.fetch_cb_price_changes.called:
        args, kwargs = mock_provider.fetch_cb_price_changes.call_args
        assert "127076" not in args[0]
        assert "127076.None" not in args[0]
        assert len(args[0]) == 0
