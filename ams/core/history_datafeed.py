from ams.core.base import BaseDataFeed
import pandas as pd

class HistoryDataFeed(BaseDataFeed):
    def __init__(self, data: pd.DataFrame):
        self.data = data
        self.data['date'] = pd.to_datetime(self.data['date'])

    def get_data(self, tickers, date):
        date = pd.to_datetime(date)
        if tickers is None:
            return self.data[self.data['date'] == date]
        return self.data[(self.data['date'] == date) & (self.data['ticker'].isin(tickers))]
