import pytest
from unittest.mock import MagicMock, patch
import deploy_to_windows
import paramiko

def test_sftp_upload_success():
    with patch("deploy_to_windows.paramiko.SSHClient") as MockSSHClient, \
         patch("deploy_to_windows.os.path.exists", return_value=True):
        
        mock_ssh = MockSSHClient.return_value
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        
        # Mock exec_command to avoid failures in the rest of the script
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_ssh.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
        
        deploy_to_windows.deploy_and_restart()
        
        # Verify SFTP calls
        assert mock_sftp.put.call_count == 2
        calls = mock_sftp.put.call_args_list
        
        assert calls[0][0][0] == "windows_bridge/finance_batch_etl.py"
        assert calls[0][0][1] == f"{deploy_to_windows.WINDOWS_TARGET_DIR}/finance_batch_etl.py"
        
        assert calls[1][0][0] == "windows_bridge/server.py"
        assert calls[1][0][1] == f"{deploy_to_windows.WINDOWS_TARGET_DIR}/server.py"

def test_ssh_connection_error():
    with patch("deploy_to_windows.paramiko.SSHClient") as MockSSHClient:
        mock_ssh = MockSSHClient.return_value
        # Simulate SSH connection error
        mock_ssh.connect.side_effect = paramiko.ssh_exception.SSHException("Connection timed out")
        
        with pytest.raises(Exception, match="Connection timed out"):
            deploy_to_windows.deploy_and_restart()
