import os
import pandas as pd
import pytest
from unittest.mock import patch
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


@pytest.fixture
def legacy_snapshot_csv(tmp_path):
    df = pd.DataFrame({
        "date": ["2024-02-05", "2024-02-05"],
        "ticker": ["110059.XSHG", "113050.XSHG"],
        "close": [101.0, 102.0],
    })
    file_path = tmp_path / "legacy_snapshot.csv"
    df.to_csv(file_path, index=False)
    return str(file_path)


@pytest.fixture
def explicit_split_snapshot_csv(tmp_path):
    df = pd.DataFrame({
        "date": ["2024-02-05", "2024-02-05"],
        "ticker": ["110059.XSHG", "113050.XSHG"],
        "close": [101.0, 102.0],
        "redeem_risk": [True, False],
        "is_redeemed": [False, True],
    })
    file_path = tmp_path / "explicit_split_snapshot.csv"
    df.to_csv(file_path, index=False)
    return str(file_path)


def test_history_datafeed_default_path_uses_project_local_contract():
    expected_path = "/tmp/project-local-default.csv"

    with patch("ams.core.history_datafeed.get_provider_artifact_paths", return_value={"dataset_path": expected_path}):
        feed = HistoryDataFeed()

    assert feed.file_path == expected_path
    assert feed.data.empty
    assert list(feed.data.columns) == ["date", "ticker", "redeem_risk", "is_redeemed"]


def test_history_datafeed_initialization(mock_csv):
    feed = HistoryDataFeed(file_path=mock_csv)
    assert not feed.data.empty
    assert len(feed.data) == 4


def test_history_datafeed_backfills_missing_redemption_split_flags_for_legacy_snapshots(legacy_snapshot_csv):
    feed = HistoryDataFeed(file_path=legacy_snapshot_csv)

    assert list(feed.data["redeem_risk"].tolist()) == [False, False]
    assert list(feed.data["is_redeemed"].tolist()) == [False, False]
    assert pd.api.types.is_bool_dtype(feed.data["redeem_risk"])
    assert pd.api.types.is_bool_dtype(feed.data["is_redeemed"])


def test_history_datafeed_preserves_explicit_redemption_split_flags(explicit_split_snapshot_csv):
    feed = HistoryDataFeed(file_path=explicit_split_snapshot_csv)

    assert list(feed.data["redeem_risk"].tolist()) == [True, False]
    assert list(feed.data["is_redeemed"].tolist()) == [False, True]


def test_history_datafeed_get_data_exact_date(mock_csv):
    feed = HistoryDataFeed(file_path=mock_csv)
    df_slice = feed.get_data('2024-02-05')

    assert len(df_slice) == 2
    assert all(df_slice['date'] == pd.Timestamp('2024-02-05'))
    assert set(df_slice['ticker'].tolist()) == {"110059.XSHG", "113050.XSHG"}


def test_history_datafeed_get_data_missing_date(mock_csv):
    feed = HistoryDataFeed(file_path=mock_csv)
    df_slice = feed.get_data('2099-01-01')
    assert df_slice.empty
    assert "date" in df_slice.columns
