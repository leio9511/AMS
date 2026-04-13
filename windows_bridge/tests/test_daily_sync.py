import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Add windows_bridge to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import daily_sync

class TestDailySync(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.data_dir = self.test_dir.name

    def tearDown(self):
        self.test_dir.cleanup()

    def test_daily_sync_polling_success(self):
        # Mock get_dir_size to simulate increasing size then stabilizing
        sizes = [0, 100, 200, 300, 300, 300, 300]
        
        with patch('daily_sync.get_dir_size', side_effect=sizes):
            # Override sleep to run fast
            with patch('time.sleep', return_value=None):
                success = daily_sync.wait_for_data_stabilization(
                    self.data_dir, 
                    timeout=10, 
                    check_interval=0.1, 
                    required_stable_checks=3
                )
                self.assertTrue(success)

    def test_daily_sync_timeout(self):
        # Mock get_dir_size to never stabilize (constantly increasing)
        def mock_size(path):
            mock_size.current += 10
            return mock_size.current
        mock_size.current = 0

        with patch('daily_sync.get_dir_size', side_effect=mock_size):
            with patch('time.sleep', return_value=None):
                success = daily_sync.wait_for_data_stabilization(
                    self.data_dir, 
                    timeout=0.2, # Short timeout
                    check_interval=0.1, 
                    required_stable_checks=3
                )
                self.assertFalse(success)

    @patch('daily_sync.xtdata')
    def test_daily_sync_fallback_path(self, mock_xtdata):
        # Delete data_dir attribute from mock if it exists
        if hasattr(mock_xtdata, 'data_dir'):
            delattr(mock_xtdata, 'data_dir')
            
        with patch('daily_sync.xtdata', mock_xtdata):
            with patch('daily_sync.xtdata.download_sector_data'):
                with patch('daily_sync.xtdata.download_financial_data'):
                    with patch('daily_sync.wait_for_data_stabilization', return_value=True) as mock_wait:
                        with patch('sys.exit'):
                            import daily_sync
                            daily_sync.main(data_dir=None)
                            
        mock_wait.assert_called_with(r"C:\qmt\userdata_mini\datadir", timeout=300)

if __name__ == '__main__':
    unittest.main()
