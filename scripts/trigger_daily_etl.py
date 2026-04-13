#!/usr/bin/env python3
"""
trigger_daily_etl.py - Linux-side SSH orchestration script for daily ETL trigger

Connects via SSH to the Windows QMT node, runs daily_sync.py remotely to fetch
latest sector + financial data, then runs finance_batch_etl.py remotely to rebuild
fundamentals.json.
"""

import json
import sys
import paramiko
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# SSH Connection Details (from TOOLS.md)
WINDOWS_HOST = '43.134.76.215'
WINDOWS_PORT = 22
WINDOWS_USER = 'Administrator'
WINDOWS_PASS = '8!9TYD.*Hm;ycV'

# Remote commands
DAILY_SYNC_CMD = r'python C:\Users\Administrator\Desktop\AMS\daily_sync.py'
FINANCE_ETL_CMD = r'python C:\Users\Administrator\Desktop\AMS\finance_batch_etl.py'


def run_remote_command(ssh_client, command):
    """
    Execute a command remotely via SSH and return (exit_status, stdout, stderr).
    """
    logger.info(f"Executing remote command: {command}")
    stdin, stdout, stderr = ssh_client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    stdout_text = stdout.read().decode('gbk', errors='ignore').strip()
    stderr_text = stderr.read().decode('gbk', errors='ignore').strip()
    
    logger.info(f"Exit status: {exit_status}")
    if stdout_text:
        logger.info(f"Stdout: {stdout_text[:500]}")
    if stderr_text:
        logger.warning(f"Stderr: {stderr_text[:500]}")
    
    return exit_status, stdout_text, stderr_text


def trigger_daily_etl():
    """
    Main function to:
    1. Connect via SSH to Windows QMT node
    2. Run daily_sync.py remotely
    3. Run finance_batch_etl.py remotely
    4. Output JSON status
    """
    result = {
        "status": "failed",
        "daily_sync_output": "",
        "etl_output": "",
        "errors": []
    }
    
    ssh = None
    
    try:
        # Step 1: Connect via SSH
        logger.info(f"Connecting to {WINDOWS_HOST}:{WINDOWS_PORT}...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            WINDOWS_HOST,
            port=WINDOWS_PORT,
            username=WINDOWS_USER,
            password=WINDOWS_PASS,
            timeout=10
        )
        logger.info("SSH connection established.")
        
        # Step 2: Run daily_sync.py remotely
        sync_status, sync_stdout, sync_stderr = run_remote_command(ssh, DAILY_SYNC_CMD)
        result["daily_sync_output"] = sync_stdout
        
        if sync_status != 0:
            error_msg = f"daily_sync.py failed with exit status {sync_status}: {sync_stderr}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            result["status"] = "partial"
            # Continue to try ETL anyway
        
        # Step 3: Run finance_batch_etl.py remotely
        etl_status, etl_stdout, etl_stderr = run_remote_command(ssh, FINANCE_ETL_CMD)
        result["etl_output"] = etl_stdout
        
        if etl_status != 0:
            error_msg = f"finance_batch_etl.py failed with exit status {etl_status}: {etl_stderr}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            if result["status"] != "partial":
                result["status"] = "partial"
        
        # Determine final status
        if result["status"] != "partial" and not result["errors"]:
            result["status"] = "success"
            logger.info("Both daily_sync and ETL completed successfully.")
        elif not result["errors"]:
            result["status"] = "success"
            
    except paramiko.SSHException as e:
        error_msg = f"SSH connection error: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["status"] = "failed"
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["status"] = "failed"
    finally:
        if ssh:
            try:
                ssh.close()
                logger.info("SSH connection closed.")
            except Exception:
                pass
    
    return result


def main():
    result = trigger_daily_etl()
    
    # Output JSON to stdout
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Exit code: 0 on success, 1 on failure
    if result["status"] == "failed":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
