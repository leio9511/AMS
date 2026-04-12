#!/usr/bin/env python3
"""
AMS (Arbitrage Monitoring System) V6.0 - AgentSkill Version
"""

import sys
import json
import os
import requests
import argparse
from datetime import datetime, timedelta

BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_PATH, 'cache', 'daily_alerts.json')

ETF_CODES = [
    "sh513330", "sh513050", "sh513100", "sz159941", 
    "sz159632", "sh513500", "sh513880", "sh513030",
    "sz159501", "sh513110", "sh513730"
]
THRESHOLD_ETF = 0.005  # 0.5%
THRESHOLD_CB = -0.008  # 折价 > 0.8%

def to_float(val):
    try: return float(val)
    except: return 0.0

def fetch_etf_data():
    url = "http://qt.gtimg.cn/q=" + ",".join(ETF_CODES)
    try:
        r = requests.get(url, timeout=10)
        r.encoding = 'gbk'
        lines = r.text.strip().split(';')
        results = []
        for line in lines:
            if not line.strip(): continue
            try:
                data = line.split('=')[1].strip('"')
                fields = data.split('~')
                if len(fields) < 80: continue
                name, code = fields[1], fields[2]
                bid1, ask1, iopv = to_float(fields[9]), to_float(fields[19]), to_float(fields[78])
                if iopv <= 0: continue
                premium = (ask1 / iopv - 1) if ask1 > 0 else 0
                discount = (1 - bid1 / iopv) if bid1 > 0 else 0
                diff_val = premium if premium > 0 else -discount
                results.append({"code": code, "name": name, "bid1": bid1, "ask1": ask1, "iopv": iopv, "diff": diff_val})
            except: continue
        return results
    except Exception:
        return []

def fetch_cb_data():
    url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=0&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f243&fs=b:MK0354,b:MK0355&fields=f12,f14,f2,f3,f243,f244'
    try:
        r = requests.get(url, timeout=10)
        items = r.json().get('data', {}).get('diff', [])
        results = []
        for i in items:
            code, name, price, prem_raw = i['f12'], i['f14'], to_float(i['f2']), i.get('f243')
            if isinstance(prem_raw, (int, float)):
                results.append({"code": code, "name": name, "price": price, "premium": prem_raw / 100.0})
        return results
    except Exception:
        return []

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def morning_report(dry_run=False):
    if dry_run:
        print("Dry run: Morning report executed.")
        return
    print(json.dumps([{"msg": "Morning report executed"}], ensure_ascii=False))

def closing_report(dry_run=False):
    if dry_run:
        print("Dry run: Closing report executed.")
        return
    print(json.dumps([{"msg": "Closing report executed"}], ensure_ascii=False))

def monitor_scan(dry_run=False):
    if dry_run:
        print("Dry run: Monitor scan executed.")
        return
        
    today = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")
    cache = load_cache()
    if cache.get('date') != today:
        cache = {'date': today, 'alerts': []}

    etfs = fetch_etf_data()
    cbs = fetch_cb_data()

    new_anomalies = []

    for e in etfs:
        if abs(e['diff']) >= THRESHOLD_ETF:
            if e['code'] not in cache['alerts']:
                new_anomalies.append({
                    "type": "ETF",
                    "code": e['code'],
                    "name": e['name'],
                    "diff": e['diff'],
                    "status": "Premium" if e['diff'] > 0 else "Discount"
                })
                cache['alerts'].append(e['code'])

    for c in cbs:
        if c['premium'] <= THRESHOLD_CB:
            if c['code'] not in cache['alerts']:
                new_anomalies.append({
                    "type": "Convertible Bond",
                    "code": c['code'],
                    "name": c['name'],
                    "premium": c['premium'],
                    "status": "Discount"
                })
                cache['alerts'].append(c['code'])

    if not new_anomalies:
        sys.exit(0)

    save_cache(cache)
    print(json.dumps(new_anomalies, ensure_ascii=False, indent=2))

def main():
    parser = argparse.ArgumentParser(description="AMS ETF Tracker")
    parser.add_argument('--mode', type=str, required=True, choices=['morning', 'monitor', 'closing'], help='Execution mode')
    parser.add_argument('--dry-run', action='store_true', help='Run in dry-run mode for testing')
    
    args = parser.parse_args()
    
    if args.mode == 'morning':
        morning_report(args.dry_run)
    elif args.mode == 'monitor':
        monitor_scan(args.dry_run)
    elif args.mode == 'closing':
        closing_report(args.dry_run)
    else:
        print(f"Unknown mode: {args.mode}")
        sys.exit(1)

if __name__ == '__main__':
    main()
