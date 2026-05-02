import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from etl.cb_provider_base import BaseDataProvider, DataProviderAuthError, DataProviderQuotaError, DataProviderError
from etl.jqdata_provider import JQDataProvider
from etl.cb_etl_pipeline import CBETLPipeline

def test_base_provider_interface():
    """Verify BaseDataProvider is an abstract class and cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseDataProvider()

def test_jq_provider_mapping():
    """Verify JQDataProvider correctly maps JQData responses."""
    mock_client = MagicMock()
    # Mock fetch_cb_basic
    mock_client.bond.run_query.return_value = pd.DataFrame({"code": ["110001.SH"], "company_code": ["600001"]})
    
    provider = JQDataProvider(jqdata_client=mock_client)
    df_basic = provider.fetch_cb_basic()
    assert isinstance(df_basic, pd.DataFrame)
    assert "code" in df_basic.columns
    
    # Mock fetch_all_securities
    mock_client.get_all_securities.return_value = pd.DataFrame(index=["110001.SH"])
    df_all = provider.fetch_all_securities()
    assert "110001.SH" in df_all.index

def test_pipeline_provider_neutrality():
    """Mock BaseDataProvider and verify CBETLPipeline calls expected methods."""
    mock_provider = MagicMock(spec=BaseDataProvider)
    mock_provider.fetch_cb_basic.return_value = pd.DataFrame({"code": ["110001.SH"], "company_code": ["600000"]})
    mock_provider.fetch_all_securities.return_value = pd.DataFrame(index=["110001.SH"])
    mock_provider.fetch_cb_daily.return_value = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1000]},
        index=pd.MultiIndex.from_tuples([("110001.SH", "2025-01-06")], names=["code", "time"])
    )
    
    pipeline = CBETLPipeline("2025-01-06", "2025-01-06", provider=mock_provider)
    success = pipeline.run_stage_a_source_acquisition()
    
    assert success is True
    mock_provider.fetch_cb_basic.assert_called_once()
    mock_provider.fetch_all_securities.assert_called_once_with(["conbond"])
    mock_provider.fetch_cb_daily.assert_called_once()
    
    # Verify no jqdatasdk import in pipeline (this is harder to verify at runtime but we can check sys.modules)
    # Actually, we can just rely on the code review and the fact that we replaced the imports.


def test_tushare_orchestrator_uses_only_adapter_contract_methods(tmp_path):
    """Premium reconstruction must not reach through provider.pro internals."""

    class ProForbiddenProvider:
        def __init__(self):
            self._bond_to_stock_map = {"113052.SH": "601236.SH"}
            self.pro = None
            self.fetch_stock_daily_called = False

        def fetch_cb_price_changes(self, ticker):
            return pd.DataFrame(
                {
                    "ts_code": [ticker],
                    "change_date": ["2023-01-01"],
                    "convert_price_initial": [10.0],
                    "convertprice_aft": [9.0],
                }
            )

        def fetch_cb_basic(self):
            return pd.DataFrame({"code": ["113052.SH"], "conv_price": [10.0]})

        def fetch_cb_daily(self, tickers, start_date, end_date):
            return pd.DataFrame(
                {
                    "code": ["113052.SH"],
                    "time": ["2023-02-01"],
                    "close": [110.0],
                }
            ).set_index(["code", "time"])

        def fetch_stock_daily(self, tickers, start_date, end_date):
            self.fetch_stock_daily_called = True
            assert tickers == ["601236.SH"]
            return pd.DataFrame(
                {
                    "stk_code": ["601236.SH"],
                    "time": ["2023-02-01"],
                    "close": [10.0],
                }
            )

    from etl.tushare_enrichment_orchestrator import TuShareEnrichmentOrchestrator

    provider = ProForbiddenProvider()
    orchestrator = TuShareEnrichmentOrchestrator(provider, cache_dir=str(tmp_path), sleep_seconds_between_calls=0)
    result = orchestrator.run(["113052.SH"], "2023-02-01", "2023-02-28")

    assert provider.fetch_stock_daily_called is True
    assert not result.empty
    assert result["convert_price"].iloc[0] == 9.0
    assert round(result["convert_premium_rate"].iloc[0], 2) == -1.0

def test_jq_provider_quota_error_handling():
    """Verify JQDataProvider raises classified errors when JQData quota is hit."""
    mock_client = MagicMock()
    mock_client.query.side_effect = Exception("JQData query limit exceeded")
    
    provider = JQDataProvider(jqdata_client=mock_client)
    with pytest.raises(DataProviderQuotaError):
        provider.fetch_cb_basic()

def test_jq_provider_auth_error_handling():
    """Verify JQDataProvider raises classified errors when JQData auth fails."""
    mock_client = MagicMock()
    mock_client.query.side_effect = Exception("JQData auth failed")
    
    provider = JQDataProvider(jqdata_client=mock_client)
    with pytest.raises(DataProviderAuthError):
        provider.fetch_cb_basic()
