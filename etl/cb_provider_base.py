from abc import ABC, abstractmethod
from enum import Enum

import pandas as pd


class DataProviderFailureStatus(str, Enum):
    """Externally observable provider failure statuses for degraded-mode gating."""

    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    AUTH_FAILED = "AUTH_FAILED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RUNTIME_BUG = "RUNTIME_BUG"


class DataProviderError(Exception):
    """Base class for data provider errors."""

    failure_status = DataProviderFailureStatus.RUNTIME_BUG

    @property
    def status(self) -> str:
        return self.failure_status.value


class DataProviderAuthError(DataProviderError):
    """Raised when authentication with the data provider fails."""

    failure_status = DataProviderFailureStatus.AUTH_FAILED


class DataProviderQuotaError(DataProviderError):
    """Raised when the data provider quota is exceeded."""

    failure_status = DataProviderFailureStatus.QUOTA_EXCEEDED


class DataProviderNetworkUnavailableError(DataProviderError):
    """Raised when the data provider is unreachable or upstream is unavailable."""

    failure_status = DataProviderFailureStatus.NETWORK_UNAVAILABLE


class DataProviderRuntimeBugError(DataProviderError):
    """Raised when provider adapter mapping/parsing/runtime logic fails."""

    failure_status = DataProviderFailureStatus.RUNTIME_BUG

class BaseDataProvider(ABC):
    @abstractmethod
    def fetch_cb_basic(self) -> pd.DataFrame:
        """Fetch basic information for all convertible bonds."""
        pass

    @abstractmethod
    def fetch_cb_daily(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch daily price data for convertible bonds using full tickers.
        
        :param tickers: List of full tickers (e.g., ['127076.SZ', '110001.SH']). Full ticker contract is required.
        :param start_date: Start date in YYYY-MM-DD format.
        :param end_date: End date in YYYY-MM-DD format.
        """
        pass

    @abstractmethod
    def fetch_cb_price_changes(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch historical conversion price changes or related valuation data using full tickers.
        
        :param tickers: List of full tickers (e.g., ['127076.SZ', '110001.SH']). Full ticker contract is required.
        :param start_date: Start date in YYYY-MM-DD format.
        :param end_date: End date in YYYY-MM-DD format.
        """
        pass

    @abstractmethod
    def fetch_stock_daily(self, tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch underlying stock daily price data using full tickers.

        :param tickers: List of full stock tickers (e.g., ['000001.SZ', '600000.SH']).
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
