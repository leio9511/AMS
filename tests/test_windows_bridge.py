import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure the module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from windows_bridge import bootstrap_data

class TestWindowsBridge(unittest.TestCase):
    
    @patch('windows_bridge.bootstrap_data.xtdata')
    @patch('windows_bridge.bootstrap_data.wait_for_download')
    def test_bootstrap_data_calls(self, mock_wait, mock_xtdata):
        """
        Mock xtdata and ensure bootstrap_data.py invokes all required bulk download 
        methods for sector and financial data exactly once without errors.
        """
        # Setup mock behavior
        mock_xtdata.download_sector_data = MagicMock()
        mock_xtdata.download_financial_data = MagicMock()

        # Execute
        bootstrap_data.run_bootstrap()

        # Assert calls
        mock_xtdata.download_sector_data.assert_called_once()
        mock_xtdata.download_financial_data.assert_called_once_with(["Capital", "Balance", "Income"])
        mock_wait.assert_called_once()

if __name__ == '__main__':
    unittest.main()
