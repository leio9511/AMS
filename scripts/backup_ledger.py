import sqlite3
import os
import sys
import json
import shutil
import datetime

DEFAULT_DB_PATH = os.path.expanduser('~/.openclaw/data/ams/ledger.db')
DEFAULT_BACKUP_DIR = os.path.expanduser('~/.openclaw/data/ams/backups')

def run_backup(db_path=DEFAULT_DB_PATH, backup_dir=DEFAULT_BACKUP_DIR):
    if not os.path.exists(db_path):
        return {
            "status": "error",
            "error": f"Database file not found: {db_path}"
        }

    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"ledger_{timestamp}.db")
    
    # Simulate SCP transfer via a stub
    # In a real environment, this might be `scp {backup_file} user@remote:/path/`
    scp_transfer_success = True
    
    try:
        shutil.copy2(db_path, backup_file)
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to copy database: {str(e)}"
        }

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Verify the table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='portfolio'")
        if not cursor.fetchone():
            total_asset_value = 0.0
        else:
            cursor.execute("SELECT amount, current_price FROM portfolio")
            rows = cursor.fetchall()
            total_asset_value = sum((row[0] * row[1] for row in rows if row[0] is not None and row[1] is not None))
        conn.close()
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to read portfolio snapshot: {str(e)}"
        }

    return {
        "status": "success",
        "timestamp": timestamp,
        "backup_file": backup_file,
        "scp_transfer": "stubbed_success" if scp_transfer_success else "failed",
        "snapshot": {
            "total_asset_value": total_asset_value
        }
    }

if __name__ == "__main__":
    result = run_backup()
    print(json.dumps(result))