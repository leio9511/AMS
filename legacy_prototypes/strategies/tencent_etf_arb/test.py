#!/usr/bin/env python3
"""
腾讯ETF套利监控 - 测试版
忽略交易时段限制，随时可测试
"""

import sys
from pathlib import Path

# 导入监控模块
sys.path.insert(0, str(Path(__file__).parent))
from monitor import (
    get_etf_info,
    get_stock_prices_and_changes,
    calculate_realtime_nav,
    generate_alert_message,
    TENCENT_SHARES,
    TRADE_RATIO,
    THRESHOLD
)
from datetime import datetime

def main():
    print("=" * 60)
    print("腾讯ETF套利监控 - 测试模式")
    print("=" * 60)
    
    # 获取数据
    etf_info = get_etf_info()
    if not etf_info:
        print("获取ETF数据失败")
        return
    
    stock_data = get_stock_prices_and_changes()
    if not stock_data or 'hk00700' not in stock_data:
        print("获取成分股数据失败")
        return
    
    # 计算实时净值
    realtime_nav, weighted_change = calculate_realtime_nav(etf_info, stock_data)
    
    # 计算溢价率
    premium = (etf_info['price'] - realtime_nav) / realtime_nav * 100
    tencent_price = stock_data['hk00700']['price']
    
    # 显示成分股详情
    print("\n成分股涨跌幅:")
    print("-" * 60)
    for code, data in stock_data.items():
        if code.startswith('hk'):
            import monitor
            if code in monitor.PORTFOLIO_WEIGHTS:
                info = monitor.PORTFOLIO_WEIGHTS[code]
                print(f"{code}: {info['name']:<12} {data['change_pct']:+.2f}% (权重{info['weight']:.1f}%)")
    print("-" * 60)
    print(f"加权涨跌幅: {weighted_change:+.2f}%")
    
    # 显示净值计算
    print(f"\n净值计算:")
    print(f"  昨收: {etf_info['prev_close']:.4f}")
    print(f"  实时净值: {realtime_nav:.4f}")
    print(f"  现价: {etf_info['price']:.4f}")
    print(f"  溢价率: {premium:+.2f}%")
    print(f"  腾讯价格: {tencent_price:.2f} HKD")
    
    # 判断套利机会
    if abs(premium) >= THRESHOLD:
        msg = generate_alert_message(etf_info, realtime_nav, premium, tencent_price)
        print("\n" + "="*60)
        print(msg)
        print("="*60)
    else:
        print(f"\n⚪ 折溢价率 {premium:+.2f}% < {THRESHOLD}%，暂无套利空间")
    
    print("\n" + "=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

if __name__ == "__main__":
    main()
