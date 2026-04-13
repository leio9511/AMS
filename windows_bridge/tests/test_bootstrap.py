import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure the module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import bootstrap_data

class TestBootstrapData(unittest.TestCase):

    @patch('bootstrap_data.xtdata')
    def test_bootstrap_sequential_execution(self, mock_xtdata):
        # Setup mock behavior
        mock_xtdata.download_sector_data = MagicMock()
        mock_xtdata.download_financial_data = MagicMock()

        # Execute
        bootstrap_data.run_bootstrap()

        # Assert sequential calls
        mock_xtdata.download_sector_data.assert_called_once()
        mock_xtdata.download_financial_data.assert_called_once_with(["Capital", "Balance", "Income"])

    @patch('bootstrap_data.xtdata')
    @patch('bootstrap_data.logger')
    def test_bootstrap_error_handling(self, mock_logger, mock_xtdata):
        # Make one of the functions raise an exception
        mock_xtdata.download_sector_data.side_effect = Exception("Mocked API Failure")

        # Execute
        bootstrap_data.run_bootstrap()

        # Assert exception is caught and logged
        mock_logger.error.assert_any_call("Failed to download sector data: Mocked API Failure")
        mock_logger.error.assert_any_call("Bootstrap process encountered an error: Mocked API Failure")
        # Ensure it doesn't proceed to financial data
        mock_xtdata.download_financial_data.assert_not_called()

if __name__ == '__main__':
    unittest.main()
