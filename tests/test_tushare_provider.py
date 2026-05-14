import json

import pandas as pd
import pytest
from unittest.mock import MagicMock

from etl.cb_provider_base import DataProviderAuthError, DataProviderError, DataProviderQuotaError
from etl.tushare_provider import CALL_TYPE_REDEEM, IMPORT_COLUMNS, SOURCE_TUSHARE, TuShareProvider


def test_tushare_cb_basic_mapping():
    mock_pro = MagicMock()
    mock_pro.cb_basic.return_value = pd.DataFrame(
        {
            "ts_code": ["110001.SH"],
            "stk_code": ["600001.SH"],
            "delist_date": ["20251231"],
        }
    )

    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_basic()

    assert "code" in df.columns
    assert "company_code" in df.columns
    assert "delist_Date" in df.columns
    assert df.iloc[0]["code"] == "110001.SH"
    assert df.iloc[0]["company_code"] == "600001.SH"
    # delist_Date is converted in pipeline usually, but provider just renames
    assert df.iloc[0]["delist_Date"] == "20251231"


def test_fetch_and_map_redemption_events_filters_strong_redeem_and_maps_import_columns():
    mock_pro = MagicMock()
    mock_pro.cb_call.return_value = pd.DataFrame(
        {
            "ts_code": ["118033.SH", "127001.SZ"],
            "ann_date": ["20260514", "20260515"],
            "call_type": [CALL_TYPE_REDEEM, "到期赎回"],
            "call_date": ["20260601", "20260602"],
        }
    )
    mock_pro.cb_basic.return_value = pd.DataFrame(
        {
            "ts_code": ["118033.SH"],
            "stk_code": ["600001.SH"],
            "delist_date": ["20260615"],
        }
    )

    provider = TuShareProvider(pro=mock_pro)
    result = provider.fetch_and_map_redemption_events("2026-05-01", "2026-05-31")

    mock_pro.cb_call.assert_called_once_with(start_date="20260501", end_date="20260531")
    assert list(result.df.columns) == IMPORT_COLUMNS
    assert len(result.df) == 1
    row = result.df.iloc[0]
    assert row["source_native_event_id"] == "118033SH_20260514"
    assert row["bond_code"] == "118033"
    assert row["announcement_date"] == "2026-05-14"
    assert row["delisting_date"] == "2026-06-15"
    assert row["source"] == SOURCE_TUSHARE
    assert row["updated_at"]
    assert result.filtered_snapshot_ids == ["118033SH_20260514"]
    assert result.rejected_duplicates == []


def test_fetch_and_map_redemption_events_prefers_cb_basic_delist_date_then_falls_back_to_call_date():
    mock_pro = MagicMock()
    mock_pro.cb_call.return_value = pd.DataFrame(
        {
            "ts_code": ["118033.SH", "127001.SZ", "110001.SH"],
            "ann_date": ["20260514", "20260515", "20260516"],
            "call_type": [CALL_TYPE_REDEEM, CALL_TYPE_REDEEM, CALL_TYPE_REDEEM],
            "call_date": ["20260601", "20260602", ""],
        }
    )
    mock_pro.cb_basic.return_value = pd.DataFrame(
        {
            "ts_code": ["118033.SH", "127001.SZ", "110001.SH"],
            "stk_code": ["600001.SH", "000001.SZ", "600002.SH"],
            "delist_date": ["20260615", "", ""],
        }
    )

    provider = TuShareProvider(pro=mock_pro)
    result = provider.fetch_and_map_redemption_events("2026-05-01", "2026-05-31")

    rows = result.df.set_index("source_native_event_id")
    assert rows.loc["118033SH_20260514", "delisting_date"] == "2026-06-15"
    assert rows.loc["127001SZ_20260515", "delisting_date"] == "2026-06-02"
    assert rows.loc["110001SH_20260516", "delisting_date"] == ""


def test_fetch_and_map_redemption_events_records_filtered_snapshot_ids_before_duplicate_rejection():
    mock_pro = MagicMock()
    mock_pro.cb_call.return_value = pd.DataFrame(
        {
            "ts_code": ["118033.SH", "118033.SH", "127001.SZ"],
            "ann_date": ["20260514", "20260514", "20260515"],
            "call_type": [CALL_TYPE_REDEEM, CALL_TYPE_REDEEM, CALL_TYPE_REDEEM],
            "call_date": ["20260601", "20260603", "20260602"],
        }
    )
    mock_pro.cb_basic.return_value = pd.DataFrame(
        {
            "ts_code": ["118033.SH", "127001.SZ"],
            "stk_code": ["600001.SH", "000001.SZ"],
            "delist_date": ["20260615", "20260620"],
        }
    )

    provider = TuShareProvider(pro=mock_pro)
    result = provider.fetch_and_map_redemption_events("2026-05-01", "2026-05-31")

    assert result.filtered_snapshot_ids == [
        "118033SH_20260514",
        "118033SH_20260514",
        "127001SZ_20260515",
    ]
    assert result.df["source_native_event_id"].tolist() == ["127001SZ_20260515"]


