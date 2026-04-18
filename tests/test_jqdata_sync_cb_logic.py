import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import os
from scripts.jqdata_sync_cb import sync_cb_data

class TestJQDataSyncCBLogic(unittest.TestCase):
    def setUp(self):
        self.start_date = "2024-01-01"
        self.end_date = "2024-01-05"
        self.ticker = "123456.XSHG"
        self.underlying = "600000.XSHG"

    @patch('scripts.jqdata_sync_cb.jqdatasdk')
    @patch('ams.validators.cb_data_validator.CBDataValidator')
    def test_fetch_real_premium_rate(self, mock_validator, mock_jq):
        # Setup env vars for logic
        os.environ['JQDATA_USER'] = 'test'
        os.environ['JQDATA_PWD'] = 'test'
        # Setup mocks
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        
        # Mock query attributes to avoid TypeError with >=
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        
        # Mock price data
        # Mock finance query attributes
        mock_jq.finance.CCB_CALL.code.in_.return_value = True
        mock_jq.finance.run_query.return_value = pd.DataFrame({'code': [self.ticker], 'pub_date': ['2024-01-05'], 'delisting_date': ['2024-01-12']})
        price_data = pd.DataFrame({
            'open': [100.0] * 5,
            'high': [101.0] * 5,
            'low': [99.0] * 5,
            'close': [100.0] * 5,
            'volume': [1000] * 5,
        }, index=pd.MultiIndex.from_product([pd.to_datetime(['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05']), [self.ticker]], names=['time', 'code']))
        mock_jq.get_price.return_value = price_data
        
        # Mock security info
        mock_info = MagicMock()
        mock_info.parent = self.underlying
        mock_jq.get_security_info.return_value = mock_info
        
        # Mock premium data
        premium_data = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'],
            'code': [self.ticker] * 5,
            'convert_premium_rate': [10.0, 15.0, 20.0, 25.0, 30.0]
        })
        mock_jq.bond.run_query.side_effect = [
            pd.DataFrame({'code': [self.ticker], 'delist_Date': ['2024-12-31']}), # df_bonds_info
            premium_data # df_premium
        ]
        
        # Mock ST status
        st_data = pd.DataFrame({self.underlying: [False, False, True, True, False]}, 
                              index=pd.to_datetime(['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05']))
        mock_jq.get_extras.return_value = st_data
        
        # Mock validator
        mock_validator.return_value.validate_dataframe.return_value = True
        
        # Run sync
        sync_cb_data(self.start_date, self.end_date)
        
        # Verify output
        df = pd.read_csv("data/cb_history_factors.csv")
        self.assertTrue((df['premium_rate'] > 0).all())
        self.assertEqual(df['premium_rate'].iloc[0], 0.1) # 10.0 / 100
        self.assertEqual(df['premium_rate'].iloc[4], 0.3) # 30.0 / 100

    @patch('scripts.jqdata_sync_cb.jqdatasdk')
    @patch('ams.validators.cb_data_validator.CBDataValidator')
    def test_fetch_st_status(self, mock_validator, mock_jq):
        # Setup env vars for logic
        os.environ['JQDATA_USER'] = 'test'
        os.environ['JQDATA_PWD'] = 'test'
        # Similar setup but focusing on is_st
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        
        # Mock query attributes
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        
        # Mock finance query attributes
        mock_jq.finance.CCB_CALL.code.in_.return_value = True
        mock_jq.finance.run_query.return_value = pd.DataFrame({'code': [self.ticker], 'pub_date': ['2024-01-05'], 'delisting_date': ['2024-01-12']})
        price_data = pd.DataFrame({
            'open': [100.0], 'high': [101.0], 'low': [99.0], 'close': [100.0], 'volume': [1000],
        }, index=pd.MultiIndex.from_tuples([(pd.to_datetime('2024-01-03'), self.ticker)], names=['time', 'code']))
        mock_jq.get_price.return_value = price_data
        
        mock_info = MagicMock()
        mock_info.parent = self.underlying
        mock_jq.get_security_info.return_value = mock_info
        
        mock_jq.bond.run_query.side_effect = [
            pd.DataFrame({'code': [self.ticker], 'delist_Date': ['2024-12-31']}), # df_bonds_info
            pd.DataFrame({'date': ['2024-01-03'], 'code': [self.ticker], 'convert_premium_rate': [10.0]}) # df_premium
        ]
        
        st_data = pd.DataFrame({self.underlying: [True]}, index=pd.to_datetime(['2024-01-03']))
        mock_jq.get_extras.return_value = st_data
        
        mock_validator.return_value.validate_dataframe.return_value = True
        
        sync_cb_data("2024-01-03", "2024-01-03")
        
        df = pd.read_csv("data/cb_history_factors.csv")
        self.assertTrue(df['is_st'].iloc[0])

    @patch('scripts.jqdata_sync_cb.jqdatasdk')
    @patch('ams.validators.cb_data_validator.CBDataValidator')
    def test_redemption_logic(self, mock_validator, mock_jq):
        # Setup env vars for logic
        os.environ['JQDATA_USER'] = 'test'
        os.environ['JQDATA_PWD'] = 'test'
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        
        # Mock query attributes
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        
        # Mock finance query attributes
        mock_jq.finance.CCB_CALL.code.in_.return_value = True
        mock_jq.finance.run_query.return_value = pd.DataFrame({'code': [self.ticker], 'pub_date': ['2024-01-05'], 'delisting_date': ['2024-01-12']})
        price_data = pd.DataFrame({
            'open': [100.0, 100.0], 'high': [101.0, 101.0], 'low': [99.0, 99.0], 'close': [100.0, 100.0], 'volume': [1000, 1000],
        }, index=pd.MultiIndex.from_tuples([
            (pd.to_datetime('2024-01-03'), self.ticker),
            (pd.to_datetime('2024-01-10'), self.ticker)
        ], names=['time', 'code']))
        mock_jq.get_price.return_value = price_data
        
        mock_info = MagicMock()
        mock_info.parent = self.underlying
        mock_jq.get_security_info.return_value = mock_info
        
        mock_jq.bond.run_query.side_effect = [
            pd.DataFrame({'code': [self.ticker], 'delist_Date': ['2024-01-10']}), # delist on 10th
            pd.DataFrame({
                'date': ['2024-01-03', '2024-01-10'], 
                'code': [self.ticker, self.ticker], 
                'convert_premium_rate': [10.0, 10.0]
            })
        ]
        
        mock_jq.get_extras.return_value = pd.DataFrame({self.underlying: [False, False]}, index=pd.to_datetime(['2024-01-03', '2024-01-10']))
        mock_validator.return_value.validate_dataframe.return_value = True
        
        sync_cb_data("2024-01-01", "2024-01-10")
        
        df = pd.read_csv("data/cb_history_factors.csv")
        # is_redeemed should be True on the 10th
        self.assertFalse(df[df['date'] == '2024-01-03']['is_redeemed'].iloc[0])
        self.assertTrue(df[df['date'] == '2024-01-10']['is_redeemed'].iloc[0])

if __name__ == '__main__':
    unittest.main()
