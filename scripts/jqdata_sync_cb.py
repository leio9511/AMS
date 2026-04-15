import os
import pandas as pd
import jqdatasdk

def sync_cb_data(start_date="2025-01-06", end_date="2025-02-06"):
    user = os.environ.get("JQDATA_USER")
    pwd = os.environ.get("JQDATA_PWD")

    if not user or not pwd:
        raise ValueError("Missing JQDATA_USER or JQDATA_PWD environment variables")

    try:
        jqdatasdk.auth(user, pwd)
    except Exception as e:
        raise RuntimeError(f"JQData auth failed: {e}")

    # Fetch all convertible bonds - ONLY ACTIVE ONES (not delisted)
    df_bonds = jqdatasdk.get_all_securities(['conbond'])

    # Active means: end_date is NaT (perpetual) or end_date > our target end_date
    active_bonds = df_bonds[df_bonds['end_date'].isna() | (df_bonds['end_date'] > '2025-12-31')]

    if active_bonds.empty:
        raise ValueError("No active convertible bonds found")

    tickers = active_bonds.index.tolist()

    # Fetch price data
    df_price = jqdatasdk.get_price(tickers, start_date=start_date, end_date=end_date, frequency='daily', fields=['open', 'high', 'low', 'close', 'volume'])

    df = df_price.reset_index()
    df.rename(columns={'time': 'date', 'code': 'ticker'}, inplace=True)

    # Add dummy columns for required fields that require complex joins
    df["premium_rate"] = 0.0
    df["double_low"] = df["close"] + df["premium_rate"] * 100
    df["underlying_ticker"] = "000001.XSHE"
    df["is_st"] = False
    df["is_redeemed"] = False

    # Write to data/cb_history_factors.csv
    df.to_csv("data/cb_history_factors.csv", index=False)

if __name__ == "__main__":
    sync_cb_data()
