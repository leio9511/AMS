import pytest
import pandas as pd
from etl.cb_etl_pipeline import CBETLPipeline
from ams.validators.cb_data_validator import CBDataValidator

class MockProvider:
    def fetch_cb_basic(self):
        return pd.DataFrame({
            "code": ["110001.XSHG", "110002.XSHG"],
            "company_code": ["600001", "600002"],
            "delist_Date": [None, None]
        })
    def fetch_all_securities(self, types):
        return pd.DataFrame(index=["110001.XSHG", "110002.XSHG"])
    def fetch_cb_daily(self, tickers, start_date, end_date):
        # Create a dataframe with some all-null OHLCV rows, partially null rows, and valid rows
        return pd.DataFrame({
            "time": ["2023-01-01", "2023-01-02", "2023-01-01", "2023-01-03"],
            "code": ["110001.XSHG", "110001.XSHG", "110002.XSHG", "110002.XSHG"],
            "open": [100.0, None, 105.0, None],
            "high": [101.0, None, 106.0, 106.0],
            "low": [99.0, None, 104.0, 104.0],
            "close": [100.5, None, 105.5, 105.5],
            "volume": [1000, None, 2000, 2000]
        })

def test_jqdata_ohlcv_filter_removes_all_null_rows():
    pipeline = CBETLPipeline("2023-01-01", "2023-01-02", provider=MockProvider())
    pipeline.run_stage_a_source_acquisition()
    
    # 2023-01-02 row for 110001.XSHG should be removed because OHLCV are all null
    # 2023-01-03 row for 110002.XSHG should be removed because open is null (partially null)
    df = pipeline.df
    assert len(df) == 2
    assert df["open"].isnull().sum() == 0

def test_core_validator_passes_on_active_universe():
    # Setup dataframe with required core fields
    df = pd.DataFrame({
        "ticker": ["110001.XSHG"],
        "date": ["2023-01-01"],
        "close": [100.5],
        "is_st": [False],
        "is_redeemed": [False]
    })
    
    validator = CBDataValidator()
    # It should pass without throwing an exception or returning False
    assert validator.validate_dataframe(df) is True

def test_active_universe_summary_metrics():
    pipeline = CBETLPipeline("2023-01-01", "2023-01-02", provider=MockProvider())
    pipeline.run_stage_a_source_acquisition()
    pipeline.run_stage_b_supportability_classification()
    
    report = pipeline.get_final_report()
    aus = report["active_universe_summary"]
    
    assert aus["core_price_row_count_before_filter"] == 4
    assert aus["core_price_row_count_after_filter"] == 2
    assert aus["all_null_ohlcv_row_count_filtered"] == 1
    assert aus["core_universe_row_count"] == 2
    assert aus["core_universe_unique_bond_count"] == 2
    assert aus["active_bond_universe_count"] == 2
    assert aus["enrichment_target_row_count"] == 2
    assert aus["enrichment_target_unique_bond_count"] == 2
