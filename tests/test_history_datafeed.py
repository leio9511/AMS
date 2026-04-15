import os
import pandas as pd
import pytest
from ams.core.history_datafeed import HistoryDataFeed

@pytest.fixture
def mock_csv(tmp_path):
    df = pd.DataFrame({
        "date": ["2024-02-04", "2024-02-05", "2024-02-05", "2024-02-06"],
        "ticker": ["110059.XSHG", "110059.XSHG", "113050.XSHG", "110059.XSHG"],
        "close": [100.0, 101.0, 102.0, 103.0]
    })
    file_path = tmp_path / "mock_cb_data.csv"
    df.to_csv(file_path, index=False)
    return str(file_path)

def test_history_datafeed_initialization(mock_csv):
    # Successfully loads a mock CSV file into memory without error
    feed = HistoryDataFeed(file_path=mock_csv)
    assert not feed.data.empty
    assert len(feed.data) == 4

def test_history_datafeed_get_data_exact_date(mock_csv):
    # Calling get_data('2024-02-05') returns only rows for '2024-02-05', and strictly NO future dates
    feed = HistoryDataFeed(file_path=mock_csv)
    df_slice = feed.get_data('2024-02-05')
    assert len(df_slice) == 2
    assert all(df_slice['date'] == '2024-02-05')
    
    # Assert ticker correctly included
    tickers = set(df_slice['ticker'].tolist())
    assert tickers == {"110059.XSHG", "113050.XSHG"}

def test_history_datafeed_get_data_missing_date(mock_csv):
    # Calling get_data('2099-01-01') returns an empty DataFrame without crashing
    feed = HistoryDataFeed(file_path=mock_csv)
    df_slice = feed.get_data('2099-01-01')
    assert df_slice.empty
    assert "date" in df_slice.columns
