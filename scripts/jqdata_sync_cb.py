import os
import pandas as pd
import jqdatasdk

def sync_cb_data(start_date="2020-01-01", end_date="2024-01-01"):
    user = os.environ.get("JQDATA_USER")
    pwd = os.environ.get("JQDATA_PWD")
    
    if not user or not pwd:
        raise ValueError("Missing JQDATA_USER or JQDATA_PWD environment variables")
        
    try:
        jqdatasdk.auth(user, pwd)
    except Exception as e:
        raise RuntimeError(f"JQData auth failed: {e}")
        
    # Example logic to fetch and save, mocked out in tests
    # ...
    
    # Write to data/cb_history_factors.csv
    os.makedirs("data", exist_ok=True)
    df = pd.DataFrame(columns=["ticker", "date", "close", "volume", "premium_rate", "is_st", "is_redeemed"])
    df.to_csv("data/cb_history_factors.csv", index=False)

if __name__ == "__main__":
    sync_cb_data()
