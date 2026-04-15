import os
import pandas as pd
from ams.core.base import BaseDataFeed

class HistoryDataFeed(BaseDataFeed):
    def __init__(self, file_path="data/cb_history_factors.csv", data=None):
        if data is not None and isinstance(data, pd.DataFrame):
            self.data = data.copy()
            self.file_path = None
        elif isinstance(file_path, pd.DataFrame):
            self.data = file_path.copy()
            self.file_path = None
        else:
            self.file_path = file_path
            if not os.path.exists(self.file_path):
                self.data = pd.DataFrame(columns=["date", "ticker"])
            else:
                self.data = pd.read_csv(self.file_path)
                
        self.data['date'] = pd.to_datetime(self.data['date'])
        self.data.set_index('date', drop=False, inplace=True)

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
