import requests
import re
import time
import math
from datetime import datetime

# --- CONFIGURATION ---
# Stock Codes
HK_STOCK_CODE = "hk00700"  # Tencent (HK)
ETF_STOCK_CODE = "sh513050" # China Internet ETF (Track Tencent & Alibaba)
# Alternatively: sh513180 (Hang Seng Tech ETF) if you prefer broad tech exposure

# Thresholds
SPREAD_THRESHOLD = 0.5 # 0.5% premium/discount trigger
POLL_INTERVAL = 3  # Check every 3 seconds

# Exchange Rate (Fixed for test, ideally fetch real-time)
# 1 HKD = X CNY
# Approx: 0.92 (Need real-time fetch in production)
FIXED_EXCHANGE_RATE = 0.92 

def get_realtime_data(codes):
    """
    Fetch real-time price from Tencent Interface.
    codes: list of strings (e.g. ['sh513050', 'r_hk00700'])
    """
    url = f"http://qt.gtimg.cn/q={','.join(codes)}"
    try:
        resp = requests.get(url, timeout=2)
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception as e:
        print(f"Error: {e}")
        return None

def parse_data(raw_data, monitored_codes):
    """
    Parse the raw string from Tencent API.
    Returns dict: { 'sh513050': {'name':..., 'price':...}, 'hk00700': {'name':..., 'price':...} }
    """
    results = {}
    lines = raw_data.strip().split(';')
    for line in lines:
        if not line.strip(): continue
        
        # v_s_sh513050="1~Name~Code~Price~..."
        # v_r_hk00700="100~Name~Code~Price~..."
        
        # Extract the variable name first to identify the stock
        var_match = re.search(r'v_(?:r_)?([a-zA-Z0-9]+)="(.*)"', line)
        if not var_match: continue
        
        code_key = var_match.group(1)
        data_str = var_match.group(2)
        fields = data_str.split('~')
        
        if len(fields) < 4: continue
        
        # Tencent fields mapping
        # A-share (s_sh/sz): 1=Name, 3=Price
        # HK-share (r_hk): 1=Name, 3=Price
        
        name = fields[1]
        try:
            price = float(fields[3])
        except ValueError:
            price = 0.0 # Handle case where price is '--' or invalid
            
        # Store using the code we requested/monitor
        # e.g. we want 'hk00700', API gives 'hk00700'
        
        results[code_key] = {
            'name': name,
            'price': price,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        }
            
    return results

def main():
    print(f"Starting Monitor: {ETF_STOCK_CODE} (A-Share ETF) vs {HK_STOCK_CODE} (HK Stock)")
    # Note: Exchange Rate is fixed for now.
    # In production, we should fetch CNH=X or HKDCNY=X
    print(f"Assumed Exchange Rate (HKD->CNY): {FIXED_EXCHANGE_RATE}")
    print("-" * 60)
    
    # We request: sh513050, r_hk00700
    # API returns var names: v_sh513050, v_r_hk00700
    # So our keys will be 'sh513050' and 'hk00700' (after regex extraction)
    
    request_url_codes = [ETF_STOCK_CODE, f"r_{HK_STOCK_CODE}"]
    
    while True:
        try:
            raw_data = get_realtime_data(request_url_codes)
            if not raw_data:
                time.sleep(POLL_INTERVAL)
                continue
                
            data = parse_data(raw_data, [ETF_STOCK_CODE, HK_STOCK_CODE])
            
            # Check if we have both
            if ETF_STOCK_CODE in data and HK_STOCK_CODE in data:
                etf = data[ETF_STOCK_CODE]
                hk = data[HK_STOCK_CODE]
                
                # Calculate Ratio
                # Ratio = ETF_Price / (HK_Price * Exchange_Rate)
                # This ratio represents "How many units of ETF = 1 unit of HK Stock" (normalized by currency)
                # If this ratio rises -> ETF is getting expensive relative to HK stock
                
                hk_price_cny = hk['price'] * FIXED_EXCHANGE_RATE
                if hk_price_cny > 0:
                    ratio = etf['price'] / hk_price_cny
                else:
                    ratio = 0
                
                # Display
                print(f"[{etf['timestamp']}] "
                      f"{etf['name']}: {etf['price']:.3f} | "
                      f"{hk['name']}: {hk['price']:.3f} (HKD) -> {hk_price_cny:.3f} (CNY) | "
                      f"Ratio: {ratio:.5f}")
            else:
                # Debug: print what keys we got if missing
                # print(f"Missing data. Got keys: {list(data.keys())}")
                pass
                
        except KeyboardInterrupt:
            print("\nMonitor stopped.")
            break
        except Exception as e:
            print(f"Error in loop: {e}")
            
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
