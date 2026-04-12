import argparse
import json
import os
import sys

CACHE_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'fundamentals_cache.json')

def load_cache():
    if not os.path.exists(CACHE_FILE):
        return None
    with open(CACHE_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return None

def run_screener(strategy, max_pe=None):
    data = load_cache()
    if data is None:
        return {"error": "Local cache missing or corrupted"}
    
    results = []
    for stock in data:
        if max_pe is not None and stock.get('pe', float('inf')) > max_pe:
            continue
        # Additional strategy logic can go here. For now, we return anything that passes pe.
        results.append(stock)
    
    return {"strategy": strategy, "results": results}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--pe", type=float, required=False)
    
    args = parser.parse_args()
    
    result = run_screener(args.strategy, args.pe)
    print(json.dumps(result, indent=2))
