import time
import subprocess
import requests
from datetime import datetime, timedelta
import json

TARGET = "telegram:6228532305"
ETF_CODES = [
    "sh513330", "sh513050", "sh513100", "sz159941", 
    "sh513120", "sh513060", "sh513130", "sh513500"
]

morning_summary_sent = False
afternoon_summary_sent = False
forced_opening_report_sent = False

def is_trading_day():
    now = datetime.utcnow() + timedelta(hours=8)
    # 0 is Monday, 6 is Sunday
    if now.weekday() >= 5:
        return False
    # Simplified holiday check (should be expanded)
    return True

def fetch_etf_data():
    results = []
    codes = ",".join(ETF_CODES)
    url = f"http://hq.sinajs.cn/list={codes}"
    try:
        response = requests.get(url, timeout=10)
        lines = response.text.split("\n")
        for line in lines:
            if "=\"" in line:
                parts = line.split("\"")
                data = parts[1].split(",")
                name = data[0]
                price = float(data[3])
                # Note: Real IOPV needs separate source, simulating for now
                results.append({"name": name, "price": price})
    except Exception as e:
        print(f"Error: {e}")
    return results

def run_tracker():
    global morning_summary_sent, afternoon_summary_sent, forced_opening_report_sent
    print("QBot Unified Tracker V3.1 Started (with Weekend Guard).")
    while True:
        if not is_trading_day():
            print("Today is weekend/holiday. Monitoring suspended.")
            time.sleep(3600) # Sleep for an hour
            continue
            
        now = datetime.utcnow() + timedelta(hours=8)
        current_time = now.strftime("%H:%M")
        
        # Reset flags at midnight
        if current_time == "00:00":
            morning_summary_sent = False
            afternoon_summary_sent = False
            forced_opening_report_sent = False

        # ... (rest of the logic)
        time.sleep(60)

# Implementation truncated for brevity in message
