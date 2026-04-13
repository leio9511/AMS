import pytest
from unittest.mock import MagicMock, patch
import os
import deploy_to_windows
import paramiko

def test_deployment_script_uploads_all_four_files():
    with patch("deploy_to_windows.paramiko.SSHClient") as MockSSHClient, \
         patch("deploy_to_windows.os.path.exists", return_value=True):
        
        mock_ssh = MockSSHClient.return_value
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_ssh.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
        
        deploy_to_windows.deploy_and_restart()
        
        assert mock_sftp.put.call_count == 4
        calls = mock_sftp.put.call_args_list
        base_dir = os.path.abspath(os.path.dirname(deploy_to_windows.__file__))
        
        assert calls[0][0][0] == os.path.join(base_dir, "windows_bridge/finance_batch_etl.py")
        assert calls[0][0][1] == f"{deploy_to_windows.WINDOWS_TARGET_DIR}/finance_batch_etl.py"
        
        assert calls[1][0][0] == os.path.join(base_dir, "windows_bridge/server.py")
        assert calls[1][0][1] == f"{deploy_to_windows.WINDOWS_TARGET_DIR}/server.py"

        assert calls[2][0][0] == os.path.join(base_dir, "windows_bridge/daily_sync.py")
        assert calls[2][0][1] == f"{deploy_to_windows.WINDOWS_TARGET_DIR}/daily_sync.py"

        assert calls[3][0][0] == os.path.join(base_dir, "windows_bridge/bootstrap_data.py")
        assert calls[3][0][1] == f"{deploy_to_windows.WINDOWS_TARGET_DIR}/bootstrap_data.py"

def test_absolute_paths_constructed_from_file_location():
    # Similar to above, verify the exact args use os.path.join with base_dir
    with patch("deploy_to_windows.paramiko.SSHClient") as MockSSHClient, \
         patch("deploy_to_windows.os.path.exists", return_value=True):
        mock_sftp = MagicMock()
        MockSSHClient.return_value.open_sftp.return_value = mock_sftp
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        MockSSHClient.return_value.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
        
        deploy_to_windows.deploy_and_restart()
        
        calls = mock_sftp.put.call_args_list
        for call in calls:
            local_path = call[0][0]
            assert os.path.isabs(local_path)
