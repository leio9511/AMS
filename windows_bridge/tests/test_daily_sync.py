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

if __name__ == '__main__':
    unittest.main()
