import os
import pandas as pd
from ams.core.base import BaseDataFeed
from ams.utils.provider_config import get_provider_artifact_paths


class HistoryDataFeed(BaseDataFeed):
    REDEMPTION_SPLIT_COLUMNS = ["redeem_risk", "is_redeemed"]

    def __init__(self, file_path=None, data=None):
        if data is not None and isinstance(data, pd.DataFrame):
            self.data = data.copy()
            self.file_path = None
        elif isinstance(file_path, pd.DataFrame):
            self.data = file_path.copy()
            self.file_path = None
        else:
            resolved_file_path = file_path or get_provider_artifact_paths()["dataset_path"]
            self.file_path = resolved_file_path
            if not os.path.exists(self.file_path):
                self.data = pd.DataFrame(columns=["date", "ticker", *self.REDEMPTION_SPLIT_COLUMNS])
            else:
                self.data = pd.read_csv(self.file_path)

        self._ensure_redemption_split_columns()
        self.data['date'] = pd.to_datetime(self.data['date'])
        self.data.set_index('date', drop=False, inplace=True)

    def _ensure_redemption_split_columns(self):
        for column in self.REDEMPTION_SPLIT_COLUMNS:
            if column not in self.data.columns:
                self.data[column] = pd.Series(False, index=self.data.index, dtype="bool")

    def get_data(self, arg1=None, arg2=None):
        """Return a DataFrame slice for exactly the requested date."""
        if isinstance(arg1, (str, pd.Timestamp)):
            date = arg1
            tickers = arg2
        elif isinstance(arg2, (str, pd.Timestamp)):
            date = arg2
            tickers = arg1
        else:
            date = arg1
            tickers = arg2

        try:
            date_obj = pd.to_datetime(date)
            slice_df = self.data.loc[[date_obj]].reset_index(drop=True)
        except KeyError:
            return pd.DataFrame(columns=self.data.columns)

        if tickers is not None:
            slice_df = slice_df[slice_df['ticker'].isin(tickers)]

        return slice_df
