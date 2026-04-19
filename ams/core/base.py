import abc

class BaseStrategy(abc.ABC):
    @abc.abstractmethod
    def on_bar(self, context, data):
        pass

    @abc.abstractmethod
    def generate_target_portfolio(self, context, data):
        pass

class BaseDataFeed(abc.ABC):
    @abc.abstractmethod
    def get_data(self, tickers, date):
        pass

class BaseBroker(abc.ABC):
    @abc.abstractmethod
    def order_target_percent(self, ticker, percent):
        pass
