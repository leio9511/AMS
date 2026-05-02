import os
import json
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from etl.tushare_enrichment_orchestrator import TuShareEnrichmentOrchestrator
from etl.cb_etl_pipeline import _normalize_premium_source
from etl.cb_provider_base import DataProviderQuotaError
from etl.cb_field_registry import (
    TUSHARE_CONVERT_PRICE_PROVENANCE_BASIC,
    TUSHARE_CONVERT_PRICE_PROVENANCE_INITIAL,
    TUSHARE_CONVERT_PRICE_PROVENANCE_LATEST,
)

@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider._bond_to_stock_map = {"113052.SH": "601236.SH"}
    
    def mock_fetch_chg(ticker):
        if ticker == "113052.SH":
            return pd.DataFrame({
                "ts_code": ["113052.SH"],
                "change_date": ["2023-01-01"],
                "convert_price_initial": [10.0],
                "convertprice_aft": [9.0]
            })
        return pd.DataFrame()
        
    provider.fetch_cb_price_changes.side_effect = mock_fetch_chg
    
    provider.fetch_cb_basic.return_value = pd.DataFrame({
        "code": ["113052.SH"],
        "conv_price": [10.0]
    })
    
    provider.fetch_cb_daily.return_value = pd.DataFrame({
        "code": ["113052.SH"],
        "time": ["2023-02-01"],
        "close": [110.0]
    }).set_index(["code", "time"])
    
    provider.pro.daily.return_value = pd.DataFrame({
        "ts_code": ["601236.SH"],
        "trade_date": ["20230201"],
        "close": [10.0]
    })
    
    return provider

def test_tushare_orchestrator_concurrent_run_blocked(tmp_path, mock_provider):
    orchestrator = TuShareEnrichmentOrchestrator(mock_provider, cache_dir=str(tmp_path))
    start_date = "2023-02-01"
    end_date = "2023-02-28"
    
    # Create an active lock
    lock_path = orchestrator._get_lock_path(start_date, end_date)
    with open(lock_path, "w") as f:
        json.dump({
            "owner_pid": os.getpid(),  # using current pid ensures it's "alive"
            "created_at": "2099-01-01T00:00:00"
        }, f)
        
    with pytest.raises(RuntimeError, match="CONCURRENT_RUN_BLOCKED"):
        orchestrator.run(["113052.SH"], start_date, end_date)

def test_tushare_orchestrator_resume_from_pending(tmp_path, mock_provider):
    orchestrator = TuShareEnrichmentOrchestrator(mock_provider, cache_dir=str(tmp_path))
    start_date = "2023-02-01"
    end_date = "2023-02-28"
    tickers = ["113052.SH", "110088.SH"]
    
    # Mock state
    state = {
        "run_status": "PARTIAL_SUCCESS",
        "provider": "tushare",
        "start_date": start_date,
        "end_date": end_date,
        "sorted_tickers": sorted(tickers),
        "completed_tickers": ["113052.SH"],
        "pending_tickers": ["110088.SH"],
        "failed_tickers": [],
        "last_processed_ticker": "113052.SH"
    }
    orchestrator.save_state(state)
    
    # 110088.SH fails, so we can verify if it only called for pending
    mock_provider.fetch_cb_price_changes.side_effect = lambda t: pd.DataFrame()
    
    orchestrator.run(tickers, start_date, end_date)
    
    # Should only call for 110088.SH
    mock_provider.fetch_cb_price_changes.assert_called_once_with("110088.SH")
    
    final_state = orchestrator.load_state(start_date, end_date, tickers)
    assert "113052.SH" in final_state["completed_tickers"]
    assert "110088.SH" in final_state["completed_tickers"]
    assert final_state["run_status"] == "COMPLETED"

def test_tushare_orchestrator_fallback_logic(tmp_path, mock_provider):
    # Fallback sequence: 1) convertprice_aft, 2) convert_price_initial, 3) cb_basic.conv_price, 4) mark missing
    orchestrator = TuShareEnrichmentOrchestrator(mock_provider, cache_dir=str(tmp_path))
    
    # Setup mock to return only cb_basic fallback
    mock_provider.fetch_cb_price_changes.side_effect = lambda t: pd.DataFrame()
    
    df_result = orchestrator.run(["113052.SH"], "2023-02-01", "2023-02-28")
    
    assert not df_result.empty
    # effective_conv_price should be 10.0 (from cb_basic)
    # stock_close = 10.0
    # bond_close = 110.0
    # premium = (110 / ((100/10) * 10)) - 1 = (110 / 100) - 1 = 10%
    assert round(df_result["convert_premium_rate"].iloc[0], 2) == 10.0
    assert df_result["convert_price"].iloc[0] == 10.0
    assert df_result["convert_price_provenance"].iloc[0] == TUSHARE_CONVERT_PRICE_PROVENANCE_BASIC

def test_tushare_orchestrator_rate_limit_degradation(tmp_path, mock_provider):
    orchestrator = TuShareEnrichmentOrchestrator(mock_provider, cache_dir=str(tmp_path))
    
    mock_provider.fetch_cb_price_changes.side_effect = DataProviderQuotaError("RATE_LIMITED")
    
    with pytest.raises(DataProviderQuotaError, match="RATE_LIMITED"):
        orchestrator.run(["113052.SH"], "2023-02-01", "2023-02-28")
        
    final_state = orchestrator.load_state("2023-02-01", "2023-02-28", ["113052.SH"])
    assert final_state["run_status"] == "RATE_LIMITED"


