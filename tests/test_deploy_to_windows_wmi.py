import pytest
from unittest.mock import MagicMock, patch
import logging
import deploy_to_windows

def test_wmi_commands_success():
    with patch("deploy_to_windows.paramiko.SSHClient") as MockSSHClient, \
         patch("deploy_to_windows.os.path.exists", return_value=True):
        
        mock_ssh = MockSSHClient.return_value
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        
        # Setup mock stdout/stderr for exec_command
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        
        mock_ssh.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
        
        deploy_to_windows.deploy_and_restart()
        
        # Verify SFTP
        assert mock_sftp.put.call_count == 2
        
        # Verify execution
        assert mock_ssh.exec_command.call_count == 2
        calls = mock_ssh.exec_command.call_args_list
        assert calls[0][0][0] == deploy_to_windows.KILL_CMD
        assert calls[1][0][0] == deploy_to_windows.START_CMD

def test_wmi_start_error():
    with patch("deploy_to_windows.paramiko.SSHClient") as MockSSHClient, \
         patch("deploy_to_windows.os.path.exists", return_value=True):
        
        mock_ssh = MockSSHClient.return_value
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        
        def mock_exec_command(cmd):
            mock_stdout = MagicMock()
            mock_stderr = MagicMock()
            if cmd == deploy_to_windows.START_CMD:
                mock_stdout.channel.recv_exit_status.return_value = 1
                mock_stderr.read.return_value = b"WMI Error: Invalid class"
            else:
                mock_stdout.channel.recv_exit_status.return_value = 0
                mock_stderr.read.return_value = b""
            return (MagicMock(), mock_stdout, mock_stderr)
            
        mock_ssh.exec_command.side_effect = mock_exec_command
        
        with pytest.raises(Exception, match="Failed to start server"):
            deploy_to_windows.deploy_and_restart()
