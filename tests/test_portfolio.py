import sqlite3
import pytest
from scripts.query_portfolio import init_db, add_asset, get_asset

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