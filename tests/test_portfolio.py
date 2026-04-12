import sqlite3
import pytest
import subprocess
import json
import os
from scripts.query_portfolio import init_db, add_asset, get_asset, update_asset, remove_asset

def test_init_db(tmp_path):
    db_path = tmp_path / "ledger.db"
    init_db(str(db_path))
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='portfolio'")
    assert cursor.fetchone() is not None
    conn.close()

def test_add_and_get_asset(tmp_path):
    db_path = tmp_path / "ledger.db"
    add_asset("159501.SZ", "ETF", 500000, 1.200, 1.600, str(db_path))
    
    asset = get_asset("159501.SZ", str(db_path))
    assert asset is not None
    assert asset['asset'] == "159501.SZ"
    assert asset['asset_type'] == "ETF"
    assert asset['amount'] == 500000
    assert asset['cost_basis'] == 1.200
    assert asset['current_price'] == 1.600
    assert asset['unrealized_pnl'] == pytest.approx(200000)
    assert asset['profit_pct'] == pytest.approx(33.33333333333333)

def test_update_asset(tmp_path):
    db_path = tmp_path / "ledger.db"
    add_asset("159501.SZ", "ETF", 500000, 1.200, 1.600, str(db_path))
    
    asset = update_asset("159501.SZ", 1.800, str(db_path))
    assert asset is not None
    assert asset['current_price'] == 1.800
    assert asset['unrealized_pnl'] == pytest.approx((1.800 - 1.200) * 500000)
    assert asset['profit_pct'] == pytest.approx(((1.800 - 1.200) / 1.200) * 100)

def test_remove_asset(tmp_path):
    db_path = tmp_path / "ledger.db"
    add_asset("159501.SZ", "ETF", 500000, 1.200, 1.600, str(db_path))
    
    res = remove_asset("159501.SZ", str(db_path))
    assert res == {"status": "success"}
    
    asset = get_asset("159501.SZ", str(db_path))
    assert asset is None

def test_json_output_format(tmp_path):
    os.environ["HOME"] = str(tmp_path)
    # The default DB path is ~/.openclaw/data/ams/ledger.db
    # It will use the mocked HOME dir.
    
    script_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'query_portfolio.py')
    
    # Add
    result = subprocess.run(
        ["python3", script_path, "--action", "add", "--asset", "159501.SZ", "--type", "ETF", "--amount", "500000", "--cost", "1.2", "--price", "1.6"],
        capture_output=True, text=True
    )
    output = json.loads(result.stdout.strip())
    assert output["asset"] == "159501.SZ"
    assert output["unrealized_pnl"] == pytest.approx(200000)
    
    # Get
    result = subprocess.run(
        ["python3", script_path, "--action", "get", "--asset", "159501.SZ"],
        capture_output=True, text=True
    )
    output = json.loads(result.stdout.strip())
    assert output["asset"] == "159501.SZ"
    assert output["asset_type"] == "ETF"
    assert output["amount"] == 500000
    assert output["cost_basis"] == 1.200
    assert output["current_price"] == 1.600
    assert output["unrealized_pnl"] == pytest.approx(200000)
    assert output["profit_pct"] == pytest.approx(33.33, rel=1e-2)
    
    # Update
    result = subprocess.run(
        ["python3", script_path, "--action", "update", "--asset", "159501.SZ", "--value", "1.8"],
        capture_output=True, text=True
    )
    output = json.loads(result.stdout.strip())
    assert output["current_price"] == 1.8
    assert output["unrealized_pnl"] == pytest.approx(300000)
    
    # Remove
    result = subprocess.run(
        ["python3", script_path, "--action", "remove", "--asset", "159501.SZ"],
        capture_output=True, text=True
    )
    output = json.loads(result.stdout.strip())
    assert output["status"] == "success"
