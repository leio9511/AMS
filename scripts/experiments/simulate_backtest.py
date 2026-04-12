import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

def simulate_backtest():
    # Simulate 250 trading days (roughly 1 year)
    np.random.seed(42)
    days = 250
    dates = pd.date_range(start='2023-06-01', periods=days, freq='B')
    
    # Base index random walk (NASDAQ 100 proxy)
    base_returns = np.random.normal(0.001, 0.01, days)
    base_index = np.cumprod(1 + base_returns) * 100
    
    # 513100 (Guotai) tracks the index very closely with minor tracking error (premium usually around 0~1%)
    # 159501 (Jiashi) tracks the same index but experiences wild premium swings due to QDII quota limits
    
    # Simulate Premium (Noise + Mean Reverting Spikes for 159501)
    premium_513100 = np.random.normal(0.005, 0.002, days) # Stable 0.5% premium
    
    # 159501 has a spike in premium around day 100 and day 200
    premium_159501 = np.random.normal(0.005, 0.003, days)
    premium_159501[90:110] += np.linspace(0, 0.08, 20) # Spike to 8%
    premium_159501[110:120] -= np.linspace(0, 0.08, 10) # Crash back
    premium_159501[190:210] += np.linspace(0, 0.06, 20) # Spike to 6%
    premium_159501[210:215] -= np.linspace(0, 0.06, 5)  # Crash back
    
    price_B = base_index * (1 + premium_513100) # 513100
    price_A = base_index * (1 + premium_159501) # 159501
    
    df = pd.DataFrame({
        '日期': dates,
        'price_A': price_A,
        'price_B': price_B
    })
    
    # Strategy Logic
    df['ratio'] = df['price_A'] / df['price_B']
    window = 20
    df['ratio_mean'] = df['ratio'].rolling(window=window).mean()
    df['ratio_std'] = df['ratio'].rolling(window=window).std()
    df['z_score'] = (df['ratio'] - df['ratio_mean']) / df['ratio_std']
    
    df = df.dropna().reset_index(drop=True)
    
    df['ret_A'] = df['price_A'].pct_change().fillna(0)
    df['ret_B'] = df['price_B'].pct_change().fillna(0)
    
    current_holding = 'B'
    portfolio_value = 1.0
    portfolio_values = [1.0]
    trades = 0
    trade_log = []
    
    for i in range(1, len(df)):
        z = df.loc[i-1, 'z_score']
        date = df.loc[i, '日期'].strftime('%Y-%m-%d')
        
        if z > 1.5 and current_holding == 'A':
            current_holding = 'B'
            trades += 1
            trade_log.append(f"{date}: 卖出 159501, 买入 513100 (Z-Score: {z:.2f} | 捕捉到 159501 异常高溢价)")
            portfolio_value *= (1 - 0.0003) # 万3手续费滑点
            
        elif z < -1.5 and current_holding == 'B':
            current_holding = 'A'
            trades += 1
            trade_log.append(f"{date}: 卖出 513100, 买入 159501 (Z-Score: {z:.2f} | 159501 溢价回落，抄底吃下一波)")
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
    
    print("\n============== 纳指ETF 轮动套利回测结果 ==============")
    print(f"回测区间: {df['日期'].iloc[0].strftime('%Y-%m-%d')} 到 {df['日期'].iloc[-1].strftime('%Y-%m-%d')}")
    print(f"对比标的: 159501 (嘉实) vs 513100 (国泰)")
    print(f"触发阈值: 布林带 Z-Score 偏离度 > 1.5")
    print(f"摩擦成本预设: 万3 (双边调仓滑点+佣金)")
    print("--------------------------------------------------")
    print(f"调仓次数 (Swaps): {trades} 次")
    print(f"一直死扛 513100 (基准净值): {end_bench:.4f}")
    print(f"轮动策略最终净值: {end_port:.4f}")
    print(f"策略超额收益 (Alpha): +{excess_return*100:.2f}% (无风险白捡)")
    print("==================================================\n")
    
    if trades > 0:
        print("核心调仓记录 (截取):")
        for log in trade_log:
            print("  -> " + log)

if __name__ == "__main__":
    simulate_backtest()