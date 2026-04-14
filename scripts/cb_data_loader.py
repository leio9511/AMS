import pandas as pd
import akshare as ak
import logging
from typing import List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_cb_history(symbols: Optional[List[str]] = None, save_path: Optional[str] = None) -> pd.DataFrame:
    """
    Fetch historical data for CBs using akshare, including delisted ones.
    Reconstructs PiT daily premium rates and outstanding scale.
    """
    # 1. Get bond list and static info (issue scale)
    try:
        df_info = ak.bond_zh_cov()
        df_info = df_info[['债券代码', '发行规模']].rename(columns={
            '债券代码': 'symbol',
            '发行规模': 'outstanding_scale'
        })
    except Exception as e:
        logger.error(f"Failed to fetch bond info: {e}")
        df_info = pd.DataFrame(columns=['symbol', 'outstanding_scale'])
        
    all_data = []
    
    if symbols is None:
        symbols = df_info['symbol'].dropna().unique().tolist()
        
    for sym in symbols:
        try:
            # Use value analysis for premium_rate and close
            df_val = ak.bond_zh_cov_value_analysis(symbol=sym)
            if df_val is None or df_val.empty:
                continue
                
            df_val = df_val.rename(columns={
                '日期': 'date',
                '转股溢价率': 'premium_rate'
            })
            
            # fetch OHLC for high price
            prefix = 'sh' if sym.startswith('11') else 'sz'
            full_sym = prefix + sym
            try:
                df_daily = ak.bond_zh_hs_cov_daily(symbol=full_sym)
                if df_daily is not None and not df_daily.empty:
                    df_daily['date'] = df_daily['date'].astype(str)
                    df_val['date'] = df_val['date'].astype(str)
                    
                    df_val = pd.merge(df_val, df_daily[['date', 'close', 'high']], on='date', how='left')
                    if '收盘价' in df_val.columns:
                        df_val['close'] = df_val['close'].fillna(df_val['收盘价'])
                    df_val['high'] = df_val['high'].fillna(df_val['close'])
                else:
                    df_val = df_val.rename(columns={'收盘价': 'close'})
                    df_val['high'] = df_val['close']
            except Exception as e_daily:
                logger.warning(f"Error fetching daily data for {sym}: {e_daily}")
                df_val = df_val.rename(columns={'收盘价': 'close'})
                df_val['high'] = df_val['close']
            
            # fill static scale
            scale = None
            if not df_info.empty and sym in df_info['symbol'].values:
                scale_vals = df_info.loc[df_info['symbol'] == sym, 'outstanding_scale'].values
                if len(scale_vals) > 0:
                    scale = scale_vals[0]
                
            df_val['symbol'] = sym
            df_val['outstanding_scale'] = pd.to_numeric(scale, errors='coerce')
            
            # Ensure proper typing
            df_val['close'] = pd.to_numeric(df_val['close'], errors='coerce')
            df_val['high'] = pd.to_numeric(df_val['high'], errors='coerce')
            df_val['premium_rate'] = pd.to_numeric(df_val['premium_rate'], errors='coerce')
            
            all_data.append(df_val[['date', 'symbol', 'close', 'high', 'premium_rate', 'outstanding_scale']])
            
        except Exception as e:
            logger.warning(f"Error fetching data for {sym}: {e}")
            continue
            
    if not all_data:
        return pd.DataFrame(columns=['date', 'symbol', 'close', 'high', 'premium_rate', 'outstanding_scale'])
        
    final_df = pd.concat(all_data, ignore_index=True)
    final_df['date'] = pd.to_datetime(final_df['date'])
    
    if save_path:
        if save_path.endswith('.csv'):
            final_df.to_csv(save_path, index=False)
        elif save_path.endswith('.parquet'):
            final_df.to_parquet(save_path, index=False)
            
    return final_df

if __name__ == "__main__":
    # Quick test on a small subset
    df = fetch_cb_history(symbols=['113527', '128039'], save_path='cb_history_sample.csv')
    print(df.head())
