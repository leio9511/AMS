from ams.core.base import BaseStrategy
import pandas as pd

class CBRotationStrategy(BaseStrategy):
    def __init__(self, top_n=5):
        self.top_n = top_n

    def on_bar(self, context, data):
        pass

    def generate_target_portfolio(self, context, data):
        if data is None or data.empty:
            return {}

        df = data.copy()

        # ST filter
        if 'is_st' in df.columns:
            df = df[~df['is_st']]

        # Stop loss logic -8%
        if 'daily_return' in df.columns:
            df = df[df['daily_return'] > -0.08]

        # Double low calculation
        if 'price' in df.columns and 'premium' in df.columns:
            df['double_low'] = df['price'] + df['premium']
            df = df.sort_values(by='double_low', ascending=True)

        target_portfolio = {}
        selected = df.head(self.top_n)
        if not selected.empty:
            weight = 1.0 / len(selected)
            for ticker in selected['ticker']:
                target_portfolio[ticker] = weight

        return target_portfolio
