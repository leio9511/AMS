from abc import ABC, abstractmethod
import pandas as pd

class DataProviderError(Exception):
    """Base class for data provider errors."""
    pass

class DataProviderAuthError(DataProviderError):
    """Raised when authentication with the data provider fails."""
    pass

class DataProviderQuotaError(DataProviderError):
    """Raised when the data provider quota is exceeded."""
    pass

class BaseDataProvider(ABC):
    @abstractmethod
    def fetch_cb_basic(self) -> pd.DataFrame:
        """Fetch basic information for all convertible bonds."""
        pass

    @abstractmethod
    def fetch_cb_daily(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch daily price data for convertible bonds.
        
        :param tickers: List of full tickers (e.g., ['127076.SZ', '110001.SH']).
        :param start_date: Start date in YYYY-MM-DD format.
        :param end_date: End date in YYYY-MM-DD format.
        """
        pass

    @abstractmethod
    def fetch_cb_price_changes(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch historical conversion price changes or related valuation data.
        
        :param tickers: List of full tickers (e.g., ['127076.SZ', '110001.SH']).
        :param start_date: Start date in YYYY-MM-DD format.
        :param end_date: End date in YYYY-MM-DD format.
        """
        pass

    @abstractmethod
    def fetch_stock_st_by_date(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch ST status for stocks by date.
        
        :param tickers: List of full stock tickers (e.g., ['000001.SZ', '600000.SH']).
        :param start_date: Start date in YYYY-MM-DD format.
        :param end_date: End date in YYYY-MM-DD format.
        """
        pass

    @abstractmethod
    def fetch_trade_calendar(self, start_date: str, end_date: str) -> list:
        """Fetch trading calendar days."""
        pass

    @abstractmethod
    def fetch_all_securities(self, types: list[str] = ["conbond"]) -> pd.DataFrame:
        """Fetch a list of all securities of specified types."""
        pass
