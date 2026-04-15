import os
import pytest
from unittest.mock import patch, MagicMock
from scripts.jqdata_sync_cb import sync_cb_data

@patch.dict(os.environ, {}, clear=True)
def test_jqdata_auth_failure():
    with pytest.raises(ValueError, match="Missing JQDATA_USER or JQDATA_PWD environment variables"):
        sync_cb_data()

@patch.dict(os.environ, {"JQDATA_USER": "test_user", "JQDATA_PWD": "test_password"}, clear=True)
@patch('scripts.jqdata_sync_cb.jqdatasdk')
def test_jqdata_successful_sync(mock_jqdatasdk):
    # Mock auth success
    mock_jqdatasdk.auth.return_value = None
    
    # Run sync
    sync_cb_data()
    
    # Check if csv created
    assert os.path.exists("data/cb_history_factors.csv")
