import os
import paramiko
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

WINDOWS_HOST = '43.134.76.215'
WINDOWS_PORT = 22
WINDOWS_USER = 'Administrator'
WINDOWS_PASS = '8!9TYD.*Hm;ycV'
WINDOWS_TARGET_DIR = 'C:/Users/Administrator/Desktop/AMS'

KILL_CMD = 'wmic process where "commandline like \'%server.py%\' and name=\'python.exe\'" call terminate'
START_CMD = 'wmic process call create "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe C:\\Users\\Administrator\\Desktop\\AMS\\server.py"'

def deploy_and_restart():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(WINDOWS_HOST, port=WINDOWS_PORT, username=WINDOWS_USER, password=WINDOWS_PASS, timeout=10)
        
        # Upload
        sftp = ssh.open_sftp()
        try:
            files_to_upload = [
                ("windows_bridge/finance_batch_etl.py", "finance_batch_etl.py"),
                ("windows_bridge/server.py", "server.py"),
                ("windows_bridge/daily_sync.py", "daily_sync.py"),
                ("windows_bridge/bootstrap_data.py", "bootstrap_data.py")
            ]
            for local_rel, remote_name in files_to_upload:
                local_path = os.path.join(base_dir, local_rel)
                if os.path.exists(local_path):
                    sftp.put(local_path, f"{WINDOWS_TARGET_DIR}/{remote_name}")
                    logger.info(f"Uploaded {remote_name}")
                else:
                    logger.warning(f"Local file not found: {local_path}")
        finally:
            sftp.close()
            
        # Execute WMI Commands
        logger.info(f"Executing: {KILL_CMD}")
        stdin, stdout, stderr = ssh.exec_command(KILL_CMD)
        exit_status = stdout.channel.recv_exit_status()
        err = stderr.read().decode('gbk', errors='ignore').strip()
        if exit_status != 0 and err:
            logger.warning(f"Kill command returned exit status {exit_status}: {err}")
        
        logger.info(f"Executing: {START_CMD}")
        stdin, stdout, stderr = ssh.exec_command(START_CMD)
        exit_status = stdout.channel.recv_exit_status()
        err = stderr.read().decode('gbk', errors='ignore').strip()
        if exit_status != 0:
            logger.error(f"Start command failed with exit status {exit_status}: {err}")
            raise Exception(f"Failed to start server: {err}")
        else:
            logger.info("Server started successfully.")
            
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}")
        raise
    finally:
        try:
            ssh.close()
        except Exception:
            pass

if __name__ == '__main__':
    deploy_and_restart()
