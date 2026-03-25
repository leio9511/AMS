#!/usr/bin/env python3
"""
计算中概互联ETF (513050) 的实时净值
基于成分股实时价格和权重
"""

import requests
from datetime import datetime

# 中概互联ETF (513050) 前十大持仓（2024年数据，需定期更新）
# 数据来源：基金季报
# 格式：{港股代码: (权重%, 股数)}
# 注意：权重会随股价波动和基金调仓而变化

PORTFOLIO = {
    # 港股代码: (权重%, 名称)
    "hk00700": (29.5, "腾讯控股"),      # 第一大持仓
    "hk09988": (24.3, "阿里巴巴-SW"),   # 第二大持仓  
    "hk03690": (14.8, "美团-W"),        # 第三大持仓
    "hk09618": (9.2, "京东集团-SW"),    # 第四大持仓
    "hk09999": (6.1, "网易-S"),         # 第五大持仓
    "hk09888": (4.5, "百度集团-SW"),    # 第六大持仓
    "hk02015": (3.2, "理想汽车-W"),     # 第七大持仓
    "hk09868": (2.8, "小鹏汽车-W"),     # 第八大持仓
    "hk09626": (2.1, "哔哩哔哩-W"),     # 第九大持仓
    "hk01810": (1.8, "小米集团-W"),     # 第十大持仓
}

# 基金基本信息
FUND_CODE = "513050"
FUND_NAME = "中概互联ETF"
TOTAL_UNITS = 100000000  # 1亿份（示例，实际需查基金规模）

def get_realtime_prices(hk_codes):
    """
    获取港股实时价格
    返回: {hk_code: price_hkd}
    """
    codes_str = ",".join(hk_codes)
    url = f"http://qt.gtimg.cn/q={codes_str}"
    
    try:
        resp = requests.get(url, timeout=5)
        content = resp.content.decode('gbk')
        
        prices = {}
        items = content.strip().split(';')
        for item in items:
            if not item.strip():
                continue
            
            import re
            match = re.search(r'v_([a-zA-Z0-9_]+)="(.*)"', item)
            if not match:
                continue
            
            full_code = match.group(1)  # e.g. "r_hk00700"
            # 提取港股代码 (去掉前缀)
            if 'hk' in full_code:
                code = full_code.replace('r_', '')
            else:
                continue
            fields = match.group(2).split('~')
            
            if len(fields) > 3:
                try:
                    price = float(fields[3])
                    prices[code] = price
                except:
                    pass
        
        return prices
    except Exception as e:
        print(f"获取价格失败: {e}")
        return {}

def get_hkdcny_rate():
    """
    获取港币兑人民币汇率
    返回: 1 HKD = ? CNY
    """
    # 方法1: 从外汇接口获取
    # 方法2: 使用固定值（实际应用中需要实时获取）
    # 这里先用固定值
    return 0.92

def calculate_nav(portfolio, prices, rate):
    """
    计算实时净值
    NAV = ∑(股票价格 × 汇率 × 权重)
    """
    nav = 0
    details = []
    
    for code, (weight, name) in portfolio.items():
        if code in prices:
            price_hkd = prices[code]
            price_cny = price_hkd * rate
            weighted_value = price_cny * weight / 100
            nav += weighted_value
            
            details.append({
                'code': code,
                'name': name,
                'price_hkd': price_hkd,
                'price_cny': price_cny,
                'weight': weight,
                'weighted_value': weighted_value
            })
        else:
            print(f"警告: 无法获取 {name} ({code}) 的价格")
    
    return nav, details

def main():
    print("=" * 60)
    print(f"实时净值计算 - {FUND_NAME} ({FUND_CODE})")
    print("=" * 60)
    
    # 获取港股实时价格
    hk_codes = list(PORTFOLIO.keys())
    print(f"\n获取 {len(hk_codes)} 只成分股实时价格...")
    prices = get_realtime_prices(hk_codes)
    
    if not prices:
        print("获取价格失败！")
        return
    
    # 获取汇率
    rate = get_hkdcny_rate()
    print(f"当前汇率: 1 HKD = {rate} CNY")
    
    # 计算净值
    nav, details = calculate_nav(PORTFOLIO, prices, rate)
    
    # 输出详情
    print("\n成分股详情:")
    print("-" * 60)
    print(f"{'代码':<12} {'名称':<15} {'价格(HKD)':<10} {'价格(CNY)':<10} {'权重':<8} {'贡献':<8}")
    print("-" * 60)
    
    for d in details:
        print(f"{d['code']:<12} {d['name']:<15} {d['price_hkd']:<10.2f} {d['price_cny']:<10.2f} {d['weight']:<8.1f}% {d['weighted_value']:<8.3f}")
    
    print("-" * 60)
    print(f"计算净值 (前十大): {nav:.4f} CNY")
    
    # 获取ETF现价和官方IOPV对比
    print("\n对比数据:")
    etf_data = get_realtime_prices(['sh513050'])
    if 'sh513050' in etf_data:
        etf_price = etf_data['sh513050']
        print(f"ETF现价: {etf_price:.3f} CNY")
        print(f"计算净值: {nav:.4f} CNY")
        print(f"溢价率: {(etf_price - nav) / nav * 100:+.2f}%")
    
    print("\n" + "=" * 60)
    print(f"计算时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

if __name__ == "__main__":
    main()
