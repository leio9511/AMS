import pytest
from unittest.mock import MagicMock, patch
import deploy_to_windows

def test_wmi_command_tolerant_decoding():
    with patch("deploy_to_windows.paramiko.SSHClient") as MockSSHClient, \
         patch("deploy_to_windows.os.path.exists", return_value=True):
        
        mock_ssh = MockSSHClient.return_value
        mock_ssh.open_sftp.return_value = MagicMock()
        
        def mock_exec_command(cmd):
            mock_stdout = MagicMock()
            mock_stderr = MagicMock()
            if cmd == deploy_to_windows.START_CMD:
                mock_stdout.channel.recv_exit_status.return_value = 1
                # Provide some invalid GBK bytes to ensure errors='ignore' works
                mock_stderr.read.return_value = b"WMI Error: Invalid class \xff\xfe"
            else:
                mock_stdout.channel.recv_exit_status.return_value = 0
                mock_stderr.read.return_value = b""
            return (MagicMock(), mock_stdout, mock_stderr)
            
        mock_ssh.exec_command.side_effect = mock_exec_command
        
        try:
            deploy_to_windows.deploy_and_restart()
        except Exception as e:
            # We expect it to raise due to exit_status == 1, but we shouldn't see UnicodeDecodeError
            assert "UnicodeDecodeError" not in str(e)
            assert "WMI Error: Invalid class" in str(e)
