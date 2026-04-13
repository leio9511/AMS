import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure the module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import bootstrap_data

class TestBootstrapData(unittest.TestCase):

    @patch('bootstrap_data.xtdata')
    @patch('bootstrap_data.wait_for_download')
    def test_bootstrap_sequential_execution(self, mock_wait, mock_xtdata):
        # Setup mock behavior
        mock_xtdata.download_sector_data = MagicMock()
        mock_xtdata.download_financial_data = MagicMock()

        # Execute
        bootstrap_data.run_bootstrap()

        # Assert sequential calls
        mock_xtdata.download_sector_data.assert_called_once()
        mock_xtdata.download_financial_data.assert_called_once_with(["Capital", "Balance", "Income"])
        mock_wait.assert_called_once()

    @patch('bootstrap_data.xtdata')
    @patch('bootstrap_data.logger')
    @patch('bootstrap_data.wait_for_download')
    def test_bootstrap_error_handling(self, mock_wait, mock_logger, mock_xtdata):
        # Make one of the functions raise an exception
        mock_xtdata.download_sector_data.side_effect = Exception("Mocked API Failure")

        # Execute
        bootstrap_data.run_bootstrap()

        # Assert exception is caught and logged
        mock_logger.error.assert_any_call("Failed to download sector data: Mocked API Failure")
        mock_logger.error.assert_any_call("Bootstrap process encountered an error: Mocked API Failure")
        # Ensure it doesn't proceed to financial data
        mock_xtdata.download_financial_data.assert_not_called()
        mock_wait.assert_not_called()


    @patch('bootstrap_data.os.path.exists', return_value=False)
    @patch('bootstrap_data.time.sleep')
    def test_bootstrap_fallback_path(self, mock_sleep, mock_exists):
        import bootstrap_data
        
        # Create a mock xtdata without data_dir
        mock_xtdata = MagicMock(spec=[])
        
        with patch('bootstrap_data.xtdata', mock_xtdata):
            bootstrap_data.wait_for_download(timeout=1)
            
        mock_exists.assert_called_with(r"C:\qmt\userdata_mini\datadir")

if __name__ == '__main__':
    unittest.main()
