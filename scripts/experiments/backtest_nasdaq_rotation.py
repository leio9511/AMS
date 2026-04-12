import akshare as ak
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

def backtest_nasdaq_etfs():
    symbol_A = '159501' # 嘉实纳指
    symbol_B = '513100' # 国泰纳指
    
    logging.info(f"Downloading historical data for {symbol_A} and {symbol_B}...")
    df_A = ak.fund_etf_hist_em(symbol=symbol_A, period='daily', start_date='20230601', end_date='20260412')
    df_B = ak.fund_etf_hist_em(symbol=symbol_B, period='daily', start_date='20230601', end_date='20260412')
    
    # Rename columns
    df_A = df_A[['日期', '收盘']].rename(columns={'收盘': 'price_A'})
    df_B = df_B[['日期', '收盘']].rename(columns={'收盘': 'price_B'})
    
    # Merge and sort
    df = pd.merge(df_A, df_B, on='日期', how='inner').sort_values('日期').reset_index(drop=True)
    
    # Calculate Ratio A/B
    df['ratio'] = df['price_A'] / df['price_B']
    
    # Calculate Z-Score (20-day rolling)
    window = 20
    df['ratio_mean'] = df['ratio'].rolling(window=window).mean()
    df['ratio_std'] = df['ratio'].rolling(window=window).std()
    df['z_score'] = (df['ratio'] - df['ratio_mean']) / df['ratio_std']
    
    # Drop NaNs from rolling
    df = df.dropna().reset_index(drop=True)
    
    # Strategy Logic:
    # We maintain a 100% position in either A or B.
    # We start with holding B (because A was newly listed in June 2023).
    # If Z-score > 1.5 -> A is too expensive compared to B. We hold B.
    # If Z-score < -1.5 -> A is too cheap compared to B. We hold A.
    # We calculate the daily return of holding A vs holding B, and apply to our portfolio.
    
    df['ret_A'] = df['price_A'].pct_change()
    df['ret_B'] = df['price_B'].pct_change()
    
    # Initial state
    current_holding = 'B'
    portfolio_value = 1.0
    portfolio_values = [1.0]
    trades = 0
    trade_log = []
    
    for i in range(1, len(df)):
        z = df.loc[i-1, 'z_score'] # use yesterday's Z-score to decide today's holding
        date = df.loc[i, '日期']
        
        # Determine target holding
        if z > 1.5 and current_holding == 'A':
            # Swap from A to B
            current_holding = 'B'
            trades += 1
            trade_log.append(f"{date}: Swap from 159501 to 513100 (Z={z:.2f})")
            portfolio_value *= (1 - 0.0003) # assume 0.03% total slippage + commission for full swap
            
        elif z < -1.5 and current_holding == 'B':
            # Swap from B to A
            current_holding = 'A'
            trades += 1
            trade_log.append(f"{date}: Swap from 513100 to 159501 (Z={z:.2f})")
            portfolio_value *= (1 - 0.0003)
            
        # Apply daily return of current holding
        ret = df.loc[i, 'ret_A'] if current_holding == 'A' else df.loc[i, 'ret_B']
        portfolio_value *= (1 + ret)
        portfolio_values.append(portfolio_value)
        
    df['portfolio'] = portfolio_values
    
    # Calculate Benchmark (Buy & Hold 513100)
    df['benchmark'] = (1 + df['ret_B']).cumprod()
    df.loc[0, 'benchmark'] = 1.0 # fix first value
    
    # Print Results
    end_port = df['portfolio'].iloc[-1]
    end_bench = df['benchmark'].iloc[-1]
    excess_return = end_port - end_bench
    
    print("\n============== 纳指ETF 轮动套利回测结果 ==============")
    print(f"回测区间: {df['日期'].iloc[0]} 到 {df['日期'].iloc[-1]}")
    print(f"策略初始持仓: {symbol_B} (单只满仓轮动)")
    print(f"触发阈值: Bollinger Bands Z-Score 偏离度 > 1.5")
    print(f"摩擦成本预设: 万3 (双边调仓滑点+佣金)")
    print("--------------------------------------------------")
    print(f"调仓次数 (Swaps): {trades} 次")
    print(f"持有 {symbol_B} 死扛基准净值: {end_bench:.4f}")
    print(f"轮动策略最终净值: {end_port:.4f}")
    print(f"策略超额收益 (Alpha): {excess_return*100:.2f}%")
    print("==================================================\n")
    
    if trades > 0:
        print("最新 5 次调仓记录:")
        for log in trade_log[-5:]:
            print("  -> " + log)
    else:
        print("未触发调仓，一直持有底仓。")
        
if __name__ == "__main__":
    backtest_nasdaq_etfs()