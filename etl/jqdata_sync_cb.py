import os
import pandas as pd
import jqdatasdk

def sync_cb_data(start_date="2025-01-06", end_date="2025-02-06"):
    output_path = "data/cb_history_factors.csv"
    bak_path = "data/cb_history_factors.csv.bak"
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if os.path.exists(output_path):
        import shutil
        shutil.copy2(output_path, bak_path)

    user = os.environ.get("JQDATA_USER")
    pwd = os.environ.get("JQDATA_PWD")

    if not user or not pwd:
        raise ValueError("Missing JQDATA_USER or JQDATA_PWD environment variables")

    try:
        jqdatasdk.auth(user, pwd)
    except Exception as e:
        raise RuntimeError(f"JQData auth failed: {e}")

    # Fetch all convertible bonds
    df_bonds_info = jqdatasdk.bond.run_query(jqdatasdk.query(jqdatasdk.bond.CONBOND_BASIC_INFO))
    
    # Get mapping of bond ticker to underlying ticker (company_code in JQData)
    # Note: JQData company_code might need to be converted to stock ticker
    # But wait, CONBOND_BASIC_INFO has company_code. 
    # Let's check what it looks like.
    
    # Actually, JQData has a better way to get underlying stock for a bond.
    # We'll use the finance table if possible, but since it's missing, 
    # we'll use a heuristic or find another way.
    
    # Let's try to get all securities to see if they have the info.
    df_all_bonds = jqdatasdk.get_all_securities(['conbond'])
    tickers = df_all_bonds.index.tolist()

    # Fetch price data
    df_price = jqdatasdk.get_price(tickers, start_date=start_date, end_date=end_date, frequency='daily', fields=['open', 'high', 'low', 'close', 'volume'])
    if df_price.empty:
        raise ValueError("No price data found for the given range")

    df = df_price.reset_index()
    df.rename(columns={'time': 'date', 'code': 'ticker'}, inplace=True)
    df['date'] = pd.to_datetime(df['date'])

    # 1. Underlying Ticker
    # We can get the underlying stock ticker from jqdatasdk.get_security_info(ticker).parent
    bond_to_stock = {}
    for t in tickers:
        try:
            info = jqdatasdk.get_security_info(t)
            bond_to_stock[t] = info.parent
        except:
            bond_to_stock[t] = None
    
    df['underlying_ticker'] = df['ticker'].map(bond_to_stock)

    # 2. Premium Rate
    # Fetch from bond.CONBOND_DAILY_CONVERT
    # We query in chunks if there are many tickers
    df_premium_list = []
    # Vectorized query for premium rate
    q = jqdatasdk.query(jqdatasdk.bond.CONBOND_DAILY_CONVERT).filter(
        jqdatasdk.bond.CONBOND_DAILY_CONVERT.code.in_(tickers),
        jqdatasdk.bond.CONBOND_DAILY_CONVERT.date >= start_date,
        jqdatasdk.bond.CONBOND_DAILY_CONVERT.date <= end_date
    )
    df_premium = jqdatasdk.bond.run_query(q)
    if not df_premium.empty:
        df_premium['date'] = pd.to_datetime(df_premium['date'])
        df_premium = df_premium[['date', 'code', 'convert_premium_rate']]
        df_premium.rename(columns={'code': 'ticker', 'convert_premium_rate': 'premium_rate'}, inplace=True)
        # Convert to decimal
        df_premium['premium_rate'] = df_premium['premium_rate'] / 100.0
        
        df = pd.merge(df, df_premium, on=['date', 'ticker'], how='left')
    else:
        df['premium_rate'] = 0.0

    # 3. ST Status
    # Get all unique underlying tickers
    underlying_tickers = [t for t in df['underlying_ticker'].unique() if t]
    if underlying_tickers:
        # Fetch ST status
        df_st = jqdatasdk.get_extras('is_st', underlying_tickers, start_date=start_date, end_date=end_date)
        # df_st has dates as index and tickers as columns
        st_long = df_st.stack().reset_index()
        st_long.columns = ['date', 'underlying_ticker', 'is_st']
        st_long['date'] = pd.to_datetime(st_long['date'])
        
        df = pd.merge(df, st_long, on=['date', 'underlying_ticker'], how='left')
    
    df['is_st'] = df['is_st'].fillna(False)

    # 4. Redemption Status
    try:
        # Fetch redemption announcements from CCB_CALL
        q_call = jqdatasdk.query(jqdatasdk.finance.CCB_CALL).filter(
            jqdatasdk.finance.CCB_CALL.code.in_(tickers)
        )
        df_call = jqdatasdk.finance.run_query(q_call)
        
        if not df_call.empty and 'code' in df_call.columns and 'pub_date' in df_call.columns and 'delisting_date' in df_call.columns:
            df_call = df_call[['code', 'pub_date', 'delisting_date']].copy()
            df_call.rename(columns={'code': 'ticker'}, inplace=True)
            df_call['pub_date'] = pd.to_datetime(df_call['pub_date'])
            df_call['delisting_date'] = pd.to_datetime(df_call['delisting_date'])
            
            df_call = df_call.drop_duplicates(subset=['ticker'], keep='last')
            
            df = pd.merge(df, df_call, on='ticker', how='left')
            df['is_redeemed'] = (df['date'] >= df['pub_date']) & (df['date'] < df['delisting_date'])
        else:
            df['is_redeemed'] = False
    except Exception as e:
        print(f"Warning: Failed to fetch CCB_CALL data: {e}")
        df['is_redeemed'] = False

    num_redeemed = df['is_redeemed'].sum()
    print(f"Total redeemed records marked: {num_redeemed}")
    
    # Fill remaining NaNs
    df['premium_rate'] = df['premium_rate'].fillna(0.0)
    df['double_low'] = df['close'] + df['premium_rate'] * 100

    # Final cleanup
    df = df[['ticker', 'date', 'open', 'high', 'low', 'close', 'volume', 'premium_rate', 'double_low', 'underlying_ticker', 'is_st', 'is_redeemed']]

    # Atomic write with validation
    from ams.validators.cb_data_validator import CBDataValidator
    validator = CBDataValidator()
    
    tmp_path = "data/cb_history_factors.csv.tmp"
    
    df.to_csv(tmp_path, index=False)
    
    # Read back to validate (to ensure types are correct as in real usage)
    df_to_val = pd.read_csv(tmp_path)
    # Cast types as the validator expects
    df_to_val["ticker"] = df_to_val["ticker"].astype(str)
    df_to_val["is_st"] = df_to_val["is_st"].astype(bool)
    df_to_val["is_redeemed"] = df_to_val["is_redeemed"].astype(bool)

    if validator.validate_dataframe(df_to_val):
        os.replace(tmp_path, output_path)
        print(f"Successfully synced data to {output_path}")
    else:
        print(f"[DataContractViolation] Validation failed for {tmp_path}, keeping old file.")
        # Ensure cleanup even if validation fails
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    sync_cb_data()