def test_fetch_and_map_redemption_events_rejects_all_rows_for_duplicate_source_native_event_ids():
    mock_pro = MagicMock()
    mock_pro.cb_call.return_value = pd.DataFrame(
        {
            "ts_code": ["118033.SH", "118033.SH", "127001.SZ"],
            "ann_date": ["20260514", "20260514", "20260515"],
            "call_type": [CALL_TYPE_REDEEM, CALL_TYPE_REDEEM, CALL_TYPE_REDEEM],
            "call_date": ["20260601", "20260603", "20260602"],
            "some_raw_field": ["alpha", "beta", "gamma"],
        }
    )
    mock_pro.cb_basic.return_value = pd.DataFrame(
        {
            "ts_code": ["118033.SH", "127001.SZ"],
            "stk_code": ["600001.SH", "000001.SZ"],
            "delist_date": ["20260615", "20260620"],
        }
    )

    provider = TuShareProvider(pro=mock_pro)
    result = provider.fetch_and_map_redemption_events("2026-05-01", "2026-05-31")

    assert result.df["source_native_event_id"].tolist() == ["127001SZ_20260515"]
    assert len(result.rejected_duplicates) == 2
    assert {row["some_raw_field"] for row in result.rejected_duplicates} == {"alpha", "beta"}
    assert all("source_native_event_id" not in row for row in result.rejected_duplicates)
    assert all("code" not in row for row in result.rejected_duplicates)
    assert result.rejected_duplicates == [
        {
            "ts_code": "118033.SH",
            "ann_date": "20260514",
            "call_type": CALL_TYPE_REDEEM,
            "call_date": "20260601",
            "some_raw_field": "alpha",
        },
        {
            "ts_code": "118033.SH",
            "ann_date": "20260514",
            "call_type": CALL_TYPE_REDEEM,
            "call_date": "20260603",
            "some_raw_field": "beta",
        },
    ]
    assert json.dumps(result.rejected_duplicates)


def test_fetch_and_map_redemption_events_returns_provider_error_for_non_empty_payload_missing_required_columns():
    provider = TuShareProvider(pro=MagicMock())
    provider.pro.cb_call.return_value = pd.DataFrame(
        {
            "ts_code": ["118033.SH"],
            "ann_date": ["20260514"],
            "call_date": ["20260601"],
        }
    )

    with pytest.raises(DataProviderError, match="TuShare error: cb_call response missing required columns: call_type"):
        provider.fetch_and_map_redemption_events("2026-05-01", "2026-05-31")



def test_fetch_and_map_redemption_events_returns_empty_result_for_empty_or_non_redeem_snapshot():
    provider = TuShareProvider(pro=MagicMock())

    provider.pro.cb_call.return_value = pd.DataFrame()
    empty_result = provider.fetch_and_map_redemption_events("2026-05-01", "2026-05-31")
    assert empty_result.df.empty
    assert list(empty_result.df.columns) == IMPORT_COLUMNS
    assert empty_result.filtered_snapshot_ids == []
    assert empty_result.rejected_duplicates == []

    provider.pro.cb_call.return_value = pd.DataFrame(
        {
            "ts_code": ["127001.SZ"],
            "ann_date": ["20260515"],
            "call_type": ["到期赎回"],
            "call_date": ["20260602"],
        }
    )
    non_redeem_result = provider.fetch_and_map_redemption_events("2026-05-01", "2026-05-31")
    assert non_redeem_result.df.empty
    assert list(non_redeem_result.df.columns) == IMPORT_COLUMNS
    assert non_redeem_result.filtered_snapshot_ids == []
    assert non_redeem_result.rejected_duplicates == []


def test_tushare_is_st_logic():
    mock_pro = MagicMock()
    # Mock trade calendar
    mock_pro.trade_cal.return_value = pd.DataFrame({"cal_date": ["20250101", "20250102"]})

    # Mock stock_st to be called by trade_date
    def mock_stock_st(trade_date=None, ts_code=None, start_date=None, end_date=None):
        if trade_date == "20250102":
            return pd.DataFrame(
                {
                    "ts_code": ["600001.SH"],
                    "trade_date": ["20250102"],
                    "type": ["ST"],
                }
            )
        return pd.DataFrame()

    mock_pro.stock_st.side_effect = mock_stock_st

    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_stock_st_by_date(["600001.SH"], "2025-01-01", "2025-01-02")

    assert df.loc["2025-01-01", "600001.SH"] == False
    assert df.loc["2025-01-02", "600001.SH"] == True
    # Verify it was called with trade_date
    mock_pro.stock_st.assert_any_call(trade_date="20250101")
    mock_pro.stock_st.assert_any_call(trade_date="20250102")


