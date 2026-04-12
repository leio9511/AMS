import sqlite3
import os
import json
import argparse

DEFAULT_DB_PATH = os.path.expanduser('~/.openclaw/data/ams/ledger.db')

def init_db(db_path=DEFAULT_DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio (
            asset TEXT PRIMARY KEY,
            asset_type TEXT,
            amount REAL,
            cost_basis REAL,
            current_price REAL,
            unrealized_pnl REAL,
            profit_pct REAL
        )
    ''')
    conn.commit()
    conn.close()

def add_asset(asset, asset_type, amount, cost_basis, current_price, db_path=DEFAULT_DB_PATH):
    init_db(db_path)
    unrealized_pnl = (current_price - cost_basis) * amount
    profit_pct = ((current_price - cost_basis) / cost_basis) * 100 if cost_basis > 0 else 0
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO portfolio 
        (asset, asset_type, amount, cost_basis, current_price, unrealized_pnl, profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (asset, asset_type, amount, cost_basis, current_price, unrealized_pnl, profit_pct))
    conn.commit()
    conn.close()

def get_asset(asset, db_path=DEFAULT_DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM portfolio WHERE asset = ?', (asset,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--action', choices=['get', 'add', 'update', 'remove'], required=True)
    parser.add_argument('--asset', type=str, required=True)
    parser.add_argument('--type', type=str, default="Stock")
    parser.add_argument('--amount', type=float, default=0)
    parser.add_argument('--cost', type=float, default=0)
    parser.add_argument('--price', type=float, default=0)
    
    args = parser.parse_args()
    
    if args.action == 'add':
        add_asset(args.asset, args.type, args.amount, args.cost, args.price)
        print(json.dumps({"status": "success"}))
    elif args.action == 'get':
        res = get_asset(args.asset)
        if res:
            print(json.dumps(res))
        else:
            print(json.dumps({"error": "not found"}))