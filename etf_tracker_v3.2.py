import time
import subprocess
import requests
from datetime import datetime, timedelta
import json
import os
import sys

TARGET = "telegram:6228532305"
LOG_PATH = "/root/.openclaw/workspace/etf_tracker.log"
DATA_PATH = "/root/.openclaw/workspace/etf_tracker_data.json"
ETF_CODES = ["sh513330", "sh513050", "sh513100", "sz159941", "sz159632", "sh513500", "sh513880", "sh513030", "sz159501", "sh513110", "sh513730"]
STALE_NAV_CODES = ['sh513050', 'sh513730', 'sh513100', 'sh513500', 'sz159941', 'sz159632', 'sz159501', 'sh513110']
THRESHOLD_ETF = 0.005
THRESHOLD_CB = -0.008

alerted_codes = set()
morning_summary_sent = False
forced_opening_report_sent = False

def log(msg):
    ts = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def send_msg(text):
    log(f"Sending message: {text[:50]}...")
    try:
        subprocess.run(["openclaw", "message", "send", "--channel", "telegram", "--target", TARGET, "--message", text], check=True)
    except Exception as e:
        log(f"Failed to send message: {e}")

def write_status_data(etfs, cbs=None):
    try:
        data = {"timestamp": (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"), "etfs": etfs, "convertible_bonds": cbs or []}
        with open(DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        log(f"Failed to write JSON data: {e}")

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
                bid1, ask1, iopv = float(fields[9]), float(fields[19]), float(fields[78])
                if iopv <= 0: continue
                premium = (ask1 / iopv - 1) if ask1 > 0 else 0
                discount = (1 - bid1 / iopv) if bid1 > 0 else 0
                diff_val = premium if premium > 0 else -discount
                results.append({"code": code, "name": name, "bid1": bid1, "ask1": ask1, "iopv": iopv, "diff": diff_val, "is_stale": code in STALE_NAV_CODES})
            except: continue
        results.sort(key=lambda x: x['diff'], reverse=True)
        return results
    except Exception as e:
        log(f"Fetch ETF error: {e}")
        return []

def fetch_cb_data():
    url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=0&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f243&fs=b:MK0354,b:MK0355&fields=f12,f14,f2,f3,f243,f244'
    try:
        r = requests.get(url, timeout=10)
        items = r.json().get('data', {}).get('diff', [])
        results = []
        for i in items:
            code, name, price, prem_raw = i['f12'], i['f14'], float(i['f2']), i.get('f243')
            if isinstance(prem_raw, (int, float)):
                results.append({"code": code, "name": name, "price": price, "premium": prem_raw / 100.0})
        return results
    except Exception as e:
        log(f"Fetch CB error: {e}")
        return []

def is_trading_day():
    now = datetime.utcnow() + timedelta(hours=8)
    if now.weekday() >= 5: return False
    return True

def run_tracker():
    global morning_summary_sent, forced_opening_report_sent
    log("V3.2 Tracker Started.")
    while True:
        try:
            if not is_trading_day():
                time.sleep(3600); continue
            
            now = datetime.utcnow() + timedelta(hours=8)
            current_time = now.strftime("%H:%M")
            
            # Reset at midnight
            if current_time == "00:00":
                forced_opening_report_sent = False; alerted_codes.clear()

            # Opening Report
            if "09:26" <= current_time <= "11:30" and not forced_opening_report_sent:
                etfs = fetch_etf_data()
                cbs = fetch_cb_data()
                write_status_data(etfs, cbs)
                if etfs:
                    msg = f"🔔 【补发：开盘简报】({current_time})\n\n📍 跨境 ETF：\n"
                    for e in etfs[:5]: msg += f"• {e['name']}: {'+' if e['diff']>0 else ''}{e['diff']*100:.2f}%\n"
                    send_msg(msg)
                    forced_opening_report_sent = True

            # Monitoring
            if ("09:30" <= current_time <= "11:30") or ("13:00" <= current_time <= "15:00"):
                etfs = fetch_etf_data()
                write_status_data(etfs)
                for e in etfs:
                    if abs(e['diff']) >= THRESHOLD_ETF and e['code'] not in alerted_codes:
                        alerted_codes.add(e['code'])
                        icon = "🔴" if e['diff'] > 0 else "🟢"
                        send_msg(f"{icon} 【ETF 异动】\n名称: {e['name']}\n幅度: {e['diff']*100:.2f}%")

            time.sleep(30)
        except Exception as e:
            log(f"Loop error: {e}")
            time.sleep(10)

if __name__ == '__main__':
    run_tracker()
