import unittest
from unittest.mock import patch, mock_open, MagicMock
import sys

# Mock xtdata to prevent ImportError and allow patching
sys.modules['xtquant'] = MagicMock()
sys.modules['xtquant.xtdata'] = MagicMock()

import windows_bridge.finance_batch_etl as etl

class TestFinanceBatchEtl(unittest.TestCase):
    @patch('windows_bridge.finance_batch_etl.xtdata')
    @patch('windows_bridge.finance_batch_etl.process_financial_data')
    @patch('builtins.open', new_callable=mock_open)
    @patch('json.dump')
    def test_etl_fetches_multiple_sectors(self, mock_json_dump, mock_file_open, mock_process, mock_xtdata):
        def get_stock_list_mock(sector):
            if sector == '沪深A股':
                return ['A1', 'A2']
            elif sector == '沪深ETF':
                return ['E1', 'A1']
            elif sector == '沪深转债':
                return ['C1']
            return []
            
        mock_xtdata.get_stock_list_in_sector.side_effect = get_stock_list_mock
        mock_process.return_value = {'mock': 'data'}
        
        etl.main()
        
        mock_xtdata.get_stock_list_in_sector.assert_any_call('沪深A股')
        mock_xtdata.get_stock_list_in_sector.assert_any_call('沪深ETF')
        mock_xtdata.get_stock_list_in_sector.assert_any_call('沪深转债')
        
        args, _ = mock_process.call_args
        processed_list = args[0]
        self.assertEqual(len(processed_list), 4)
        self.assertSetEqual(set(processed_list), {'A1', 'A2', 'E1', 'C1'})
        
        mock_json_dump.assert_called_once_with({'mock': 'data'}, mock_file_open(), ensure_ascii=False, indent=2)

if __name__ == '__main__':
    unittest.main()
