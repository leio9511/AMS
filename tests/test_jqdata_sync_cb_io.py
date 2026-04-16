import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import os
import shutil
from scripts.jqdata_sync_cb import sync_cb_data
from ams.validators.cb_data_validator import CBDataValidator

class TestJQDataSyncCBIO(unittest.TestCase):
    def setUp(self):
        self.output_path = "data/cb_history_factors.csv"
        self.bak_path = "data/cb_history_factors.csv.bak"
        self.tmp_path = "data/cb_history_factors.csv.tmp"
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        # Clean up before tests
        for p in [self.output_path, self.bak_path, self.tmp_path]:
            if os.path.exists(p):
                os.remove(p)

    def tearDown(self):
        # Clean up after tests
        for p in [self.output_path, self.bak_path, self.tmp_path]:
            if os.path.exists(p):
                os.remove(p)

    @patch('scripts.jqdata_sync_cb.jqdatasdk')
    @patch('scripts.jqdata_sync_cb.pd.DataFrame.to_csv')
    @patch('scripts.jqdata_sync_cb.pd.read_csv')
    @patch('ams.validators.cb_data_validator.CBDataValidator.validate_dataframe')
    def test_atomic_write_success(self, mock_validate, mock_read_csv, mock_to_csv, mock_jq):
        # Setup mocks
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=["123456.XSHG"])
        mock_jq.get_price.return_value = pd.DataFrame({'open': [100.0], 'high': [101.0], 'low': [99.0], 'close': [100.0], 'volume': [1000]}, index=pd.MultiIndex.from_tuples([(pd.to_datetime('2024-01-01'), "123456.XSHG")], names=['time', 'code']))
        
        # Mock run_query to return expected columns
        mock_jq.bond.run_query.return_value = pd.DataFrame(columns=['code', 'delist_Date', 'date', 'convert_premium_rate'])
        mock_jq.get_extras.return_value = pd.DataFrame()
        
        # Mock query attributes to avoid TypeError
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        
        mock_read_csv.return_value = pd.DataFrame({
            "ticker": ["123456.XSHG"],
            "date": ["2024-01-01"],
            "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000],
            "premium_rate": [0.0], "double_low": [100.0], "underlying_ticker": [None],
            "is_st": [False], "is_redeemed": [False]
        })
        mock_validate.return_value = True

        # Write a dummy tmp file to simulate to_csv
        def fake_to_csv(path, **kwargs):
            with open(path, 'w') as f:
                f.write("dummy")
        mock_to_csv.side_effect = fake_to_csv

        # Pre-create tmp file manually as we mocked to_csv
        with open(self.tmp_path, 'w') as f:
            f.write("dummy")
            
        with patch('os.replace') as mock_replace:
            sync_cb_data("2024-01-01", "2024-01-01")
            mock_replace.assert_called_once_with(self.tmp_path, self.output_path)

    @patch('scripts.jqdata_sync_cb.jqdatasdk')
    @patch('scripts.jqdata_sync_cb.pd.DataFrame.to_csv')
    @patch('scripts.jqdata_sync_cb.pd.read_csv')
    @patch('ams.validators.cb_data_validator.CBDataValidator.validate_dataframe')
    def test_validation_interception(self, mock_validate, mock_read_csv, mock_to_csv, mock_jq):
        # Setup mocks
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=["123456.XSHG"])
        mock_jq.get_price.return_value = pd.DataFrame({'open': [100.0], 'high': [101.0], 'low': [99.0], 'close': [100.0], 'volume': [1000]}, index=pd.MultiIndex.from_tuples([(pd.to_datetime('2024-01-01'), "123456.XSHG")], names=['time', 'code']))
        
        # Mock run_query
        mock_jq.bond.run_query.return_value = pd.DataFrame(columns=['code', 'delist_Date', 'date', 'convert_premium_rate'])
        mock_jq.get_extras.return_value = pd.DataFrame()
        
        # Mock query attributes
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        
        mock_read_csv.return_value = pd.DataFrame({
            "ticker": ["123456.XSHG"],
            "date": ["2024-01-01"],
            "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000],
            "premium_rate": [float('nan')], "double_low": [100.0], "underlying_ticker": [None],
            "is_st": [False], "is_redeemed": [False]
        })
        mock_validate.return_value = False

        def fake_to_csv(path, **kwargs):
            with open(path, 'w') as f:
                f.write("dirty_data")
        mock_to_csv.side_effect = fake_to_csv
        
        # ensure output_path doesn't exist
        if os.path.exists(self.output_path):
            os.remove(self.output_path)

        with patch('os.replace') as mock_replace:
            # capture output
            from io import StringIO
            import sys
            captured_output = StringIO()
            sys.stdout = captured_output
            
            sync_cb_data("2024-01-01", "2024-01-01")
            
            sys.stdout = sys.__stdout__
            
            mock_replace.assert_not_called()
            self.assertIn("[DataContractViolation]", captured_output.getvalue())
            self.assertFalse(os.path.exists(self.output_path))
            self.assertFalse(os.path.exists(self.tmp_path))

    @patch('scripts.jqdata_sync_cb.jqdatasdk')
    def test_backup_creation(self, mock_jq):
        # Create a dummy output file before running
        with open(self.output_path, 'w') as f:
            f.write("old_data")
            
        # Exception to stop the script right after backup
        mock_jq.auth.side_effect = Exception("Stop early")
        
        try:
            sync_cb_data("2024-01-01", "2024-01-01")
        except RuntimeError:
            pass
            
        self.assertTrue(os.path.exists(self.bak_path))
        with open(self.bak_path, 'r') as f:
            self.assertEqual(f.read(), "old_data")

    @patch('scripts.jqdata_sync_cb.jqdatasdk')
    @patch('scripts.jqdata_sync_cb.pd.read_csv')
    @patch('scripts.jqdata_sync_cb.pd.DataFrame.to_csv')
    def test_validator_integration(self, mock_to_csv, mock_read_csv, mock_jq):
        # Verify that CBDataValidator is imported and instantiated correctly
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=["123456.XSHG"])
        mock_jq.get_price.return_value = pd.DataFrame({'open': [100.0], 'high': [101.0], 'low': [99.0], 'close': [100.0], 'volume': [1000]}, index=pd.MultiIndex.from_tuples([(pd.to_datetime('2024-01-01'), "123456.XSHG")], names=['time', 'code']))
        
        # Mock run_query
        mock_jq.bond.run_query.return_value = pd.DataFrame(columns=['code', 'delist_Date', 'date', 'convert_premium_rate'])
        mock_jq.get_extras.return_value = pd.DataFrame()
        
        # Mock query attributes
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        
        mock_read_csv.return_value = pd.DataFrame({
            "ticker": ["123456.XSHG"],
            "date": ["2024-01-01"],
            "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000],
            "premium_rate": [0.0], "double_low": [100.0], "underlying_ticker": ["000001.XSHE"],
            "is_st": [False], "is_redeemed": [False]
        })
        
        with patch('ams.validators.cb_data_validator.CBDataValidator') as mock_validator_class:
            mock_validator_instance = MagicMock()
            mock_validator_class.return_value = mock_validator_instance
            mock_validator_instance.validate_dataframe.return_value = False # fail to skip replace
            
            with patch('os.replace'):
                sync_cb_data("2024-01-01", "2024-01-01")
                
            mock_validator_class.assert_called_once()
            mock_validator_instance.validate_dataframe.assert_called_once()

if __name__ == '__main__':
    unittest.main()
