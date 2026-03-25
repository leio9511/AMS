#!/usr/bin/env python3
"""
基于成分股涨跌幅计算ETF实时净值
逻辑：
1. 获取昨天净值
2. 计算成分股今天涨跌幅（加权）
3. 实时净值 = 昨天净值 × (1 + 加权涨跌幅)
"""

import requests
import re
from datetime import datetime, timedelta

# 中概互联ETF (513050) 成分股权重
# 数据来源：基金最新持仓公告
PORTFOLIO_WEIGHTS = {
    "hk00700": {"name": "腾讯控股", "weight": 29.5},
    "hk09988": {"name": "阿里巴巴-SW", "weight": 24.3},
    "hk03690": {"name": "美团-W", "weight": 14.8},
    "hk09618": {"name": "京东集团-SW", "weight": 9.2},
    "hk09999": {"name": "网易-S", "weight": 6.1},
    "hk09888": {"name": "百度集团-SW", "weight": 4.5},
    "hk02015": {"name": "理想汽车-W", "weight": 3.2},
    "hk09868": {"name": "小鹏汽车-W", "weight": 2.8},
    "hk09626": {"name": "哔哩哔哩-W", "weight": 2.1},
    "hk01810": {"name": "小米集团-W", "weight": 1.8},
}

# 汇率
HKD_CNY_RATE = 0.92

def get_etf_info():
    """获取ETF基本信息（昨天净值）"""
    url = "http://qt.gtimg.cn/q=sh513050"
    try:
        resp = requests.get(url, timeout=5)
        content = resp.content.decode('gbk')
        match = re.search(r'v_sh513050="(.*)"', content)
        if match:
            fields = match.group(1).split('~')
            # 字段：
            # 3: 现价
            # 4: 昨收
            # 30: 时间
            # -7: 可能是净值
            
            current_price = float(fields[3])
            prev_close = float(fields[4])
            timestamp = fields[30]
            
            return {
                'price': current_price,
                'prev_close': prev_close,
                'timestamp': timestamp,
            }
    except Exception as e:
        print(f"获取ETF信息失败: {e}")
    return None

def get_stock_prices_and_changes():
    """
    获取成分股实时价格和涨跌幅
    返回：{code: {'price': 价格, 'change_pct': 涨跌幅%}}
    """
    codes = [f"r_{code}" for code in PORTFOLIO_WEIGHTS.keys()]
    url = f"http://qt.gtimg.cn/q={','.join(codes)}"
    
    try:
        resp = requests.get(url, timeout=5)
        content = resp.content.decode('gbk')
        
        result = {}
        items = content.strip().split(';')
        
        for item in items:
            if not item.strip():
                continue
            
            match = re.search(r'v_([a-zA-Z0-9_]+)="(.*)"', item)
            if not match:
                continue
            
            full_code = match.group(1)  # r_hk00700
            fields = match.group(2).split('~')
            
            if 'hk' not in full_code or len(fields) < 35:
                continue
            
            code = full_code.replace('r_', '')  # hk00700
            
            try:
                # 字段说明：
                # 3: 现价
                # 4: 昨收
                # 32: 涨跌幅
                price = float(fields[3])
                prev_close = float(fields[4])
                change_pct = float(fields[32]) if fields[32] else ((price / prev_close - 1) * 100)
                
                result[code] = {
                    'price': price,
                    'prev_close': prev_close,
                    'change_pct': change_pct
                }
            except Exception as e:
                print(f"解析 {code} 失败: {e}")
        
        return result
    except Exception as e:
        print(f"获取股价失败: {e}")
        return {}

def calculate_weighted_change(stock_data):
    """
    计算成分股加权涨跌幅
    """
    total_weight = sum(info['weight'] for info in PORTFOLIO_WEIGHTS.values())
    weighted_change = 0
    total_covered_weight = 0
    
    print("\n成分股涨跌幅:")
    print("-" * 60)
    print(f"{'代码':<12} {'名称':<15} {'涨跌幅':<10} {'权重':<10} {'加权贡献':<10}")
    print("-" * 60)
    
    for code, info in PORTFOLIO_WEIGHTS.items():
        if code in stock_data:
            change = stock_data[code]['change_pct']
            weight = info['weight']
            contribution = change * weight / 100
            weighted_change += contribution
            total_covered_weight += weight
            
            print(f"{code:<12} {info['name']:<15} {change:+.2f}%     {weight:.1f}%      {contribution:+.4f}%")
    
    print("-" * 60)
    print(f"覆盖权重: {total_covered_weight:.1f}% | 加权涨跌幅: {weighted_change:+.2f}%")
    
    return weighted_change

def main():
    print("=" * 60)
    print("ETF实时净值计算 - 中概互联ETF (513050)")
    print("=" * 60)
    
    # 1. 获取ETF信息
    etf_info = get_etf_info()
    if not etf_info:
        print("获取ETF信息失败！")
        return
    
    print(f"\nETF信息:")
    print(f"  现价: {etf_info['price']:.3f}")
    print(f"  昨收: {etf_info['prev_close']:.3f}")
    print(f"  时间: {etf_info['timestamp']}")
    
    # 2. 获取成分股价格和涨跌幅
    stock_data = get_stock_prices_and_changes()
    if not stock_data:
        print("\n获取成分股数据失败！")
        return
    
    # 3. 计算加权涨跌幅
    weighted_change = calculate_weighted_change(stock_data)
    
    # 4. 计算实时净值
    # 昨天净值 = ETF昨收
    # 实时净值 = 昨天净值 × (1 + 加权涨跌幅)
    prev_nav = etf_info['prev_close']
    realtime_nav = prev_nav * (1 + weighted_change / 100)
    
    print(f"\n净值计算:")
    print(f"  昨天净值: {prev_nav:.4f}")
    print(f"  实时净值: {realtime_nav:.4f}")
    print(f"  现价: {etf_info['price']:.4f}")
    
    # 5. 计算折溢价率
    premium = (etf_info['price'] - realtime_nav) / realtime_nav * 100
    print(f"\n溢价率: {premium:+.2f}%")
    
    if abs(premium) > 2:
        if premium > 0:
            print("\n🔴 溢价套利机会：ETF贵了，卖出ETF，买入成分股")
        else:
            print("\n🟢 折价套利机会：ETF便宜，买入ETF，卖出成分股")
    else:
        print("\n⚪ 折溢价较小，暂无套利空间")
    
    print("\n" + "=" * 60)
    print(f"计算时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

if __name__ == "__main__":
    main()