def test_tushare_governed_payload_provenance_survives_normalization_without_jqdata_rewrite(tmp_path, mock_provider):
    orchestrator = TuShareEnrichmentOrchestrator(mock_provider, cache_dir=str(tmp_path))

    df_result = orchestrator.run(["113052.SH"], "2023-02-01", "2023-02-28")

    assert not df_result.empty
    assert df_result["convert_price"].iloc[0] == 9.0
    assert df_result["convert_price_provenance"].iloc[0] == TUSHARE_CONVERT_PRICE_PROVENANCE_LATEST

    normalized = _normalize_premium_source(df_result)

    assert normalized.loc[0, "convert_price_provenance"] == TUSHARE_CONVERT_PRICE_PROVENANCE_LATEST


def test_tushare_latest_non_null_convertprice_aft_wins_when_latest_change_row_is_null(tmp_path, mock_provider):
    orchestrator = TuShareEnrichmentOrchestrator(mock_provider, cache_dir=str(tmp_path))

    mock_provider.fetch_cb_price_changes.side_effect = lambda t: pd.DataFrame(
        {
            "ts_code": ["113052.SH", "113052.SH"],
            "change_date": ["2023-01-01", "2023-01-20"],
            "convert_price_initial": [10.0, 8.0],
            "convertprice_aft": [9.0, None],
        }
    )

    df_result = orchestrator.run(["113052.SH"], "2023-02-01", "2023-02-28")

    assert not df_result.empty
    assert df_result["convert_price"].iloc[0] == 9.0
    assert df_result["convert_price_provenance"].iloc[0] == TUSHARE_CONVERT_PRICE_PROVENANCE_LATEST


def test_tushare_fallback_uses_initial_when_convertprice_aft_column_missing(tmp_path, mock_provider):
    orchestrator = TuShareEnrichmentOrchestrator(mock_provider, cache_dir=str(tmp_path))

    mock_provider.fetch_cb_price_changes.side_effect = lambda t: pd.DataFrame(
        {
            "ts_code": ["113052.SH"],
            "change_date": ["2023-01-01"],
            "convert_price_initial": [11.0],
        }
    )

    df_result = orchestrator.run(["113052.SH"], "2023-02-01", "2023-02-28")

    assert not df_result.empty
    assert df_result["convert_price"].iloc[0] == 11.0
    assert df_result["convert_price_provenance"].iloc[0] == TUSHARE_CONVERT_PRICE_PROVENANCE_INITIAL
    assert round(df_result["convert_premium_rate"].iloc[0], 6) == round((110.0 / ((100 / 11.0) * 10.0) - 1) * 100, 6)


def test_tushare_fallback_uses_cb_basic_when_change_price_columns_missing(tmp_path, mock_provider):
    orchestrator = TuShareEnrichmentOrchestrator(mock_provider, cache_dir=str(tmp_path))

    mock_provider.fetch_cb_price_changes.side_effect = lambda t: pd.DataFrame(
        {
            "ts_code": ["113052.SH"],
            "change_date": ["2023-01-01"],
        }
    )

    df_result = orchestrator.run(["113052.SH"], "2023-02-01", "2023-02-28")

    assert not df_result.empty
    assert df_result["convert_price"].iloc[0] == 10.0
    assert df_result["convert_price_provenance"].iloc[0] == TUSHARE_CONVERT_PRICE_PROVENANCE_BASIC
    assert round(df_result["convert_premium_rate"].iloc[0], 2) == 10.0


def test_tushare_fallback_marks_missing_without_synthesizing_default_when_all_conversion_prices_missing(tmp_path, mock_provider):
    orchestrator = TuShareEnrichmentOrchestrator(mock_provider, cache_dir=str(tmp_path))

    mock_provider.fetch_cb_price_changes.side_effect = lambda t: pd.DataFrame(
        {
            "ts_code": ["113052.SH"],
            "change_date": ["2023-01-01"],
        }
    )
    mock_provider.fetch_cb_basic.return_value = pd.DataFrame(
        {
            "code": ["113052.SH"],
            "conv_price": [None],
        }
    )

    df_result = orchestrator.run(["113052.SH"], "2023-02-01", "2023-02-28")

    assert not df_result.empty
    assert pd.isna(df_result["convert_price"].iloc[0])
    assert pd.isna(df_result["convert_price_provenance"].iloc[0])
    assert pd.isna(df_result["convert_premium_rate"].iloc[0])


def test_tushare_latest_non_null_convertprice_aft_takes_precedence_over_initial_and_basic(tmp_path, mock_provider):
    orchestrator = TuShareEnrichmentOrchestrator(mock_provider, cache_dir=str(tmp_path))

    mock_provider.fetch_cb_price_changes.side_effect = lambda t: pd.DataFrame(
        {
            "ts_code": ["113052.SH", "113052.SH"],
            "change_date": ["2023-01-01", "2023-01-20"],
            "convert_price_initial": [10.0, 8.0],
            "convertprice_aft": [9.0, None],
        }
    )
    mock_provider.fetch_cb_basic.return_value = pd.DataFrame(
        {
            "code": ["113052.SH"],
            "conv_price": [7.0],
        }
    )

    df_result = orchestrator.run(["113052.SH"], "2023-02-01", "2023-02-28")

    assert not df_result.empty
    assert df_result["convert_price"].iloc[0] == 9.0
    assert df_result["convert_price_provenance"].iloc[0] == TUSHARE_CONVERT_PRICE_PROVENANCE_LATEST
