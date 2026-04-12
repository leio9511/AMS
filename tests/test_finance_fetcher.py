import sys
import os
import unittest
from unittest.mock import patch
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scripts.finance_fetcher import fetch_fundamental_data

class TestFinanceFetcher(unittest.TestCase):
    @patch('scripts.finance_fetcher.ak.stock_zh_a_spot_em')
    def test_fetch_fundamental_data_columns(self, mock_ak):
        mock_ak.return_value = pd.DataFrame({
            '代码': ['600000', '600004'],
            '市盈率-动态': [5.0, 10.0],
            '总市值': [1e8, 2e8]
        })
        df = fetch_fundamental_data()
        self.assertIsInstance(df, pd.DataFrame)
        self.assertIn('代码', df.columns)
        self.assertIn('市盈率-动态', df.columns)
        self.assertIn('总市值', df.columns)
        
    @patch('scripts.finance_fetcher.ak.stock_zh_a_spot_em')
    def test_fetch_fundamental_data_authenticity(self, mock_ak):
        mock_ak.return_value = pd.DataFrame({
            '代码': ['600000', '600004', '000001'],
            '市盈率-动态': [5.0, 10.0, 15.0],
            '总市值': [1e8, 2e8, 3e8]
        })
        df = fetch_fundamental_data()
        unique_pe = len(df['市盈率-动态'].dropna().unique())
        self.assertTrue(unique_pe > 1, f"Expected unique PE values > 1, got {unique_pe}. Data is a stub!")

if __name__ == '__main__':
    unittest.main()
