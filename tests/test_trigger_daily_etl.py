"""
Tests for trigger_daily_etl.py
TDD Blueprint:
- Test Case 1: test_trigger_daily_etl_successful_execution
- Test Case 2: test_trigger_daily_etl_ssh_connection_failure
- Test Case 3: test_trigger_daily_etl_daily_sync_failure
- Test Case 4: test_trigger_daily_etl_etl_failure
"""

import pytest
import json
import sys
from unittest.mock import Mock, MagicMock, patch, call


class MockChannel:
    """Mock for SSH channel to handle recv_exit_status"""
    def __init__(self, exit_status=0):
        self.exit_status = exit_status

    def recv_exit_status(self):
        return self.exit_status


class MockStdout:
    """Mock stdout that reads from buffer"""
    def __init__(self, data=b'', channel=None):
        self._data = data
        self.channel = channel or MockChannel()

    def read(self):
        return self._data


class MockStderr:
    """Mock stderr that reads from buffer"""
    def __init__(self, data=b'', channel=None):
        self._data = data
        self.channel = channel or MockChannel()

    def read(self):
        return self._data


class TestTriggerDailyETL:
    """Test suite for trigger_daily_etl.py"""

    def test_trigger_daily_etl_import(self):
        """Test Case 1: Verify the module can be imported without errors."""
        import importlib
        import scripts.trigger_daily_etl as tde_module
        importlib.reload(tde_module)
        
        # Verify the module has the required functions and constants
        assert hasattr(tde_module, 'trigger_daily_etl'), "Missing trigger_daily_etl function"
        assert hasattr(tde_module, 'WINDOWS_HOST'), "Missing WINDOWS_HOST constant"
        assert hasattr(tde_module, 'WINDOWS_USER'), "Missing WINDOWS_USER constant"
        assert hasattr(tde_module, 'DAILY_SYNC_CMD'), "Missing DAILY_SYNC_CMD constant"
        assert hasattr(tde_module, 'FINANCE_ETL_CMD'), "Missing FINANCE_ETL_CMD constant"

    def test_trigger_daily_etl_output_fields(self):
        """Test Case 5: Verify output JSON has all 4 required fields."""
        import importlib
        import scripts.trigger_daily_etl as tde_module
        importlib.reload(tde_module)
        
        # Create a minimal mock that returns valid response
        def mock_exec_command(self, cmd):
            channel = MockChannel(exit_status=0)
            return (MagicMock(),
                    MockStdout(b'OK', channel),
                    MockStderr(b'', channel))
        
        mock_ssh_instance = MagicMock()
        mock_ssh_instance.exec_command = mock_exec_command
        mock_ssh_instance.close = MagicMock()
        
        with patch.object(tde_module.paramiko.SSHClient, '__init__', return_value=None):
            with patch.object(tde_module.paramiko.SSHClient, 'set_missing_host_key_policy'):
                with patch.object(tde_module.paramiko.SSHClient, 'connect'):
                    with patch.object(tde_module.paramiko.SSHClient, 'close', mock_ssh_instance.close):
                        with patch.object(tde_module.paramiko.SSHClient, 'exec_command', mock_ssh_instance.exec_command):
                            with patch.object(tde_module.paramiko.SSHClient, '__call__', return_value=mock_ssh_instance):
                                result = tde_module.trigger_daily_etl()
        
        # Verify all 4 required fields are present
        assert "status" in result, "Missing 'status' field in output"
        assert "daily_sync_output" in result, "Missing 'daily_sync_output' field in output"
        assert "etl_output" in result, "Missing 'etl_output' field in output"
        assert "errors" in result, "Missing 'errors' field in output"
        
        # Verify errors is a list
        assert isinstance(result["errors"], list), "errors should be a list"

    def test_trigger_daily_etl_successful_execution(self):
        """Test Case 1: Mock paramiko SSHClient to simulate successful execution
        of both daily_sync.py and finance_batch_etl.py.
        Assert JSON output has status 'success' and both commands were called."""

        # We need to reimport the module to reset its state
        import importlib
        import scripts.trigger_daily_etl as tde_module
        importlib.reload(tde_module)

        # Track calls
        exec_calls = []

        def mock_exec_command(self, cmd):
            exec_calls.append(cmd)
            channel = MockChannel(exit_status=0)
            if 'daily_sync' in cmd:
                return (MagicMock(),
                        MockStdout(b'Sync completed successfully', channel),
                        MockStderr(b'', channel))
            else:
                return (MagicMock(),
                        MockStdout(b'ETL completed successfully', channel),
                        MockStderr(b'', channel))

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.exec_command = mock_exec_command
        mock_ssh_instance.close = MagicMock()

        with patch.object(tde_module.paramiko.SSHClient, '__init__', return_value=None):
            with patch.object(tde_module.paramiko.SSHClient, 'set_missing_host_key_policy'):
                with patch.object(tde_module.paramiko.SSHClient, 'connect'):
                    with patch.object(tde_module.paramiko.SSHClient, 'close', mock_ssh_instance.close):
                        with patch.object(tde_module.paramiko.SSHClient, 'exec_command', mock_ssh_instance.exec_command):
                            # Patch the return value of SSHClient to be our mock
                            with patch.object(tde_module.paramiko.SSHClient, '__call__', return_value=mock_ssh_instance):
                                result = tde_module.trigger_daily_etl()

        # Assertions
        assert result["status"] == "success", f"Expected status 'success', got '{result['status']}'"
        assert result["daily_sync_output"] == "Sync completed successfully"
        assert result["etl_output"] == "ETL completed successfully"
        assert result["errors"] == []

        # Verify both commands were called (daily_sync + finance_batch_etl)
        assert len(exec_calls) == 2, f"Expected 2 exec_command calls, got {len(exec_calls)}"
        assert 'daily_sync' in exec_calls[0]
        assert 'finance_batch_etl' in exec_calls[1]

    def test_trigger_daily_etl_connection_failure(self):
        """Test Case 2: Mock paramiko to raise an exception on connect.
        Assert JSON output has status 'failed' and errors list contains
        the connection error message."""

        import importlib
        import scripts.trigger_daily_etl as tde_module
        importlib.reload(tde_module)

        connection_error = Exception("Connection refused")

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.close = MagicMock()

        with patch.object(tde_module.paramiko.SSHClient, '__init__', return_value=None):
            with patch.object(tde_module.paramiko.SSHClient, 'set_missing_host_key_policy'):
                with patch.object(tde_module.paramiko.SSHClient, 'connect', side_effect=connection_error):
                    with patch.object(tde_module.paramiko.SSHClient, 'close', mock_ssh_instance.close):
                        result = tde_module.trigger_daily_etl()

        # Assertions
        assert result["status"] == "failed", f"Expected status 'failed', got '{result['status']}'"
        assert len(result["errors"]) > 0
        assert any("Connection refused" in err or "connect" in err.lower() for err in result["errors"])

    def test_trigger_daily_etl_daily_sync_fails(self):
        """Test Case 3: Mock paramiko so daily_sync.py returns non-zero exit.
        Assert JSON output has status 'partial' and errors includes the failure reason."""

        import importlib
        import scripts.trigger_daily_etl as tde_module
        importlib.reload(tde_module)

        exec_calls = []

        def mock_exec_command(self, cmd):
            exec_calls.append(cmd)
            if 'daily_sync' in cmd:
                # daily_sync fails - use channel with exit_status=1 for stdout
                failing_channel = MockChannel(exit_status=1)
                return (MagicMock(),
                        MockStdout(b'', failing_channel),
                        MockStderr(b'Sync failed: data directory not found', failing_channel))
            else:
                # ETL succeeds
                channel = MockChannel(exit_status=0)
                return (MagicMock(),
                        MockStdout(b'ETL completed', channel),
                        MockStderr(b'', channel))

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.exec_command = mock_exec_command
        mock_ssh_instance.close = MagicMock()

        with patch.object(tde_module.paramiko.SSHClient, '__init__', return_value=None):
            with patch.object(tde_module.paramiko.SSHClient, 'set_missing_host_key_policy'):
                with patch.object(tde_module.paramiko.SSHClient, 'connect'):
                    with patch.object(tde_module.paramiko.SSHClient, 'close', mock_ssh_instance.close):
                        with patch.object(tde_module.paramiko.SSHClient, 'exec_command', mock_ssh_instance.exec_command):
                            with patch.object(tde_module.paramiko.SSHClient, '__call__', return_value=mock_ssh_instance):
                                result = tde_module.trigger_daily_etl()

        # Assertions
        assert result["status"] == "partial", f"Expected status 'partial', got '{result['status']}'"
        assert any("daily_sync.py failed" in err for err in result["errors"])
        assert result["etl_output"] == "ETL completed"

    def test_trigger_daily_etl_etl_fails(self):
        """Test Case 4: Mock paramiko so daily_sync succeeds but
        finance_batch_etl.py returns non-zero exit.
        Assert status 'partial' with appropriate error."""

        import importlib
        import scripts.trigger_daily_etl as tde_module
        importlib.reload(tde_module)

        exec_calls = []

        def mock_exec_command(self, cmd):
            exec_calls.append(cmd)
            if 'daily_sync' in cmd:
                # daily_sync succeeds
                channel = MockChannel(exit_status=0)
                return (MagicMock(),
                        MockStdout(b'Sync completed', channel),
                        MockStderr(b'', channel))
            else:
                # ETL fails - use channel with exit_status=1 for stdout
                failing_channel = MockChannel(exit_status=1)
                return (MagicMock(),
                        MockStdout(b'', failing_channel),
                        MockStderr(b'ETL failed: missing fundamentals data', failing_channel))

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.exec_command = mock_exec_command
        mock_ssh_instance.close = MagicMock()

        with patch.object(tde_module.paramiko.SSHClient, '__init__', return_value=None):
            with patch.object(tde_module.paramiko.SSHClient, 'set_missing_host_key_policy'):
                with patch.object(tde_module.paramiko.SSHClient, 'connect'):
                    with patch.object(tde_module.paramiko.SSHClient, 'close', mock_ssh_instance.close):
                        with patch.object(tde_module.paramiko.SSHClient, 'exec_command', mock_ssh_instance.exec_command):
                            with patch.object(tde_module.paramiko.SSHClient, '__call__', return_value=mock_ssh_instance):
                                result = tde_module.trigger_daily_etl()

        # Assertions
        assert result["status"] == "partial", f"Expected status 'partial', got '{result['status']}'"
        assert result["daily_sync_output"] == "Sync completed"
        assert any("finance_batch_etl.py failed" in err for err in result["errors"])


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