def test_tushare_daily_volume_mapping():
    mock_pro = MagicMock()
    mock_pro.trade_cal.return_value = pd.DataFrame({"cal_date": ["20250120"]})
    mock_pro.cb_daily.return_value = pd.DataFrame(
        {
            "ts_code": ["127076.SZ"],
            "trade_date": ["20250120"],
            "close": [100.0],
            "vol": [5000.0],
        }
    )

    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_daily(["127076.SZ"], "2025-01-20", "2025-01-20")

    assert "volume" in df.columns
    assert df.iloc[0]["volume"] == 5000.0
    assert "vol" not in df.columns


def test_tushare_quota_error():
    mock_pro = MagicMock()
    mock_pro.cb_basic.side_effect = Exception("抱歉，您每分钟最多访问该接口次数限制")

    provider = TuShareProvider(pro=mock_pro)
    with pytest.raises(DataProviderQuotaError):
        provider.fetch_cb_basic()


def test_tushare_auth_error():
    mock_pro = MagicMock()
    mock_pro.cb_basic.side_effect = Exception("抱歉，您输入的TOKEN无效")

    provider = TuShareProvider(pro=mock_pro)
    with pytest.raises(DataProviderAuthError):
        provider.fetch_cb_basic()


def test_tushare_cb_daily_query_strategy():
    mock_pro = MagicMock()
    # Setup: Mock trade_cal to return two trading days
    mock_pro.trade_cal.return_value = pd.DataFrame({"cal_date": ["20250120", "20250121"]})

    # Setup: Mock cb_daily for each day
    def mock_cb_daily(trade_date=None):
        if trade_date == "20250120":
            return pd.DataFrame(
                {
                    "ts_code": ["127076.SZ", "110001.SH"],
                    "trade_date": ["20250120", "20250120"],
                    "close": [100.0, 110.0],
                }
            )
        if trade_date == "20250121":
            return pd.DataFrame(
                {
                    "ts_code": ["127076.SZ", "999999.SH"],
                    "trade_date": ["20250121", "20250121"],
                    "close": [101.0, 120.0],
                }
            )
        return pd.DataFrame()

    mock_pro.cb_daily.side_effect = mock_cb_daily

    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_daily(["127076.SZ"], "2025-01-20", "2025-01-21")

    # Assertions
    assert mock_pro.cb_daily.call_count == 2
    mock_pro.cb_daily.assert_any_call(trade_date="20250120")
    mock_pro.cb_daily.assert_any_call(trade_date="20250121")

    # Verify result contains only for "127076.SZ"
    assert len(df) == 2
    assert all(df.index.get_level_values("code") == "127076.SZ")

    # Verify index and formatting
    assert isinstance(df.index, pd.MultiIndex)
    assert "2025-01-20" in df.index.get_level_values("time")
    assert "2025-01-21" in df.index.get_level_values("time")


def test_tushare_cb_daily_empty_range():
    mock_pro = MagicMock()
    # Mock trade_cal to return empty dataframe with expected columns
    mock_pro.trade_cal.return_value = pd.DataFrame(columns=["cal_date"])

    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_cb_daily(["127076.SZ"], "2025-01-25", "2025-01-26")

    assert df.empty


def test_tushare_full_ticker_contract_compliance():
    """
    Verify that provider methods strictly use the provided tickers
    without attempting to guess suffixes or handle raw codes.
    """
    mock_pro = MagicMock()
    mock_pro.trade_cal.return_value = pd.DataFrame({"cal_date": ["20250120"]})
    # Mock cb_daily returning mixed tickers
    mock_pro.cb_daily.return_value = pd.DataFrame(
        {
            "ts_code": ["127076.SZ", "110001.SH", "123456.SZ"],
            "trade_date": ["20250120", "20250120", "20250120"],
            "close": [100.0, 110.0, 120.0],
            "vol": [1000, 2000, 3000],
        }
    )

    provider = TuShareProvider(pro=mock_pro)
    # If we pass a list of full tickers, it should only return those.
    df = provider.fetch_cb_daily(["127076.SZ", "110001.SH"], "2025-01-20", "2025-01-20")

    assert len(df) == 2
    assert "127076.SZ" in df.index.get_level_values("code")
    assert "110001.SH" in df.index.get_level_values("code")
    assert "123456.SZ" not in df.index.get_level_values("code")

    # Verify that it didn't do any complex parsing, just a straight 'isin' filter
    # which is the current implementation.


def test_tushare_provider_exposes_stock_daily_adapter_method_for_enrichment_reconstruction():
    mock_pro = MagicMock()
    mock_pro.daily.return_value = pd.DataFrame(
        {
            "ts_code": ["601236.SH"],
            "trade_date": ["20230201"],
            "close": [10.0],
        }
    )

    provider = TuShareProvider(pro=mock_pro)
    df = provider.fetch_stock_daily(["601236.SH"], "2023-02-01", "2023-02-28")

    mock_pro.daily.assert_called_once_with(ts_code="601236.SH", start_date="20230201", end_date="20230228")
    assert "stk_code" in df.columns
    assert "time" in df.columns
    assert df.iloc[0]["stk_code"] == "601236.SH"
    assert df.iloc[0]["time"] == "2023-02-01"
    assert df.iloc[0]["close"] == 10.0
