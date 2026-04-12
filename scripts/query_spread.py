import argparse
import json
import requests
import sys

def get_spread(ticker: str) -> dict:
    url = f"http://43.134.76.215:8000/quote?ticker={ticker}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        current_price = float(data.get("current_price", 0))
        iopv = float(data.get("iopv", 0))
        
        if iopv > 0:
            premium_pct = round(((current_price / iopv) - 1) * 100, 2)
        else:
            premium_pct = 0.0
            
        return {
            "ticker": ticker,
            "current_price": current_price,
            "iopv": iopv,
            "premium_pct": premium_pct
        }
    except requests.exceptions.RequestException as e:
        return {
            "error": f"QMT bridge failure: {str(e)}"
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Market Spread Radar")
    parser.add_argument("--ticker", required=True, help="Ticker symbol to query")
    args = parser.parse_args()
    
    result = get_spread(args.ticker)
    print(json.dumps(result, indent=2))
