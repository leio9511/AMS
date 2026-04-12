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
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(WINDOWS_HOST, port=WINDOWS_PORT, username=WINDOWS_USER, password=WINDOWS_PASS, timeout=10)
        
        # Upload
        sftp = ssh.open_sftp()
        try:
            # Ensure target directory exists (not strictly required if we assume it exists, but good practice)
            # Just upload
            local_etl = "windows_bridge/finance_batch_etl.py"
            local_server = "windows_bridge/server.py"
            
            if os.path.exists(local_etl):
                sftp.put(local_etl, f"{WINDOWS_TARGET_DIR}/finance_batch_etl.py")
                logger.info("Uploaded finance_batch_etl.py")
            if os.path.exists(local_server):
                sftp.put(local_server, f"{WINDOWS_TARGET_DIR}/server.py")
                logger.info("Uploaded server.py")
        finally:
            sftp.close()
            
        # Execute WMI Commands
        logger.info(f"Executing: {KILL_CMD}")
        stdin, stdout, stderr = ssh.exec_command(KILL_CMD)
        exit_status = stdout.channel.recv_exit_status()
        err = stderr.read().decode().strip()
        if exit_status != 0 and err:
            logger.warning(f"Kill command returned exit status {exit_status}: {err}")
        
        logger.info(f"Executing: {START_CMD}")
        stdin, stdout, stderr = ssh.exec_command(START_CMD)
        exit_status = stdout.channel.recv_exit_status()
        err = stderr.read().decode().strip()
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
