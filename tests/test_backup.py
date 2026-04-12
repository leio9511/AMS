import os
import json
import sqlite3
import pytest
from unittest import mock
import tempfile
import sys
import subprocess

# Add scripts to path to import backup_ledger
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import backup_ledger

@pytest.fixture
def temp_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, 'ledger.db')
        backup_dir = os.path.join(temp_dir, 'backups')
        
        # Setup mock db
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE portfolio (
                asset TEXT PRIMARY KEY,
                asset_type TEXT,
                amount REAL,
                cost_basis REAL,
                current_price REAL,
                unrealized_pnl REAL,
                profit_pct REAL
            )
        ''')
        cursor.execute("INSERT INTO portfolio VALUES ('159501.SZ', 'ETF', 5000, 1.2, 1.6, 2000, 33.33)")
        cursor.execute("INSERT INTO portfolio VALUES ('000001.SZ', 'Stock', 1000, 10.0, 11.0, 1000, 10.0)")
        conn.commit()
        conn.close()
        
        yield db_path, backup_dir

def test_backup_creates_copy(temp_env):
    db_path, backup_dir = temp_env
    res = backup_ledger.run_backup(db_path, backup_dir)
    assert res['status'] == 'success'
    assert 'timestamp' in res
    assert os.path.exists(res['backup_file'])
    assert res['backup_file'].startswith(backup_dir)

def test_backup_json_summary(temp_env):
    db_path, backup_dir = temp_env
    
    # We want to test the script as it would be executed by the LLM
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts/backup_ledger.py'))
    
    # Run the script using subprocess, monkeypatching the default paths doesn't work easily with subprocess
    # So we'll patch the run_backup locally for the stdout test, or just test stdout capture locally
    import io
    with mock.patch('sys.stdout', new=io.StringIO()) as fake_stdout:
        with mock.patch('backup_ledger.DEFAULT_DB_PATH', db_path), \
             mock.patch('backup_ledger.DEFAULT_BACKUP_DIR', backup_dir):
            # simulate __main__
            res = backup_ledger.run_backup(db_path, backup_dir)
            print(json.dumps(res))
            
    output = fake_stdout.getvalue()
    parsed = json.loads(output)
    
    assert parsed['status'] == 'success'
    assert 'snapshot' in parsed
    assert parsed['snapshot']['total_asset_value'] == 19000.0

def test_backup_missing_db(temp_env):
    db_path, backup_dir = temp_env
    os.remove(db_path)
    res = backup_ledger.run_backup(db_path, backup_dir)
    assert res['status'] == 'error'
    assert "not found" in res['error'].lower()
