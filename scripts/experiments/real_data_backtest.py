import yfinance as yf
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(message)s')

def fetch_data(ticker, start_date, end_date):
    """Fetch historical daily data using yfinance."""
    df = yf.download(ticker, start=start_date, end=end_date, progress=False)
    df.reset_index(inplace=True)
    df = df[['Date', 'Close']]
    df.columns = ['date', 'close']
    return df

def run_backtest():
    # A-share tickers in yfinance format
    # 159501.SZ -> 159501.SZ
    # 513100.SH -> 513100.SS
    symbol_A = '159501.SZ' # 嘉实纳指
    symbol_B = '513100.SS' # 国泰纳指
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365) # Past 1 year
    
    logging.info(f"Downloading real daily K-lines for {symbol_A} and {symbol_B}...")
    try:
        df_A = fetch_data(symbol_A, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        df_B = fetch_data(symbol_B, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    except Exception as e:
        logging.error(f"Failed to download data: {e}")
        return
        
    if df_A.empty or df_B.empty:
        logging.error("Downloaded data is empty.")
        return
        
    df_A = df_A.rename(columns={'close': 'price_A'})
    df_B = df_B.rename(columns={'close': 'price_B'})
    
    # Merge on date
    df = pd.merge(df_A, df_B, on='date', how='inner').sort_values('date').reset_index(drop=True)
    
    # Clean data (flatten MultiIndex if returned by yfinance)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
        
    df['price_A'] = pd.to_numeric(df['price_A'], errors='coerce')
    df['price_B'] = pd.to_numeric(df['price_B'], errors='coerce')
    df = df.dropna().reset_index(drop=True)
    
    if len(df) < 30:
        logging.error(f"Not enough common data points ({len(df)} found). Need at least 30.")
        return

    # Calculate Ratio A/B
    df['ratio'] = df['price_A'] / df['price_B']
    
    # Calculate Z-Score (20-day rolling)
    window = 20
    df['ratio_mean'] = df['ratio'].rolling(window=window).mean()
    df['ratio_std'] = df['ratio'].rolling(window=window).std()
    df['z_score'] = (df['ratio'] - df['ratio_mean']) / df['ratio_std']
    
    # Drop NaNs from rolling window initialization
    df = df.dropna().reset_index(drop=True)
    
    # Strategy Logic
    df['ret_A'] = df['price_A'].pct_change().fillna(0)
    df['ret_B'] = df['price_B'].pct_change().fillna(0)
    
    # We maintain a 100% position in either A or B. Start with B.
    current_holding = 'B'
    portfolio_value = 1.0
    portfolio_values = [1.0]
    trades = 0
    trade_log = []
    
    for i in range(1, len(df)):
        z = df.loc[i-1, 'z_score'] # use yesterday's Z-score to avoid look-ahead bias
        date = df.loc[i, 'date'].strftime('%Y-%m-%d')
        
        if z > 1.5 and current_holding == 'A':
            # Swap from A to B
            current_holding = 'B'
            trades += 1
            trade_log.append(f"{date}: 卖出 159501, 买入 513100 (Z-Score: {z:.2f})")
            portfolio_value *= (1 - 0.0003) # 万3双边手续费/滑点
            
        elif z < -1.5 and current_holding == 'B':
            # Swap from B to A
            current_holding = 'A'
            trades += 1
            trade_log.append(f"{date}: 卖出 513100, 买入 159501 (Z-Score: {z:.2f})")
            portfolio_value *= (1 - 0.0003)
            
        ret = df.loc[i, 'ret_A'] if current_holding == 'A' else df.loc[i, 'ret_B']
        portfolio_value *= (1 + ret)
        portfolio_values.append(portfolio_value)
        
    df['portfolio'] = portfolio_values
    df['benchmark'] = (1 + df['ret_B']).cumprod()
    df.loc[0, 'benchmark'] = 1.0
    
    end_port = df['portfolio'].iloc[-1]
    end_bench = df['benchmark'].iloc[-1]
    excess_return = end_port - end_bench
    
    print("\n============== 纳指ETF 轮动套利真实数据回测 ==============")
    print(f"回测区间: {df['date'].iloc[0].strftime('%Y-%m-%d')} 到 {df['date'].iloc[-1].strftime('%Y-%m-%d')} (近一年实际K线)")
    print(f"对比标的: 159501.SZ (嘉实) vs 513100.SH (国泰)")
    print(f"触发阈值: Bollinger Bands Z-Score 偏离度 > 1.5")
    print(f"摩擦成本预设: 万3 (双边调仓滑点+佣金)")
    print("--------------------------------------------------")
    print(f"数据天数: {len(df)} 个交易日")
    print(f"调仓次数 (Swaps): {trades} 次")
    print(f"一直死扛 513100 (基准净值): {end_bench:.4f}")
    print(f"轮动策略最终净值: {end_port:.4f}")
    print(f"策略超额收益 (Alpha): {excess_return*100:+.2f}%")
    print("==================================================\n")
    
    if trades > 0:
        print("最新 5 次调仓记录:")
        for log in trade_log[-5:]:
            print("  -> " + log)
    else:
        print("未触发调仓，一直持有底仓。")

if __name__ == "__main__":
    run_backtest()